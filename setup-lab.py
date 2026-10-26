"""이 제품의 .venv만 생성. 운영 MCP·전역 환경은 변경하지 않는다."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import venv

root=Path(__file__).resolve().parent
folder=root/'.venv'
use_uv=importlib.util.find_spec('ensurepip') is None and shutil.which('uv') is not None
if use_uv:
    subprocess.run(['uv','venv','--allow-existing',str(folder)],check=True)
else:
    venv.EnvBuilder(with_pip=True).create(folder)
python=folder/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
installer=['uv','pip','install','--python',str(python)] if use_uv else [str(python),'-m','pip','install']
subprocess.run(installer+['-r',str(root/'requirements.lock')],check=True)
subprocess.run(installer+['--no-build-isolation','--no-deps',str(root)],check=True)
print(f'Ready: {python} -m court_auction_mcp coverage')
