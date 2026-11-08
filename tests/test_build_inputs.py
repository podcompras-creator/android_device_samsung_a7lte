import hashlib,importlib.util,json,tempfile,unittest
from pathlib import Path
s=importlib.util.spec_from_file_location('checks',Path(__file__).resolve().parents[1]/'scripts/check-build-inputs.py'); c=importlib.util.module_from_spec(s); s.loader.exec_module(c)
class BuildInputs(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory(); self.root=Path(self.t.name); self.tree=self.root/'android'; self.vendor=self.tree/'vendor/samsung/a7lte'; self.vendor.mkdir(parents=True)
  self.blob=self.vendor/'proprietary/lib/test.so'; self.blob.parent.mkdir(parents=True); self.blob.write_bytes(b'fixture only')
  self.mk=self.tree/'device/samsung/a7lte/partition-sizes.mk'; self.mk.parent.mkdir(parents=True); self.mk.write_text('BOARD_BOOTIMAGE_PARTITION_SIZE := 13631488\n')
  self.layout=self.root/'layout.json'; self.layout.write_text(json.dumps(dict(layout_format=1,layout_verified=True,model='SM-A700FD',firmware='A700FDXXS1CSB1',makefile=dict(sha256=c.digest(self.mk)))))
  for name,obj in {'vendor-audit.json':dict(model='SM-A700FD',firmware='A700FDXXS1CSB1',ready_for_diagnostic_build=True,selected_files=1),'vendor-review.json':dict(reviewed=True,firmware='A700FDXXS1CSB1',files=[dict(source='lib/test.so',action='module')]),'stock-inventory.json':dict(firmware='A700FDXXS1CSB1',files=[dict(source='lib/test.so',sha256=c.digest(self.blob))])}.items(): (self.vendor/name).write_text(json.dumps(obj))
 def tearDown(self): self.t.cleanup()
 def test_unchanged(self): self.assertEqual(c.check(self.tree,self.layout),1)
 def test_changed_blob(self):
  self.blob.write_bytes(b'changed')
  with self.assertRaises(AssertionError): c.check(self.tree,self.layout)
 def test_changed_layout(self):
  self.mk.write_text('wrong')
  with self.assertRaises(AssertionError): c.check(self.tree,self.layout)
 def test_escaping_blob(self):
  outside=self.root/'other'; outside.write_bytes(self.blob.read_bytes()); self.blob.unlink(); self.blob.symlink_to(outside)
  with self.assertRaises(AssertionError): c.check(self.tree,self.layout)
if __name__=='__main__': unittest.main()
