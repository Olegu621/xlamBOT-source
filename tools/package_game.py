"""Publish only original Supercell APKs after Android signature verification."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import zipfile
from cryptography.hazmat.primitives import serialization

CERT='731a29e80b7ca89c7e9b39d381821ee8dccd1b0456782f788650945e7d60d8d3'


def digest(path):
    value=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):value.update(block)
    return value.hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('input','output','key','java','apksigner','aapt'):p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args()
    if args.output.exists():raise ValueError('Do not overwrite a published game version')
    paths=sorted(args.input.glob('*.apk'))
    if not paths or not (args.input/'base.apk').is_file():raise ValueError('Missing base APK')
    version=None;files={}
    for path in paths:
        if not re.fullmatch(r'(base|split_[a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)*)\.apk',path.name) or path.is_symlink():raise ValueError('Invalid APK inventory')
        certs=subprocess.check_output([str(args.java),'-jar',str(args.apksigner),'verify','--print-certs',str(path)],text=True)
        fingerprints=re.findall(r'^Signer #\d+ certificate SHA-256 digest: ([0-9a-f]+)$',certs,re.M)
        if fingerprints!=[CERT]:raise ValueError('Not an original Supercell APK')
        badging=subprocess.check_output([str(args.aapt),'dump','badging',str(path)],text=True,encoding='utf-8')
        match=re.search(r"package: name='com.supercell.brawlstars' versionCode='(\d+)' versionName='([^']*)'",badging)
        if not match:raise ValueError('Wrong package')
        if version and version[0] != match[1]:raise ValueError('Split version mismatch')
        if path.name=='base.apk':
            if not match[2]:raise ValueError('Missing game version')
            version=match.groups()
        files[path.name]=digest(path)
    args.output.mkdir(parents=True)
    archive=args.output/'brawlstars.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as zipped:
        for path in paths:zipped.write(path,path.name)
    repo='Olegu621/xlamBOT-LDPlayer'
    m={'repository':repo,'package_name':'com.supercell.brawlstars','version_code':int(version[0]),'version_name':version[1],
       'certificate':CERT,'files':files,'archive':{'url':f'https://github.com/{repo}/releases/download/game-{version[0]}/brawlstars.zip',
       'size':archive.stat().st_size,'sha256':digest(archive)}}
    key=serialization.load_pem_private_key(args.key.read_bytes(),password=None)
    canonical=json.dumps(m,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
    (args.output/'latest-game.json').write_text(json.dumps({'manifest':m,'signature':key.sign(canonical).hex()},indent=2),'utf-8')
    print('Verified original Supercell APKs:',version,len(files),archive.stat().st_size)


if __name__=='__main__':main()
