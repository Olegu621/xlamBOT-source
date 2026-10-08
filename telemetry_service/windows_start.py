"""Start the local receiver at sign-in; owned child processes share a kill job."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--home',type=Path,required=True)
    args=parser.parse_args()
    import win32api
    import win32event
    import win32job
    mutex=win32event.CreateMutex(None,False,'Local\\xlamBOTErrorReceiverLauncher')
    if win32api.GetLastError()==183:
        return
    args.home.mkdir(parents=True,exist_ok=True)
    status=args.home/'host-status.json'
    def save(state):
        temp=status.with_suffix('.tmp')
        temp.write_text(json.dumps({'state':state,'setup':'http://127.0.0.1:8110/'}),encoding='utf-8')
        temp.replace(status)
    job=win32job.CreateJobObject(None,'')
    info=win32job.QueryInformationJobObject(job,win32job.JobObjectExtendedLimitInformation)
    info['BasicLimitInformation']['LimitFlags']|=win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    win32job.SetInformationJobObject(job,win32job.JobObjectExtendedLimitInformation,info)
    host=None
    try:
        host=subprocess.Popen([sys.executable,'-m','telemetry_service.windows_host','--home',str(args.home)],
            creationflags=subprocess.CREATE_NO_WINDOW,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        handle=win32api.OpenProcess(0x0100|0x0001,False,host.pid)
        try:
            win32job.AssignProcessToJobObject(job,handle)
        finally:
            win32api.CloseHandle(handle)
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
            save('receiver_failed')
            return
        save('local_ready')
        host.wait()
        save('receiver_stopped')
    except Exception:
        save('startup_failed')
    finally:
        win32api.CloseHandle(job)
        if host and host.poll() is None:
            host.terminate()
        win32api.CloseHandle(mutex)


if __name__=='__main__':
    main()
