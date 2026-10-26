"""설치된 제품 가상환경으로 지역 선택을 실행한다."""
from pathlib import Path
import os
import subprocess
import sys

root=Path(__file__).resolve().parents[1]
python=root/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
if not python.exists():
    print('먼저 제품 폴더에서 python setup-lab.py 로 설치하세요.',file=sys.stderr)
    raise SystemExit(2)
raise SystemExit(subprocess.call([str(python),'-m','court_auction_mcp','--export-root',str(root/'지역별'/'수집결과'),'guide',*sys.argv[1:]],cwd=root))
