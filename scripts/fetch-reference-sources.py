#!/usr/bin/env python3
"""Restore pinned reference checkouts needed to regenerate the saved overlay."""
import argparse,json,subprocess
from pathlib import Path
r=Path(__file__).resolve().parents[1]; rows=json.loads((r/'sources.lock.json').read_text()); byname={Path(x['path']).name:x for x in rows}
p=argparse.ArgumentParser(description=__doc__); p.add_argument('--name',action='append',choices=sorted(byname)); a=p.parse_args()
for name in a.name or ['a7lte','common']:
    row=byname[name]; d=r/row['path']
    if d.exists():
        rev=subprocess.check_output(['git','-C',str(d),'rev-parse','HEAD'],text=True).strip()
        if rev!=row['revision']: p.error(f'{d} exists at a different revision; preserving it')
        print(f'{name}: pinned checkout already present'); continue
    d.mkdir(parents=True)
    subprocess.run(['git','init','-q',str(d)],check=True)
    subprocess.run(['git','-C',str(d),'remote','add','origin',row['remote']],check=True)
    subprocess.run(['git','-C',str(d),'fetch','--depth=1','origin',row['revision']],check=True)
    subprocess.run(['git','-C',str(d),'checkout','--detach','FETCH_HEAD'],check=True)
