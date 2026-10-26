"""Create private local configuration without overwriting an existing setup."""
import os
from pathlib import Path
import secrets
import socket


def main():
    root=Path(__file__).resolve().parent
    target=root/'server/.env'
    if target.exists():
        raise SystemExit('server/.env already exists; it was not modified.')
    text=(root/'server/.env.example').read_text(encoding='utf-8')
    keys=['VEGLIA_TOKEN','VEGLIA_PHONE_TOKEN','VEGLIA_SENSOR_TOKEN','VEGLIA_MCP_TOKEN','VEGLIA_MCP_READ_TOKEN','VEGLIA_OAUTH_PASSWORD']
    values={key:secrets.token_urlsafe(32) for key in keys}
    for key,value in values.items():text=text.replace(key+'=\n',key+'='+value+'\n',1)
    target.write_text(text,encoding='utf-8')
    try:target.chmod(0o600)
    except OSError:pass
    private=root/'server/data';private.mkdir(exist_ok=True)
    info=private/'setup-credentials.txt'
    info.write_text('PRIVATE: do not upload or share this file.\n\n'+
        'Phone Token: '+values['VEGLIA_PHONE_TOKEN']+'\n'+
        'Sensor Token: '+values['VEGLIA_SENSOR_TOKEN']+'\n'+
        'MCP full access Token: '+values['VEGLIA_MCP_TOKEN']+'\n'+
        'MCP read-only Token: '+values['VEGLIA_MCP_READ_TOKEN']+'\n'+
        'OAuth consent password: '+values['VEGLIA_OAUTH_PASSWORD']+'\n\n'+
        'Phone server URL: http://YOUR-COMPUTER-LAN-IP:8513\n'+
        'MCP URL: http://127.0.0.1:8514/mcp\n'+
        'Set VEGLIA_PUBLIC_URL to your HTTPS origin before enabling a tunnel.\n',encoding='utf-8')
    try:info.chmod(0o600)
    except OSError:pass
    if os.name=='nt':
        import subprocess
        user=subprocess.check_output(['whoami','/user','/fo','csv','/nh'],text=True).strip().split(',')[-1].strip('"')
        for path in [target,private]:
            grants=[f'*{user}:(OI)(CI)F','*S-1-5-18:(OI)(CI)F'] if path.is_dir() else [f'*{user}:F','*S-1-5-18:F']
            subprocess.run(['icacls',str(path),'/inheritance:r','/grant:r',*grants],check=True,stdout=subprocess.DEVNULL)
    print('Created configuration. Private credentials are in:',info)


if __name__=='__main__':main()
