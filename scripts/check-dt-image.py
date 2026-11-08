#!/usr/bin/env python3
import json, struct
from pathlib import Path
p=Path(__file__).resolve().parents[1]/'artifacts/dt.img'
d=p.read_bytes(); magic,version,count=struct.unpack_from('<4sII',d)
assert magic==b'QCDT' and version==2 and count==15
rows=[]
for i in range(count):
 soc,board,rev,hwrev,offset,size=struct.unpack_from('<6I',d,12+24*i)
 assert offset%2048==0 and size%2048==0 and offset+size<=len(d)
 assert d[offset:offset+4]==bytes.fromhex('d00dfeed')
 actual_size=struct.unpack_from('>I',d,offset+4)[0]
 assert actual_size<=size
 rows.append(dict(soc=soc,board=hex(board),board_revision=rev,soc_revision=hwrev,offset=offset,size=size))
assert len({r['offset'] for r in rows})==5
assert {r['board_revision'] for r in rows}=={1,3,4,5,6}
print(json.dumps(dict(result='PASS',version=version,entries=count,unique_dtbs=5,bytes=len(d),table=rows),indent=2))
