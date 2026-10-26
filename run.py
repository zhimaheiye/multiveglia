"""Launch one component or the full local stack."""
import argparse
import os
from pathlib import Path
import runpy
import subprocess
import sys
import time


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['all','core','mcp','sensor','stdio'])
    args=parser.parse_args()
    root=Path(__file__).resolve().parent
    server=root/'server'
    if not (server/'.env').exists() and not os.environ.get('VEGLIA_TOKEN'):
        raise SystemExit('Run setup.py (or Setup.cmd) first.')
    os.chdir(server)
    sys.path.insert(0,str(server))
    scripts={'core':'veglia_server.py','mcp':'veglia_mcp_http.py','sensor':'device_sensor.py','stdio':'veglia_mcp.py'}
    if args.mode!='all':
        if args.mode=='stdio':os.environ.pop('VEGLIA_HTTP_MODE',None)
        runpy.run_path(str(server/scripts[args.mode]),run_name='__main__')
        return
    children=[];logs=[]
    logdir=server/'logs';logdir.mkdir(exist_ok=True)
    try:
        for mode in ['core','mcp','sensor']:
            log=open(logdir/(mode+'.log'),'a',encoding='utf-8');logs.append(log)
            flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
            child=subprocess.Popen([sys.executable,str(root/'run.py'),mode],stdout=log,stderr=log,creationflags=flags)
            children.append(child)
        print('MultiVeglia is running. Press Ctrl+C to stop. Logs: server/logs')
        while all(p.poll() is None for p in children):time.sleep(1)
        raise SystemExit('A component exited; inspect server/logs. The stack is stopping.')
    except KeyboardInterrupt:
        print('Stopping MultiVeglia...')
    finally:
        for p in children:
            if p.poll() is None:p.terminate()
        for p in children:
            try:p.wait(timeout=10)
            except subprocess.TimeoutExpired:p.kill();p.wait()
        for log in logs:log.close()


if __name__=='__main__':main()
