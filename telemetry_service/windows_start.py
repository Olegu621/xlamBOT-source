"""Single-user background launcher. Quick Tunnel is a deployment test only."""
import argparse
from collections import deque
import json
from pathlib import Path
import re
import subprocess
import sys
import threading
import time


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--home',type=Path,required=True)
    args=parser.parse_args()
    import win32api
    import win32event
    mutex=win32event.CreateMutex(None,False,'Local\\xlamBOTErrorReceiverLauncher')
    if win32api.GetLastError()==183:
        return
    args.home.mkdir(parents=True,exist_ok=True)
    status=args.home/'host-status.json'
    status_lock=threading.Lock()
    def save(data):
        with status_lock:
            temp=status.with_suffix('.tmp')
            temp.write_text(json.dumps(data),encoding='utf-8')
            temp.replace(status)
    flags=subprocess.CREATE_NO_WINDOW
    host=None
    tunnel=None
    try:
        host=subprocess.Popen([sys.executable,'-m','telemetry_service.windows_host','--home',str(args.home)],
                              creationflags=flags,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        import requests
        ready=False
        for _ in range(60):
            if host.poll() is not None:
                break
            try:
                ready=requests.get('http://127.0.0.1:8088/health',timeout=1).json().get('ok') is True
            except Exception:
                pass
            if ready:
                break
            time.sleep(.5)
        if not ready:
            save({'state':'receiver_failed'})
            return
        save({'state':'local_ready','setup':'http://127.0.0.1:8110/'})
        connector=args.home/'cloudflared.exe'
        tunnel=subprocess.Popen([str(connector),'tunnel','--no-autoupdate','--url','http://127.0.0.1:8088',
                                 '--protocol','http2'],creationflags=flags,
                                 stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True,encoding='utf-8',errors='replace')
        history=deque(maxlen=30)
        connected=threading.Event()
        def read_connector():
            for line in tunnel.stderr:
                history.append(line[:1000])
                (args.home/'connector-last-lines.txt').write_text(''.join(history),encoding='utf-8')
                found=re.search(r'https://[a-z0-9-]+\.trycloudflare\.com',line)
                if found:
                    save({'state':'tunnel_started','setup':'http://127.0.0.1:8110/',
                          'public_url':found.group(0),'temporary':True})
                if 'Registered tunnel connection' in line:
                    connected.set()
        threading.Thread(target=read_connector,daemon=True).start()
        deadline=time.monotonic()+45
        failed=False
        while host.poll() is None:
            if not failed and (tunnel.poll() is not None or (not connected.is_set() and time.monotonic()>deadline)):
                if tunnel.poll() is None:
                    tunnel.terminate()
                save({'state':'local_only','setup':'http://127.0.0.1:8110/',
                      'reason':'tunnel_unavailable'})
                failed=True
            time.sleep(1)
        save({'state':'process_stopped','receiver_exit':host.poll(),'tunnel_exit':tunnel.poll()})
        (args.home/'connector-last-lines.txt').write_text(''.join(history),encoding='utf-8')
    except Exception:
        save({'state':'startup_failed'})
    finally:
        for child in (tunnel,host):
            if child and child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    child.kill()
        win32api.CloseHandle(mutex)


if __name__=='__main__':
    main()
