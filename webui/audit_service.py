"""Optional bounded, read-only match auditing with per-device output folders."""
from __future__ import annotations
import io,json,re,threading,uuid,zipfile
from pathlib import Path
from types import SimpleNamespace
import device_profiles

class AuditService:
    def __init__(self, data_root):
        self.root=Path(data_root)/'match_audits'
        self.lock=threading.RLock()
        self.jobs={}

    def _key(self,key):
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}',str(key)) or key in ('.','..'):
            raise ValueError('Некорректный идентификатор устройства')
        return key

    def busy(self):
        with self.lock:return any(j['thread'].is_alive() for j in self.jobs.values())

    def status(self,key):
        key=self._key(key)
        with self.lock:
            job=self.jobs.get(key)
            if not job:return {'state':'idle','completed':0,'target':0,'error':None}
            return {name:job.get(name) for name in ('state','completed','target','error','last_result')}

    def start(self,key,base,target=10):
        key=self._key(key)
        if isinstance(target,bool) or not isinstance(target,int) or not 1<=target<=100:
            raise ValueError('Выберите от 1 до 100 матчей')
        if not re.fullmatch(r'http://127\.0\.0\.1:\d{1,5}',base):
            raise ValueError('Аудит доступен только для локальной панели')
        with self.lock:
            previous=self.jobs.get(key)
            if previous and previous['thread'].is_alive():raise ValueError('Аудит уже запущен')
            folder=self.root/key/uuid.uuid4().hex
            folder.mkdir(parents=True,exist_ok=False)
            job={'state':'starting','completed':0,'target':target,'error':None,'last_result':None,
                 'folder':folder,'stop':threading.Event()}
            thread=threading.Thread(target=self._run,args=(key,base,job),daemon=True,name=f'match-audit-{key}')
            job['thread']=thread;self.jobs[key]=job;thread.start()
        return self.status(key)

    def _run(self,key,base,job):
        lock_path=None
        try:
            from match_audit import run,acquire_lock
            lock_path=acquire_lock(key)
            def progress(done,record):
                with self.lock:job.update(completed=done,last_result=record)
            args=SimpleNamespace(panel=base,serial=key,target=job['target'],
                out=str(job['folder']/'matches.jsonl'),evidence_root=str(job['folder']/'evidence'),
                interval=2.,buffer=120,analyse_frames=60,stop_event=job['stop'],progress=progress)
            with self.lock:job['state']='running' if not job['stop'].is_set() else 'stopping'
            with device_profiles.use_profile(key):run(args,lock_path)
            with self.lock:job['state']='stopped' if job['stop'].is_set() else 'completed'
        except Exception as error:
            with self.lock:job.update(state='error',error=str(error))
        finally:
            if lock_path is not None:lock_path.unlink(missing_ok=True)

    def stop(self,key):
        key=self._key(key)
        with self.lock:
            job=self.jobs.get(key)
            if job and job['thread'].is_alive():
                job['stop'].set();job['state']='stopping'
        return self.status(key)

    def stop_all(self):
        with self.lock:
            for key in list(self.jobs):self.stop(key)

    def export(self,key):
        key=self._key(key)
        with self.lock:
            job=self.jobs.get(key)
            folder=job['folder'] if job else None
            if job and job['thread'].is_alive():raise ValueError('Остановите аудит перед скачиванием')
        if folder is None:
            device_root=self.root/key
            candidates=sorted((p for p in device_root.iterdir() if p.is_dir()),key=lambda p:p.stat().st_mtime) if device_root.is_dir() else []
            if not candidates:raise ValueError('Сначала запустите аудит')
            folder=candidates[-1]
        output=io.BytesIO()
        with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
            for path in folder.rglob('*'):
                if path.is_file() and not path.is_symlink():archive.write(path,path.relative_to(folder).as_posix())
        output.seek(0)
        return output
