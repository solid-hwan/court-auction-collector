import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('release_builder',ROOT/'tools/build_release.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)


class ReleaseTests(unittest.TestCase):
    def test_archive_allowlist_manifest_and_reproducibility(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=builder.build(Path(tmp)/'a');b=builder.build(Path(tmp)/'b')
            self.assertEqual(a['sha256'],b['sha256'])
            with zipfile.ZipFile(a['archive']) as z:
                names=z.namelist()
                self.assertFalse(any(('/.venv/' in n or '__pycache__' in n or '.sqlite' in n or '/.git/' in n or n.endswith('.env')) for n in names))
                prefix='court-auction-mcp-0.2.1/'
                manifest=json.loads(z.read(prefix+'SOURCE_MANIFEST.json'))
                for name,digest in manifest['files'].items():
                    self.assertEqual(hashlib.sha256(z.read(prefix+name)).hexdigest(),digest)
                self.assertIn(prefix+'examples/synthetic.json',names)
                self.assertIn(prefix+'LICENSE',names)

    def test_docs_links_exist_and_no_personal_runtime_paths(self):
        import re
        for path in [ROOT/'README.md',ROOT/'AGENTS.md',ROOT/'CLAUDE.md',ROOT/'NOTICE.md',*list((ROOT/'docs').glob('*.md'))]:
            text=path.read_text()
            self.assertNotIn('/home/kkhwan/',text)
            for link in re.findall(r'\]\(([^)]+)\)',text):
                if '://' not in link and not link.startswith('#'):
                    self.assertTrue((path.parent/link.split('#')[0]).exists(),(path,link))

    def test_readme_four_step_diagram(self):
        text=(ROOT/'README.md').read_text()
        diagram=text.split('```mermaid\n')[1].split('```')[0]
        self.assertEqual(diagram.count('-->'),3)
        self.assertNotIn('sequenceDiagram',text)
