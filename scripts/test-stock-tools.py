#!/usr/bin/env python3
"""Real conversion smoke test on synthetic data only; never mounts or flashes."""
import hashlib,json,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
TOOLS=ROOT/'host/stock-tools/bin'


def run(name,*args):
    proc=subprocess.run([str(TOOLS/name),*map(str,args)],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    return proc.stdout


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    with tempfile.TemporaryDirectory(prefix='a7lte-synthetic-stock-') as d:
        base=Path(d); tree=base/'tree';tree.mkdir()
        payload=b'ro.product.model=SM-A700FD\nro.build.PDA=A700FDXXS1CSB1\n# SYNTHETIC FIXTURE ONLY\n'
        (tree/'build.prop').write_bytes(payload)
        raw=base/'system.raw'
        with raw.open('wb') as f:f.truncate(16*1024**2)
        run('mkfs.ext4','-F','-q','-d',tree,raw)
        run('img2simg',raw,base/'system.sparse')
        run('simg2img',base/'system.sparse',base/'system.roundtrip')
        assert sha(raw)==sha(base/'system.roundtrip'),'Sparse roundtrip bytes differ'
        run('lz4','-l','-f',base/'system.sparse',base/'system.sparse.lz4')
        run('lz4','-d','-f',base/'system.sparse.lz4',base/'system.decompressed')
        assert sha(base/'system.sparse')==sha(base/'system.decompressed'),'LZ4 legacy roundtrip differs'
        out=base/'extracted';out.mkdir()
        before=sha(raw)
        run('debugfs','-R',f'rdump / {out}',raw)
        assert (out/'build.prop').read_bytes()==payload,'debugfs rdump content differs'
        assert sha(raw)==before,'Read-only debugfs changed filesystem'
        print(json.dumps({'result':'PASS','fixture':'synthetic only, not Samsung firmware','raw_ext4_bytes':raw.stat().st_size,'sparse_bytes':(base/'system.sparse').stat().st_size,'lz4_legacy_bytes':(base/'system.sparse.lz4').stat().st_size,'tests':['mkfs.ext4 directory population','img2simg→simg2img byte-identical roundtrip','LZ4 legacy→decompress byte-identical roundtrip','debugfs read-only rdump content','original filesystem SHA256 unchanged'],'raw_sha256':before},indent=2))


if __name__=='__main__':main()
