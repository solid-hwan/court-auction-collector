"""소스·가상 예제만 선별하여 재현 가능한 ZIP과 SHA-256을 만든다."""
import argparse
import hashlib
import json
from pathlib import Path
import tomllib
import zipfile

ROOT=Path(__file__).resolve().parents[1]
TOP=('README.md','AGENTS.md','CLAUDE.md','CONTRIBUTING.md','LICENSE','NOTICE.md','CHANGELOG.md','pyproject.toml','requirements.lock','setup-lab.py','.gitignore')
PATTERNS=('src/**/*.py','src/**/*.json','tests/*.py','examples/*.py','examples/*.json','examples/*.md','docs/*.md','docs/*.json','tools/*.py','.github/workflows/*.yml')


def selected_files():
    paths={ROOT/p for p in TOP}
    for pattern in PATTERNS:
        paths.update(ROOT.glob(pattern))
    return sorted(p for p in paths if p.is_file() and '__pycache__' not in p.parts)


def build(destination):
    version=tomllib.loads((ROOT/'pyproject.toml').read_text())['project']['version']
    prefix='court-auction-mcp-'+version
    destination=Path(destination); destination.mkdir(parents=True,exist_ok=True)
    archive=destination/(prefix+'.zip')
    if archive.exists():
        raise SystemExit('기존 ZIP을 덮어쓰지 않습니다. 새 출력 폴더를 지정하세요.')
    selected=selected_files()
    manifest={'version':version,'files':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in selected},'data':'synthetic examples only; no live DB, cookies or responses'}
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as bundle:
        for name,content in [(str(p.relative_to(ROOT)),p.read_bytes()) for p in selected]+[('SOURCE_MANIFEST.json',(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode())]:
            info=zipfile.ZipInfo(prefix+'/'+name,date_time=(2026,10,26,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED; info.external_attr=0o644<<16
            bundle.writestr(info,content)
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    (destination/(prefix+'.sha256')).write_text(digest+'  '+archive.name+'\n')
    return {'archive':str(archive),'sha256':digest,'files':len(selected)+1}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True)
    print(json.dumps(build(p.parse_args().output),ensure_ascii=False))
