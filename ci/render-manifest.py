#!/usr/bin/env python3
import argparse,re,xml.etree.ElementTree as E
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--repository',required=True);p.add_argument('--revision',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',a.repository):p.error('Expected OWNER/REPOSITORY')
if not re.fullmatch(r'[0-9a-f]{40}',a.revision):p.error('Expected a full published commit SHA')
t=E.parse(Path(__file__).resolve().parents[1]/'local_manifests.xml')
for x in t.getroot().findall('project'):
 if x.get('name')=='__PORT_REPOSITORY__':x.set('name',a.repository);x.set('revision',a.revision)
a.output.parent.mkdir(parents=True,exist_ok=True);E.indent(t);t.write(a.output,encoding='utf-8',xml_declaration=True)
