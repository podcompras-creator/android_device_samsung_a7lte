#!/usr/bin/env python3
"""Normalize `repo manifest -r` for standalone, immutable replay."""
import argparse, re, xml.etree.ElementTree as E
p=argparse.ArgumentParser(); p.add_argument('input'); p.add_argument('output'); a=p.parse_args()
t=E.parse(a.input); r=t.getroot()
for x in r.findall('project'):
    if not re.fullmatch('[0-9a-f]{40}',x.get('revision','')): p.error('input must be fully resolved with repo manifest -r: '+x.get('name',''))
for x in r.findall('remote'):
    if x.get('name')=='github' and x.get('fetch')=='..': x.set('fetch','https://github.com')
    if not (x.get('fetch','').startswith(('https://','ssh://','git@'))): p.error('relative remote cannot be replayed: '+str(x.attrib))
E.indent(t); t.write(a.output,encoding='utf-8',xml_declaration=True)
