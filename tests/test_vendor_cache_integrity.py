import importlib.util,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def module(name,path):
 s=importlib.util.spec_from_file_location(name,ROOT/path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
prep=module('cache_prep','ci/prepare-csb1-vendor.py');check=module('cache_check','ci/verify-csb1-vendor-cache.py')
class CacheIntegrity(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();b=Path(self.tmp.name);system=b/'stock/system';system.mkdir(parents=True)
  (system/'build.prop').write_text('ro.product.model=SM-A700FD\nro.product.manufacturer=samsung\nro.build.PDA=A700FDXXS1CSB1\nro.build.version.incremental=A700FDXXS1CSB1\n')
  (system/'etc').mkdir();(system/'etc/fixture.conf').write_text('synthetic fixture only\n');lst=b/'list';lst.write_text('etc/fixture.conf\n');tree=b/'tree';prep.prepare(system,tree,b/'stage',False,lst)
  self.vendor=tree/'vendor/samsung/a7lte';self.contract=ROOT/'scripts/native-contracts.json'
 def tearDown(self):self.tmp.cleanup()
 def test_unmodified_cache(self):self.assertEqual(check.validate(self.vendor,self.contract),1)
 def test_changed_blob(self):
  (self.vendor/'proprietary/etc/fixture.conf').write_text('changed')
  with self.assertRaisesRegex(ValueError,'blob changed'):check.validate(self.vendor,self.contract)
 def test_changed_recipe(self):
  (self.vendor/'Android.mk').write_text('changed')
  with self.assertRaisesRegex(ValueError,'recipe changed'):check.validate(self.vendor,self.contract)
 def test_changed_review(self):
  (self.vendor/'vendor-review.json').write_text('{}')
  with self.assertRaisesRegex(ValueError,'metadata changed'):check.validate(self.vendor,self.contract)
if __name__=='__main__':unittest.main()
