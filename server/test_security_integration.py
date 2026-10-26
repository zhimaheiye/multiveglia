"""Isolated protocol/security tests; never contact the owner's running services."""
import asyncio
import base64
import hashlib
import json
import os
import re
import secrets
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

HERE = Path(__file__).resolve().parent


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1',0))
        return s.getsockname()[1]


class SecurityIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.processes = []
        cls.logs = []
        cls.core = f'http://127.0.0.1:{free_port()}'
        cls.base = f'http://127.0.0.1:{free_port()}'
        cls.keys = {k:secrets.token_urlsafe(32) for k in ['core','phone','sensor','full','read','owner','previous']}
        env = {k:v for k,v in os.environ.items() if not k.startswith('VEGLIA_')}
        env['PYTHONPATH'] = os.pathsep.join(sys.path)
        env.update(VEGLIA_TOKEN=cls.keys['core'],VEGLIA_PHONE_TOKEN=cls.keys['phone'],
            VEGLIA_SENSOR_TOKEN=cls.keys['sensor'],VEGLIA_MCP_TOKEN=cls.keys['full'],
            VEGLIA_MCP_READ_TOKEN=cls.keys['read'],VEGLIA_OAUTH_PASSWORD=cls.keys['owner'],
            VEGLIA_PHONE_TOKEN_PREVIOUS=cls.keys['previous'],VEGLIA_PHONE_TOKEN_PREVIOUS_UNTIL=str(time.time()+3600),
            VEGLIA_HOST='127.0.0.1',VEGLIA_PORT=str(urlparse(cls.core).port),
            VEGLIA_URL=cls.core,VEGLIA_PUBLIC_URL=cls.base,VEGLIA_MCP_PORT=str(urlparse(cls.base).port),
            VEGLIA_AUTH_DB=str(Path(cls.tmp.name)/'auth.sqlite3'),VEGLIA_DATA_DIR=cls.tmp.name,
            VEGLIA_HOOK='',PYTHONIOENCODING='utf-8')
        cls.http = httpx2.Client(trust_env=False,timeout=10,follow_redirects=False)
        try:
            for script,url in [('veglia_server.py',cls.core),('veglia_mcp_http.py',cls.base)]:
                log=open(Path(cls.tmp.name)/(script+'.log'),'w+',encoding='utf-8');cls.logs.append(log)
                proc=subprocess.Popen([getattr(sys,'_base_executable',sys.executable),str(HERE/script)],env=env,cwd=cls.tmp.name,stdout=log,stderr=log)
                cls.processes.append(proc)
                for _ in range(100):
                    if proc.poll() is not None:
                        log.seek(0);raise RuntimeError(log.read())
                    try:
                        if cls.http.get(url+'/health').status_code==200:break
                    except httpx2.RequestError:pass
                    time.sleep(.1)
                else:
                    log.flush();log.seek(0)
                    raise RuntimeError('Server startup timed out: '+script+' '+log.read()[-6000:])
        except Exception:
            cls.tearDownClass();raise

    @classmethod
    def tearDownClass(cls):
        for proc in cls.processes:
            proc.terminate()
            try:proc.wait(timeout=10)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()
        cls.http.close()
        for log in cls.logs:log.close()
        cls.tmp.cleanup()

    def test_core_role_separation(self):
        for credential in ['',self.keys['phone'],self.keys['sensor'],self.keys['full']]:
            r=self.http.get(self.core+'/context',headers={'X-Auth-Token':credential})
            self.assertEqual(r.status_code,403)
        self.assertEqual(self.http.get(self.core+'/context',headers={'X-Auth-Token':self.keys['core']}).status_code,200)
        for token in [self.keys['phone'],self.keys['previous']]:
            self.assertEqual(self.http.post(self.core+'/phone/activity',json={'app':'test.app'},headers={'X-Auth-Token':token}).status_code,200)
            self.assertEqual(self.http.post(self.core+'/phone/summon',headers={'X-Auth-Token':token}).status_code,403)
        self.assertEqual(self.http.post(self.core+'/devices/report',json={'device_id':'test-pc'},headers={'X-Auth-Token':self.keys['sensor']}).status_code,200)
        self.assertEqual(self.http.get(self.core+'/context?token='+self.keys['core']).status_code,403)

    def test_mcp_missing_wrong_and_core_credentials_denied(self):
        for method in ['GET','POST','DELETE']:
            for token in ['', 'incorrect', self.keys['core'], self.keys['phone']]:
                r=self.http.request(method,self.base+'/mcp',headers={'Authorization':'Bearer '+token} if token else {})
                self.assertEqual(r.status_code,401)
                self.assertIn('resource_metadata',r.headers.get('www-authenticate',''))

    def test_mcp_real_handshake_and_readonly_scopes(self):
        async def run():
            async with httpx2.AsyncClient(trust_env=False,headers={'Authorization':'Bearer '+self.keys['read']}) as http:
                async with streamable_http_client(self.base+'/mcp',http_client=http) as streams:
                    async with ClientSession(streams[0],streams[1]) as session:
                        await session.initialize()
                        self.assertEqual(len((await session.list_tools()).tools),8)
                        status=await session.call_tool('get_veglia_status',{})
                        self.assertFalse(status.is_error)
                        text=''.join(getattr(c,'text','') for c in status.content)
                        self.assertNotIn('screenshots_dir',text)
                        for name in ['get_phone_screen','summon_phone_ai']:
                            r=await session.call_tool(name,{})
                            self.assertTrue(r.is_error)
                            self.assertIn('mcp/www_authenticate',r.meta)
        asyncio.run(run())

    def test_host_origin_and_body_limits(self):
        self.assertEqual(self.http.get(self.base+'/health',headers={'Host':'evil.example'}).status_code,400)
        r=self.http.post(self.base+'/mcp',headers={'Authorization':'Bearer '+self.keys['read'],'Origin':'https://evil.example'},json={})
        self.assertIn(r.status_code,[400,403])
        self.assertEqual(self.http.post(self.base+'/register',content=b'x'*(256*1024+1)).status_code,413)
        # Send only the oversized length: the Core must reject before reading
        # the body. Sending the entire body races a TCP reset on Windows when
        # BaseHTTPRequestHandler closes a connection with unread upload bytes.
        with socket.create_connection(('127.0.0.1',urlparse(self.core).port),timeout=5) as sock:
            sock.sendall((f'POST /phone/activity HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: {256*1024+1}\r\nX-Auth-Token: {self.keys["phone"]}\r\nConnection: close\r\n\r\n').encode())
            self.assertIn(b' 413 ',sock.recv(4096).split(b'\r\n',1)[0])

    def register(self):
        r=self.http.post(self.base+'/register',json={'client_name':'Integration test','redirect_uris':['http://127.0.0.1:18999/callback'],
            'token_endpoint_auth_method':'none','grant_types':['authorization_code','refresh_token'],'response_types':['code'],'scope':'veglia:read veglia:capture veglia:summon'})
        self.assertEqual(r.status_code,201,r.text)
        return r.json()['client_id']

    def authorize(self,client,scopes='veglia:read'):
        verifier=secrets.token_urlsafe(48)
        challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        r=self.http.get(self.base+'/authorize',params={'client_id':client,'redirect_uri':'http://127.0.0.1:18999/callback',
            'response_type':'code','code_challenge':challenge,'code_challenge_method':'S256','state':'test-state','scope':scopes,'resource':self.base+'/mcp'})
        self.assertEqual(r.status_code,302,r.text)
        consent=r.headers['location']
        page=self.http.get(consent)
        self.assertEqual(page.status_code,200,page.text)
        csrf=re.search('name="csrf" value="([^"]+)"',page.text).group(1)
        bad=self.http.post(consent,data={'csrf':'wrong','password':self.keys['owner'],'scope':'veglia:read','decision':'allow'})
        self.assertEqual(bad.status_code,403)
        bad=self.http.post(consent,data={'csrf':csrf,'password':'wrong','scope':'veglia:read','decision':'allow'})
        self.assertEqual(bad.status_code,403)
        good=self.http.post(consent,data={'csrf':csrf,'password':self.keys['owner'],'scope':'veglia:read','decision':'allow'})
        self.assertEqual(good.status_code,303,good.text)
        params=parse_qs(urlparse(good.headers['location']).query)
        self.assertEqual(params['state'],['test-state'])
        return params['code'][0],verifier

    def test_oauth_pkce_refresh_replay_revocation_and_audience(self):
        meta=self.http.get(self.base+'/.well-known/oauth-authorization-server').json()
        self.assertIn('S256',meta['code_challenge_methods_supported'])
        protected=self.http.get(self.base+'/.well-known/oauth-protected-resource/mcp')
        self.assertEqual(protected.status_code,200)
        self.assertEqual(protected.json()['resource'],self.base+'/mcp')
        bad=self.http.post(self.base+'/register',json={'redirect_uris':['https://evil.example/callback'],'token_endpoint_auth_method':'none'})
        self.assertEqual(bad.status_code,400)
        client=self.register();code,verifier=self.authorize(client)
        form={'grant_type':'authorization_code','client_id':client,'code':code,'code_verifier':verifier,
            'redirect_uri':'http://127.0.0.1:18999/callback','resource':self.base+'/mcp'}
        self.assertEqual(self.http.post(self.base+'/token',data={**form,'resource':'https://wrong.example/mcp'}).status_code,400)
        self.assertEqual(self.http.post(self.base+'/token',data={**form,'code_verifier':'incorrect'}).status_code,400)
        other=self.register()
        self.assertEqual(self.http.post(self.base+'/token',data={**form,'client_id':other}).status_code,400)
        r=self.http.post(self.base+'/token',data=form)
        self.assertEqual(r.status_code,200,r.text);tokens=r.json()
        self.assertEqual(self.http.post(self.base+'/token',data=form).status_code,400)
        def access_status(token):
            return self.http.get(self.base+'/mcp',headers={'Authorization':'Bearer '+token}).status_code
        self.assertNotEqual(access_status(tokens['access_token']),401)
        refresh={'grant_type':'refresh_token','client_id':client,'refresh_token':tokens['refresh_token'],'resource':self.base+'/mcp'}
        self.assertEqual(self.http.post(self.base+'/token',data={**refresh,'scope':'veglia:read veglia:summon'}).status_code,400)
        r=self.http.post(self.base+'/token',data=refresh);self.assertEqual(r.status_code,200,r.text);new=r.json()
        self.assertEqual(access_status(tokens['access_token']),401)

        self.assertEqual(self.http.post(self.base+'/token',data=refresh).status_code,400)
        self.assertEqual(access_status(new['access_token']),401)
        code,verifier=self.authorize(client)
        r=self.http.post(self.base+'/token',data={**form,'code':code,'code_verifier':verifier});tokens=r.json()
        r=self.http.post(self.base+'/revoke',data={'client_id':client,'token':tokens['refresh_token'],'token_type_hint':'refresh_token'})
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(access_status(tokens['access_token']),401)

    def test_expired_access_token_rejected(self):
        client=self.register();code,verifier=self.authorize(client)
        response=self.http.post(self.base+'/token',data={'grant_type':'authorization_code','client_id':client,
            'code':code,'code_verifier':verifier,'redirect_uri':'http://127.0.0.1:18999/callback','resource':self.base+'/mcp'})
        self.assertEqual(response.status_code,200,response.text)
        access=response.json()['access_token']
        with sqlite3.connect(Path(self.tmp.name)/'auth.sqlite3') as db:
            db.execute("UPDATE records SET expiry=0 WHERE kind='access' AND key=?",(hashlib.sha256(access.encode()).hexdigest(),))
        db.close()
        r=self.http.get(self.base+'/mcp',headers={'Authorization':'Bearer '+access})
        self.assertEqual(r.status_code,401)


if __name__ == '__main__':
    unittest.main()
