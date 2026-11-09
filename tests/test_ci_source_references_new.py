#!/usr/bin/env python3
"""New analysis-only reference checks; no earlier suites or stock code executed."""
import importlib.util,json,shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(name):
 s=importlib.util.spec_from_file_location(name.replace('-','_'),ROOT/'ci'/f'{name}.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
ci=load('prepare-csb1-vendor');cache=load('verify-csb1-vendor-cache')
class SourceReferences(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='a7-new-refs-elf-');d=Path(cls.tmp.name);(d/'test.c').write_text('int synthetic_reference(void){return 7;}')
  cls.elf=d/'fixture.so';subprocess.run([str(ROOT/'sources/toolchain/bin/arm-eabi-gcc'),'-shared','-nostdlib',str(d/'test.c'),'-o',str(cls.elf)],check=True)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='a7-source-refs-');self.root=Path(self.tmp.name);self.system=self.root/'system';self.system.mkdir();self.tree=self.root/'tree';self.stage=self.root/'staging';self.vendor=self.tree/'vendor/samsung/a7lte'
  (self.system/'build.prop').write_text('ro.product.model=SM-A700FD\nro.product.manufacturer=samsung\nro.build.PDA=A700FDXXS1CSB1\nro.build.version.incremental=A700FDXXS1CSB1\n')
  for name in ['lib/hw/camera.msm8916.so','lib/libgps.utils.so','lib/libprotobuf-cpp-full.so']:
   target=self.system/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(self.elf,target)
  self.list=self.root/'list';self.list.write_text('lib/hw/camera.msm8916.so:lib/hw/camera.vendor.msm8916.so\n')
 def tearDown(self):self.tmp.cleanup()
 def prepare(self):
  return ci.prepare(self.system,self.tree,self.stage,False,self.list)
 def report(self):return json.loads((self.vendor/'vendor-audit.json').read_text())
 def rewrite(self,r):(self.vendor/'vendor-audit.json').write_text(json.dumps(r))
 def validate(self):return cache.validate(self.vendor,ROOT/'scripts/native-contracts.json')
 def test_preserved_bytes_provenance_and_no_image_rules(self):
  originals={p:ci.digest(self.system/p) for p in ci.SOURCE_REFERENCE_PATHS};r=self.prepare();self.assertEqual(r['selected_files'],1);refs=r['source_reference_files'];self.assertEqual(len(refs),2)
  for entry in refs:
   self.assertEqual(entry['status'],'present');self.assertEqual(entry['sha256'],originals[entry['source']]);self.assertEqual(ci.digest(self.vendor/entry['path']),originals[entry['source']]);self.assertEqual(ci.digest(self.system/entry['source']),originals[entry['source']]);self.assertFalse(entry['installed_into_image']);self.assertEqual(entry['provenance']['pda'],'A700FDXXS1CSB1')
  for recipe in ('Android.mk','a7lte-vendor.mk'):
   text=(self.vendor/recipe).read_text();self.assertNotIn('stock-reference',text);self.assertNotIn('LOCAL_MODULE := libgps.utils',text);self.assertNotIn('LOCAL_MODULE := libprotobuf-cpp-full',text)
  self.assertEqual(self.validate(),1)
 def test_missing_reference_is_recorded_and_cache_valid(self):
  (self.system/'lib/libprotobuf-cpp-full.so').unlink();self.prepare();row=next(x for x in self.report()['source_reference_files'] if x['source'].endswith('libprotobuf-cpp-full.so'));self.assertEqual(row['status'],'missing');self.assertNotIn('sha256',row);self.assertFalse((self.vendor/row['path']).exists());self.assertEqual(self.validate(),1)
 def test_external_source_reference_link_not_followed(self):
  p=self.system/'lib/libgps.utils.so';p.unlink();outside=self.root/'outside.so';outside.write_bytes(b'not stock');p.symlink_to(outside);self.prepare();row=self.report()['source_reference_files'][0];self.assertEqual(row['status'],'unresolved_external_symlink');self.assertFalse((self.vendor/row['path']).exists());self.assertEqual(self.validate(),1)
 def test_cached_reference_byte_change_rejected(self):
  self.prepare();p=self.vendor/'stock-reference/lib/libgps.utils.so';p.unlink();p.write_bytes(b'changed bytes')
  with self.assertRaisesRegex(ValueError,'reference bytes changed'):self.validate()
 def test_cached_reference_path_traversal_rejected(self):
  self.prepare();r=self.report();r['source_reference_files'][0]['path']='../outside';self.rewrite(r)
  with self.assertRaisesRegex(ValueError,'unsafe source-reference path'):self.validate()
 def test_old_cache_without_optional_reference_field_valid(self):
  self.prepare();r=self.report();r.pop('source_reference_files');self.rewrite(r);shutil.rmtree(self.vendor/'stock-reference');self.assertEqual(self.validate(),1)
 def test_cached_reference_symlink_escape_rejected(self):
  self.prepare();p=self.vendor/'stock-reference/lib/libgps.utils.so';outside=self.root/'outside';outside.write_bytes(p.read_bytes());p.unlink();p.symlink_to(outside)
  with self.assertRaisesRegex(ValueError,'path escapes vendor'):self.validate()
 def test_cached_reference_identity_change_rejected(self):
  self.prepare();r=self.report();r['source_reference_files'][0]['provenance']['model']='SM-A700F';self.rewrite(r)
  with self.assertRaisesRegex(ValueError,'identity mismatch'):self.validate()
if __name__=='__main__':unittest.main(verbosity=2)
