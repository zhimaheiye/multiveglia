"""Single-owner OAuth authorization code + PKCE and independent API keys.

Protocol parsing/PKCE/client authentication use the MCP SDK. This provider owns
consent and a private SQLite credential store. Never put that store in a release.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse, urlencode

from mcp.server.auth.provider import (AccessToken, AuthorizationCode, AuthorizationParams,
    AuthorizeError, OAuthAuthorizationServerProvider, RefreshToken, RegistrationError,
    TokenError, construct_redirect_uri)
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
from security import matches, current_or_previous

SCOPES = ['veglia:read', 'veglia:capture', 'veglia:summon']
SCOPE_LABELS = {'veglia:read': '读取手机应用活动、电脑窗口标题与设备状态',
                'veglia:capture': '请求并读取手机截图', 'veglia:summon': '将手机上的指定应用拉到前台'}


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class OwnerOAuth(OAuthAuthorizationServerProvider[AuthorizationCode, RefreshToken, AccessToken]):
    def __init__(self, issuer, database, password):
        self.issuer = issuer.rstrip('/')
        self.resource = self.issuer + '/mcp'
        self.password = password
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS records (kind TEXT, key TEXT, data TEXT, expiry REAL, family TEXT, PRIMARY KEY(kind,key))')
        try:
            self.database.chmod(0o600)
        except OSError:
            pass

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def put(self, kind, key, data, expiry, family=''):
        with self.connect() as db:
            db.execute('DELETE FROM records WHERE expiry < ?', (time.time(),))
            count = db.execute('SELECT count(*) FROM records WHERE kind=?', (kind,)).fetchone()[0]
            if count >= (128 if kind == 'client' else 512):
                raise ValueError('Authorization store capacity reached; revoke unused clients locally.')
            db.execute('INSERT OR REPLACE INTO records VALUES (?,?,?,?,?)',
                       (kind, digest(key), json.dumps(data), expiry, family))

    def get(self, kind, key, consume=False):
        with self.connect() as db:
            if consume:
                db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT data,expiry,family FROM records WHERE kind=? AND key=?', (kind,digest(key))).fetchone()
            if not row or row[1] < time.time():
                return None
            if consume:
                db.execute('DELETE FROM records WHERE kind=? AND key=?', (kind,digest(key)))
            return json.loads(row[0]), row[2]

    def revoke_family(self, family):
        with self.connect() as db:
            db.execute("DELETE FROM records WHERE family=? AND kind != 'spent'", (family,))

    def valid_redirect(self, uri):
        u = urlparse(str(uri))
        if u.username or u.password or u.fragment:
            return False
        if u.scheme == 'http' and u.hostname in ('127.0.0.1', 'localhost', '::1'):
            return True
        if u.scheme != 'https':
            return False
        if u.hostname == 'chatgpt.com' and u.port in (None, 443) and not u.query:
            return u.path == '/connector_platform_oauth_redirect' or bool(re.fullmatch(r'/connector/oauth/[A-Za-z0-9_-]+', u.path))
        return str(uri) in os.environ.get('VEGLIA_OAUTH_REDIRECT_URIS', '').split(',')

    async def register_client(self, client_info):
        if not self.password:
            raise RegistrationError('invalid_client_metadata', 'OAuth is not enabled.')
        uris = client_info.redirect_uris or []
        if not uris or len(uris) > 8 or any(not self.valid_redirect(u) for u in uris):
            raise RegistrationError('invalid_redirect_uri', 'Redirect URI is not allowed by this server owner.')
        if client_info.token_endpoint_auth_method not in ('none', 'client_secret_post'):
            raise RegistrationError('invalid_client_metadata', 'Use none (PKCE) or client_secret_post.')
        try:
            self.put('client', client_info.client_id, client_info.model_dump(mode='json'), time.time()+365*86400)
        except ValueError:
            raise RegistrationError('invalid_client_metadata', 'Client registration capacity reached.')

    async def get_client(self, client_id):
        row = self.get('client', client_id)
        return OAuthClientInformationFull.model_validate(row[0]) if row else None

    async def authorize(self, client, params):
        if not self.password:
            raise AuthorizeError('access_denied', 'OAuth is not enabled.')
        if params.resource not in (None, self.resource):
            raise AuthorizeError('invalid_target', 'Wrong MCP resource.')
        if not self.valid_redirect(params.redirect_uri):
            raise AuthorizeError('access_denied', 'Redirect no longer allowed.')
        requested = params.scopes or ['veglia:read']
        if not set(requested).issubset(SCOPES) or 'veglia:read' not in requested:
            raise AuthorizeError('invalid_scope', 'Request veglia:read and optional capture/summon scopes.')
        if not re.fullmatch(r'[A-Za-z0-9_-]{43}', params.code_challenge):
            raise AuthorizeError('invalid_request', 'A SHA-256 PKCE challenge is required.')
        nonce = secrets.token_urlsafe(32)
        try:
            self.put('pending', nonce, {'client_id':client.client_id, 'params':params.model_dump(mode='json')}, time.time()+300)
        except ValueError:
            raise AuthorizeError('temporarily_unavailable', 'Too many pending requests.')
        return self.issuer + '/consent?' + urlencode({'request':nonce})

    async def consent(self, request):
        nonce = request.query_params.get('request', '')
        pending = self.get('pending', nonce)
        headers = {'Cache-Control':'no-store', 'Referrer-Policy':'no-referrer',
                   'X-Frame-Options':'DENY', 'Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'"}
        if not pending:
            return HTMLResponse('授权请求已过期，请从 Agent 重新连接。', status_code=400, headers=headers)
        data = pending[0]
        params = AuthorizationParams.model_validate(data['params'])
        client = await self.get_client(data['client_id'])
        if not client:
            return HTMLResponse('Client revoked.', status_code=400, headers=headers)
        scopes = params.scopes or ['veglia:read']
        if request.method == 'POST':
            form = await request.form()
            csrf = str(form.get('csrf',''))
            cookie = request.cookies.get('veglia_consent','')
            origin = request.headers.get('origin')
            if (origin and origin != self.issuer) or not csrf or not matches(csrf, cookie) or not matches(digest(csrf), data.get('csrf','')):
                return HTMLResponse('Invalid consent request.', status_code=403, headers=headers)
            if form.get('decision') == 'deny':
                self.get('pending', nonce, consume=True)
                return RedirectResponse(construct_redirect_uri(str(params.redirect_uri), error='access_denied', state=params.state, iss=self.issuer), status_code=303, headers=headers)
            if not matches(str(form.get('password','')), self.password):
                return HTMLResponse('授权密码错误，请返回重试。', status_code=403, headers=headers)
            chosen = list(form.getlist('scope'))
            if 'veglia:read' not in chosen or not set(chosen).issubset(scopes):
                return HTMLResponse('Invalid scope selection.', status_code=400, headers=headers)
            if not self.get('pending', nonce, consume=True):
                return HTMLResponse('Already used.', status_code=400, headers=headers)
            code = secrets.token_urlsafe(32)
            record = AuthorizationCode(code='', client_id=client.client_id, scopes=chosen,
                expires_at=time.time()+120, code_challenge=params.code_challenge,
                redirect_uri=params.redirect_uri, redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
                resource=self.resource, subject='owner')
            self.put('code', code, record.model_dump(mode='json'), record.expires_at)
            response = RedirectResponse(construct_redirect_uri(str(params.redirect_uri), code=code, state=params.state, iss=self.issuer), status_code=303, headers=headers)
            response.delete_cookie('veglia_consent', path='/consent')
            return response
        csrf = secrets.token_urlsafe(32)
        data['csrf'] = digest(csrf)
        self.put('pending', nonce, data, time.time()+300)
        checkboxes = ''.join(f'<label><input type="checkbox" name="scope" value="{html.escape(s)}" {"checked" if s == "veglia:read" else ""}> {SCOPE_LABELS[s]}</label>' for s in scopes)
        page = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>授权访问 Veglia</title>
        <style>body{{font:17px system-ui;max-width:640px;margin:8vh auto;padding:24px;color:#142321;background:#f3f6f5}}label{{display:block;margin:18px 0}}input[type=password]{{width:90%;padding:12px}}button{{padding:12px 20px;margin:16px 12px 0 0}}small{{overflow-wrap:anywhere}}</style>
        <h1>授权访问你的 Veglia</h1><p>客户端：<strong>{html.escape(client.client_name or 'Unnamed client')}</strong></p>
        <p><small>返回地址：{html.escape(str(params.redirect_uri))}</small></p><p>只有在你刚刚主动连接 Agent 时继续。名称由客户端提供；请核对返回地址。</p>
        <form method="post"><input type="hidden" name="csrf" value="{csrf}">{checkboxes}
        <label>本机生成的 OAuth 授权密码<input type="password" name="password" autocomplete="current-password" required></label>
        <button name="decision" value="allow">授权所选权限</button><button name="decision" value="deny" formnovalidate>拒绝</button></form></html>'''
        response = HTMLResponse(page, headers=headers)
        response.set_cookie('veglia_consent', csrf, max_age=300, httponly=True, secure=self.issuer.startswith('https:'), samesite='lax', path='/consent')
        return response

    async def load_authorization_code(self, client, authorization_code):
        row = self.get('code', authorization_code)
        if not row or row[0]['client_id'] != client.client_id:
            return None
        return AuthorizationCode.model_validate({**row[0], 'code':authorization_code})

    def issue(self, client_id, scopes, family=None):
        family = family or secrets.token_urlsafe(24)
        access, refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        now = int(time.time())
        a = AccessToken(token='',client_id=client_id,scopes=scopes,expires_at=now+3600,resource=self.resource,subject='owner',claims={'iss':self.issuer})
        r = RefreshToken(token='',client_id=client_id,scopes=scopes,expires_at=now+7*86400,subject='owner')
        self.put('access',access,a.model_dump(mode='json'),a.expires_at,family)
        self.put('refresh',refresh,r.model_dump(mode='json'),r.expires_at,family)
        return OAuthToken(access_token=access,token_type='Bearer',expires_in=3600,refresh_token=refresh,scope=' '.join(scopes))

    async def exchange_authorization_code(self, client, authorization_code):
        if not self.get('code',authorization_code.code,consume=True):
            raise TokenError('invalid_grant','Authorization code already used or expired.')
        return self.issue(client.client_id, authorization_code.scopes)

    async def load_refresh_token(self, client, refresh_token):
        spent = self.get('spent',refresh_token)
        if spent:
            self.revoke_family(spent[1])
            return None
        row = self.get('refresh',refresh_token)
        if not row or row[0]['client_id'] != client.client_id:
            return None
        return RefreshToken.model_validate({**row[0],'token':refresh_token})

    async def exchange_refresh_token(self, client, refresh_token, scopes):
        row = self.get('refresh',refresh_token.token,consume=True)
        if not row or not set(scopes).issubset(row[0]['scopes']):
            raise TokenError('invalid_grant','Refresh token invalid or scope increased.')
        family = row[1]
        self.put('spent',refresh_token.token,{},time.time()+7*86400,family)
        self.revoke_family(family)
        return self.issue(client.client_id,scopes,family)

    async def load_access_token(self, token):
        for name, scopes in [('VEGLIA_MCP_TOKEN',SCOPES),('VEGLIA_MCP_READ_TOKEN',['veglia:read'])]:
            if current_or_previous(token,name):
                return AccessToken(token=token,client_id=name,scopes=scopes,resource=self.resource,subject='owner',claims={'iss':self.issuer})
        row = self.get('access',token)
        if not row or row[0].get('resource') != self.resource or row[0].get('claims',{}).get('iss') != self.issuer:
            return None
        return AccessToken.model_validate({**row[0],'token':token})

    async def revoke_token(self, token):
        for kind in ('access','refresh'):
            row = self.get(kind,token.token)
            if row:
                self.revoke_family(row[1])


def build_auth():
    issuer = os.environ.get('VEGLIA_PUBLIC_URL','http://127.0.0.1:8514').rstrip('/')
    parsed = urlparse(issuer)
    if parsed.path or parsed.query or parsed.fragment or parsed.username or not parsed.hostname:
        raise ValueError('VEGLIA_PUBLIC_URL must be an origin without path, query, or credentials.')
    if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1','localhost','::1')):
        raise ValueError('Public MCP requires HTTPS.')
    password = os.environ.get('VEGLIA_OAUTH_PASSWORD','')
    credentials = [os.environ.get(n,'') for n in ('VEGLIA_MCP_TOKEN','VEGLIA_MCP_READ_TOKEN','VEGLIA_OAUTH_PASSWORD')]
    if not any(credentials) or any(x and len(x) < 32 for x in credentials):
        raise ValueError('Configure independent random MCP credentials of at least 32 characters.')
    configured = [x for x in credentials if x]
    if len(set(configured)) != len(configured) or os.environ.get('VEGLIA_TOKEN') in configured:
        raise ValueError('Core, MCP, read-only, and OAuth credentials must be different.')
    database = os.environ.get('VEGLIA_AUTH_DB',str(Path(__file__).parent/'data'/'auth.sqlite3'))
    provider = OwnerOAuth(issuer,database,password)
    settings = AuthSettings(issuer_url=issuer,resource_server_url=provider.resource,
        required_scopes=['veglia:read'],client_registration_options=ClientRegistrationOptions(
            enabled=bool(password),valid_scopes=SCOPES,default_scopes=['veglia:read']),
        revocation_options=RevocationOptions(enabled=True))
    return provider, settings
