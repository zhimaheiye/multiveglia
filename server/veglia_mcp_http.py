"""Authenticated HTTP MCP. No unauthenticated mode, including on the LAN."""
import os
import time
from collections import defaultdict, deque
from urllib.parse import urlparse

import uvicorn
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse
from starlette.requests import Request
from mcp.server.streamable_http import TransportSecuritySettings
from mcp.server.transport_security import RequestBodyLimitMiddleware

os.environ['VEGLIA_HTTP_MODE'] = '1'
from veglia_mcp import mcp, AUTH_PROVIDER


class AuthBoundary:
    """Bound auth requests; reject wrong token audiences before SDK handling."""
    def __init__(self, app):
        self.app = app
        self.hits = defaultdict(deque)

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        path = scope.get('path','')
        if path in ('/register','/authorize','/token','/consent','/revoke'):
            now = time.monotonic()
            key = 'login' if path == '/consent' and scope['method'] == 'POST' else 'auth'
            queue = self.hits[key]
            while queue and queue[0] < now - 60:
                queue.popleft()
            if len(queue) >= (10 if key == 'login' else 120):
                return await JSONResponse({'error':'rate_limited'},429,headers={'Retry-After':'60'})(scope,receive,send)
            queue.append(now)
        if path in ('/token', '/revoke') and scope['method'] == 'POST':
            request = Request(scope, receive)
            body = await request.body()
            from urllib.parse import parse_qs, urlencode
            form = parse_qs(body.decode('utf-8',errors='replace'), keep_blank_values=True)
            if any(len(values) != 1 for values in form.values()):
                return await JSONResponse({'error':'invalid_request'},400)(scope,receive,send)
            resource = form.get('resource', [None])[0]
            if resource is not None and resource != AUTH_PROVIDER.resource:
                return await JSONResponse({'error':'invalid_target'},400)(scope,receive,send)
            # SDK 2.1.1's revocation schema requires this nullable field even
            # for public PKCE clients. Authentication still runs in the SDK.
            if path == '/revoke' and 'client_secret' not in form:
                form['client_secret'] = ['']
                body = urlencode({k:v[0] for k,v in form.items()}).encode()
                scope = {**scope, 'headers':[(k,v) for k,v in scope['headers'] if k.lower() != b'content-length'] + [(b'content-length',str(len(body)).encode())]}
            delivered = False
            async def replay():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {'type':'http.request','body':body,'more_body':False}
                return await receive()
            return await self.app(scope,replay,send)
        return await self.app(scope,receive,send)


def create_app():
    public = urlparse(AUTH_PROVIDER.issuer)
    allowed = ['127.0.0.1:*','localhost:*','[::1]:*',public.netloc]
    allowed += [x.strip() for x in os.environ.get('VEGLIA_MCP_ALLOWED_HOSTS','').split(',') if x.strip()]
    origins = [AUTH_PROVIDER.issuer]
    origins += [x.strip() for x in os.environ.get('VEGLIA_MCP_ALLOWED_ORIGINS','').split(',') if x.strip()]
    app = mcp.streamable_http_app(streamable_http_path='/mcp',
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True,
            allowed_hosts=allowed, allowed_origins=origins),
        host=os.environ.get('VEGLIA_MCP_HOST','127.0.0.1'))
    app.add_route('/consent',AUTH_PROVIDER.consent,methods=['GET','POST'])
    async def health(request):
        return JSONResponse({'ok':True,'service':'veglia-mcp-http','authentication':'required'})
    app.add_route('/health',health,methods=['GET'])
    app.add_middleware(AuthBoundary)
    app.add_middleware(RequestBodyLimitMiddleware,max_body_size=256*1024)
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=list({urlparse('http://'+x).hostname or x for x in allowed}))
    return app


if __name__ == '__main__':
    # Query strings may contain authorization codes; access logging stays off.
    uvicorn.run(create_app(),host=os.environ.get('VEGLIA_MCP_HOST','127.0.0.1'),
        port=int(os.environ.get('VEGLIA_MCP_PORT','8514')),access_log=False,
        proxy_headers=False)
