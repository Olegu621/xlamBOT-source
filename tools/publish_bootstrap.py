"""Publish an immutable signed bootstrap descriptor; never modify script trust."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
from cryptography.hazmat.primitives import serialization
from source_sync import git

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')

def build_archive(exe, source, target):
    payloads={'xlamBOT.exe':Path(exe).read_bytes()}
    for directory in ['static','templates']:
        for path in sorted((Path(source)/directory).rglob('*')):
            if path.is_file() and not path.is_symlink():
                payloads['_internal/'+path.relative_to(source).as_posix()]=path.read_bytes()
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,data in sorted(payloads.items()):
            info=zipfile.ZipInfo(name,date_time=(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(info,data)
    return {name:hashlib.sha256(data).hexdigest() for name,data in payloads.items()}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe',type=Path,required=True)
    parser.add_argument('--key',type=Path,required=True)
    parser.add_argument('--revision',type=int,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--source-repo',type=Path,default=Path(__file__).resolve().parents[1])
    args=parser.parse_args()
    commit=git(args.source_repo,'rev-parse','HEAD')
    if git(args.source_repo,'status','--porcelain') or git(args.source_repo,'branch','--show-current')!='main':
        raise RuntimeError('Merge and clean sources before publishing bootstrap')
    if git(args.source_repo,'rev-parse',f'bot-revision-{args.revision}^{{commit}}')!=commit:
        raise RuntimeError('Bootstrap must correspond to the published script revision')
    if args.output.exists():raise RuntimeError('Do not overwrite an existing bootstrap release')
    data=args.exe.read_bytes()
    if not data.startswith(b'MZ') or not 0<len(data)<=64*1024*1024:raise ValueError('Invalid bootstrap executable')
    args.output.mkdir(parents=True)
    files=build_archive(args.exe,args.source_repo,args.output/'bootstrap.zip')
    data=(args.output/'bootstrap.zip').read_bytes()
    manifest={'repository':'Olegu621/xlamBOT','version':'0.8.20','runtime':'0.8.18','revision':args.revision,
              'source_commit':commit,'file':'bootstrap.zip','bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'files':files}
    key=serialization.load_pem_private_key(args.key.read_bytes(),password=None)
    envelope={'manifest':manifest,'signature':key.sign(canonical(manifest)).hex()}
    (args.output/'bootstrap.json').write_bytes(canonical(envelope))
    print(json.dumps({'revision':args.revision,'bytes':len(data),'sha256':manifest['sha256']}))

if __name__=='__main__':main()
