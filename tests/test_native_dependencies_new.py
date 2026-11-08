#!/usr/bin/env python3
"""New targeted native-linkage/generation checks, not the prior46-test suite."""
import importlib.util,json,shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def load(name):
 s=importlib.util.spec_from_file_location(name.replace('-','_'),ROOT/'scripts'/f'{name}.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
native=load('audit-native-dependencies');extract=load('extract-stock');generate=load('generate-vendor');inputs=load('check-build-inputs')

class NativeChecks(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='a7-native-new-');self.root=Path(self.tmp.name);self.product=self.root/'product';(self.product/'system/lib').mkdir(parents=True)
  self.cc=ROOT/'sources/toolchain/bin/arm-eabi-gcc';self.contract=self.root/'contract.json'
  self.set_contract()
 def tearDown(self):self.tmp.cleanup()
 def set_contract(self,essential=None,shims=None):
  self.contract.write_text(json.dumps(dict(schema_version=1,model='SM-A700FD',firmware='A700FDXXS1CSB1',essential_files=essential or ['system/lib/libconsumer.so'],injected_shims=shims or {})))
 def dso(self,name,code,needed=None,subdir='system/lib'):
  src=self.root/(name+'.c');src.write_text(code);out=self.product/subdir/name;out.parent.mkdir(parents=True,exist_ok=True)
  cmd=[str(self.cc),'-shared','-nostdlib','-Wl,-soname,'+name,str(src),'-o',str(out)]
  if needed:cmd+=['-L'+str(self.product/'system/lib'),'-Wl,--no-as-needed','-l:'+needed]
  subprocess.run(cmd,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE);return out
 def setup_linked(self):
  self.dso('libprovider.so','int supplied(void){return 8;}')
  self.dso('libconsumer.so','extern int supplied(void); extern int optional(void) __attribute__((weak)); int use(void){return supplied()+(optional?optional():0);}',needed='libprovider.so')
 def test_needed_and_strong_symbols_resolve_weak_is_optional(self):
  self.setup_linked();r=native.audit(self.product,self.contract);self.assertTrue(r['ready_for_image_packaging']);self.assertEqual(r['elf_count'],2)
 def test_absent_needed_provider_blocks(self):
  self.setup_linked();(self.product/'system/lib/libprovider.so').unlink();r=native.audit(self.product,self.contract);self.assertFalse(r['ready_for_image_packaging']);self.assertEqual(r['missing_needed'][0]['needed'],'libprovider.so')
 def test_strong_symbol_without_needed_provider_blocks(self):
  self.dso('libconsumer.so','extern int notsupplied(void);int use(void){return notsupplied();}')
  r=native.audit(self.product,self.contract);self.assertIn('notsupplied',[x['symbol'] for x in r['unresolved_strong_symbols']])
 def test_explicit_injected_shim_resolves(self):
  self.dso('libconsumer.so','extern int oldapi(void);int use(void){return oldapi();}');self.dso('libshim.so','int oldapi(void){return 1;}')
  self.set_contract(shims={'system/lib/libconsumer.so':['libshim.so']});self.assertTrue(native.audit(self.product,self.contract)['ready_for_image_packaging'])
 def test_different_soname_providers_are_not_guessed(self):
  self.setup_linked();self.dso('libprovider.so','int supplied(void){return 22;}',subdir='system/vendor/lib');r=native.audit(self.product,self.contract);self.assertFalse(r['ready_for_image_packaging']);self.assertTrue(r['ambiguous_providers'])
 def test_report_rejects_added_elf_provider(self):
  self.setup_linked();r=native.audit(self.product,self.contract);report=self.root/'report.json';report.write_text(json.dumps(r));native.validate_report(self.product,report,self.contract)
  self.dso('libextra.so','int extra(void){return 0;}')
  with self.assertRaisesRegex(ValueError,'output changed'):native.validate_report(self.product,report,self.contract)
 def test_report_rejects_modified_elf_hash(self):
  self.setup_linked();report=self.root/'report.json';report.write_text(json.dumps(native.audit(self.product,self.contract)))
  self.dso('libprovider.so','int supplied(void){return 27;}')
  with self.assertRaisesRegex(ValueError,'stale'):native.validate_report(self.product,report,self.contract)
 def test_missing_essential_path_blocks(self):
  self.setup_linked();self.set_contract(essential=['system/lib/missing.so']);self.assertFalse(native.audit(self.product,self.contract)['ready_for_image_packaging'])
 def test_versioned_symbol_matching(self):
  self.assertTrue(native.symbol_matches('foo@LIBC',{'foo@LIBC'}));self.assertTrue(native.symbol_matches('foo',{'foo@@LIBC'}));self.assertFalse(native.symbol_matches('foo',{'foo@OLD'}));self.assertFalse(native.symbol_matches('foo@OTHER',{'foo@LIBC'}))
 def vendor_fixture(self):
  self.setup_linked();system=self.root/'stock';(system/'lib').mkdir(parents=True)
  for p in (self.product/'system/lib').glob('*.so'):shutil.copyfile(p,system/'lib'/p.name)
  (system/'build.prop').write_text('ro.product.model=SM-A700FD\nro.product.manufacturer=samsung\nro.build.PDA=A700FDXXS1CSB1\n')
  listing=self.root/'files.txt';listing.write_text('lib/libprovider.so\nlib/libconsumer.so\n');staging=self.root/'stage';extract.extract(system,staging,listing)
  plan=json.loads((staging/'vendor-review.candidate.json').read_text());plan['reviewed']=True
  for row in plan['files']:
   row.update(action='module',module='provider_compat' if row['source'].endswith('libprovider.so') else 'libconsumer')
  planpath=self.root/'review.json';planpath.write_text(json.dumps(plan));vendor=self.root/'tree/vendor/samsung/a7lte';generate.generate(staging,planpath,vendor)
  return staging,planpath,vendor
 def test_prebuilt_dependency_uses_selected_module_alias(self):
  _,_,vendor=self.vendor_fixture();mk=(vendor/'Android.mk').read_text();self.assertIn('LOCAL_SHARED_LIBRARIES := provider_compat',mk)
 def test_generated_makefile_tamper_blocks_packaging_inputs(self):
  _,_,vendor=self.vendor_fixture();tree=self.root/'tree';mk=tree/'device/samsung/a7lte/partition-sizes.mk';mk.parent.mkdir(parents=True);mk.write_text('verified fixture layout\n');layout=self.root/'layout.json';layout.write_text(json.dumps(dict(layout_format=1,layout_verified=True,model='SM-A700FD',firmware='A700FDXXS1CSB1',makefile=dict(sha256=inputs.digest(mk)))))
  self.assertEqual(inputs.check(tree,layout),2);(vendor/'Android.mk').write_text('# changed module paths')
  with self.assertRaisesRegex(AssertionError,'makefile changed'):inputs.check(tree,layout)
 def test_source_owned_stock_libril_cannot_replace_pie_module(self):
  staging,planpath,_=self.vendor_fixture();inv=json.loads((staging/'inventory.json').read_text());row=inv['files'][0];source=row['source'];row['source']='lib/libril.so';(staging/'proprietary/lib/libril.so').write_bytes((staging/'proprietary'/source).read_bytes());(staging/'inventory.json').write_text(json.dumps(inv));plan=json.loads(planpath.read_text());plan['files'][0]['source']='lib/libril.so';planpath.write_text(json.dumps(plan))
  with self.assertRaisesRegex(ValueError,'source-owned'):generate.generate(staging,planpath,self.root/'other-vendor')

if __name__=='__main__':unittest.main(verbosity=2)
