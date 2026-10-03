"""Backend regressions in separate hard-60-second batches, including PostgreSQL schemas."""
import json
import os
import subprocess
from pathlib import Path
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'docs/reviews/2026-10-03-core-closing'
BATCH_FILES = 6
files = sorted(p for p in (ROOT / 'backend/tests').rglob('test_*.py')
               if 'paperless' not in p.parts and not p.name.startswith('test_wps'))
env = dict(os.environ, TEST_DATABASE_URL=dotenv_values(ROOT / '.env')['DATABASE_URL'])
results = []
for index in range(0, len(files), BATCH_FILES):
    batch = files[index:index + BATCH_FILES]
    args = [str(ROOT / '.venv/bin/python'), '-m', 'pytest', '--timeout=60', '-q', *map(str, batch)]
    name = f'backend-batch-{index // BATCH_FILES + 1:02d}.txt'
    try:
        result = subprocess.run(args, cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=60)
        output, code = result.stdout, result.returncode
    except subprocess.TimeoutExpired as error:
        output, code = str(error.stdout or '') + '\nHARD BATCH TIMEOUT 60s', 124
    (OUT / name).write_text(output)
    results.append(dict(log=name, files=[str(p.relative_to(ROOT)) for p in batch], exit_code=code))
    print(name, code, output.splitlines()[-1] if output else '', flush=True)
(OUT / 'backend-batches.json').write_text(json.dumps(results, indent=2))
raise SystemExit(1 if any(r['exit_code'] for r in results) else 0)
