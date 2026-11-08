#!/usr/bin/env python3
"""CI adapter synthetic fixtures only; never treated as actual CSB1 evidence."""
import importlib.util,json,os,shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('ci_vendor',ROOT/'ci/prepare-csb1-vendor.py');ci=importlib.util.module_from_spec(s);s.loader.exec_module(ci)

class CIVendor(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.t=tempfile.TemporaryDirectory(prefix='a7-ci-elf-');d=Path(cls.t.name);(d/'test.c').write_text('int fixture(void){return 3;}')
  cls.elf=d/'fixture.so';subprocess.run([str(ROOT/'sources/toolchain/bin/arm-eabi-gcc'),'-shared','-nostdlib',str(d/'test.c'),'-o',str(cls.elf)],check=True)
 @classmethod
 def tearDownClass(cls):cls.t.cleanup()
 def setUp(self):
  self.t=tempfile.TemporaryDirectory(prefix='a7-ci-vendor-');self.base=Path(self.t.name);self.system=self.base/'verified/system';self.system.mkdir(parents=True);self.tree=self.base/'android';self.stage=self.base/'staging'
  (self.system/'build.prop').write_text('ro.product.model=SM-A700FD\nro.product.manufacturer=samsung\nro.build.PDA=A700FDXXS1CSB1\nro.build.version.incremental=A700FDXXS1CSB1\n')
  self.files=self.base/'candidates.txt';self.files.write_text('lib/hw/camera.msm8916.so:lib/hw/camera.vendor.msm8916.so\nlib/hw/sensors.msm8916.so:lib/hw/sensors.vendor.msm8916.so\nbin/rild\n')
  for name in ['lib/hw/camera.msm8916.so','lib/hw/sensors.msm8916.so']:
   p=self.system/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(self.elf,p)
 def tearDown(self):self.t.cleanup()
 def run_prepare(self,allow=False):return ci.prepare(self.system,self.tree,self.stage,allow,self.files)
 def test_actual_selected_bytes_hashes_and_wrappers(self):
  before=ci.digest(self.system/'lib/hw/camera.msm8916.so');r=self.run_prepare();self.assertTrue(r['success']);self.assertEqual(r['selected_files'],2)
  vendor=self.tree/'vendor/samsung/a7lte';mk=(vendor/'Android.mk').read_text();self.assertIn('LOCAL_MODULE := camera.vendor.msm8916',mk);self.assertIn('LOCAL_MODULE := sensors.vendor.msm8916',mk);self.assertNotIn('LOCAL_MODULE := rild',mk)
  self.assertEqual(ci.digest(vendor/'proprietary/lib/hw/camera.msm8916.so'),before);self.assertEqual(ci.digest(self.system/'lib/hw/camera.msm8916.so'),before);self.assertFalse((self.stage/'safe-system-view').exists());self.assertFalse(r['pie_symbol_compatibility_verified'])
 def test_strict_missing_stops_and_preserves_inventory(self):
  (self.system/'lib/hw/camera.msm8916.so').unlink()
  with self.assertRaisesRegex(ValueError,'stock candidates unresolved'):self.run_prepare()
  r=json.loads((self.stage/'generation-audit.json').read_text());self.assertEqual(r['essential_stock_missing_count'],1);self.assertFalse(r['success']);self.assertFalse((self.tree/'vendor/samsung/a7lte/Android.mk').exists())
 def test_force_records_missing_without_substitution(self):
  (self.system/'lib/hw/camera.msm8916.so').unlink();r=self.run_prepare(True);self.assertTrue(r['success']);self.assertEqual(r['essential_stock_missing_count'],1)
  row=r['unresolved_candidates'][0];self.assertTrue(row['unresolved']);self.assertFalse(row['source_provided']);self.assertEqual(row['reason'],'not present in verified CSB1 SYSTEM')
  self.assertFalse((self.tree/'vendor/samsung/a7lte/proprietary/lib/hw/camera.msm8916.so').exists())
 def test_external_file_symlink_is_recorded_not_followed(self):
  p=self.system/'lib/hw/camera.msm8916.so';p.unlink();outside=self.base/'outside.so';shutil.copyfile(self.elf,outside);p.symlink_to(outside)
  r=self.run_prepare(True);self.assertEqual(r['unresolved_candidates'][0]['unresolved_status'],'unresolved_external_symlink');self.assertEqual(r['selected_files'],1)
 def test_external_directory_symlink_is_not_followed(self):
  (self.system/'vendor').symlink_to(self.base);self.files.write_text(self.files.read_text()+'vendor/external.so\n');shutil.copyfile(self.elf,self.base/'external.so');r=self.run_prepare(True)
  self.assertEqual(next(x for x in r['unresolved_candidates'] if x['source']=='vendor/external.so')['unresolved_status'],'unresolved_external_symlink')
 def test_source_module_and_firmware_link_destinations_skip(self):
  self.files.write_text(self.files.read_text()+'lib/libsecril-client.so\nvendor/firmware/keymaste.b00:vendor/firmware/keymaster/keymaster.b00\n');r=self.run_prepare()
  rows={x['source']:x for x in r['source_provided_skips']};self.assertTrue(rows['lib/libsecril-client.so']['source_provided']);self.assertIn('firmware/image/keymaste.b00',rows['vendor/firmware/keymaste.b00']['reason']);self.assertEqual(r['unresolved_count'],0)
 def test_wrong_identity_refused_before_vendor_generation(self):
  (self.system/'build.prop').write_text('ro.product.model=SM-A700F\nro.product.manufacturer=samsung\nro.build.PDA=A700FDXXS1CSB1\n')
  with self.assertRaisesRegex(ValueError,'SM-A700FD'):self.run_prepare(True)
  self.assertFalse(self.stage.exists())
 def test_failed_fetch_provenance_cannot_be_reused(self):
  (self.system.parent/'fetch-result.json').write_text('{"success":false,"error":"CRC failed"}')
  with self.assertRaisesRegex(ValueError,'fetch-result reports failure'):self.run_prepare(True)
 def test_optional_csc_external_link_does_not_abort_other_files(self):
  (self.system/'csc').symlink_to(self.base/'host-csc');(self.base/'host-csc').mkdir();(self.base/'host-csc/sales_code.dat').write_text('ZTO')
  r=self.run_prepare();self.assertEqual(r['csc_probe']['status'],'unresolved_external_symlink');self.assertTrue(r['success']);self.assertFalse(json.loads((self.tree/'vendor/samsung/a7lte/vendor-audit.json').read_text())['csc_region_verified'])
 def test_existing_vendor_is_preserved(self):
  v=self.tree/'vendor/samsung/a7lte';v.mkdir(parents=True);(v/'keep').write_text('keep')
  with self.assertRaisesRegex(ValueError,'vendor output must be empty'):self.run_prepare(True)
  self.assertEqual((v/'keep').read_text(),'keep')

 def test_vendor_parent_symlink_is_rejected(self):
  (self.tree/'vendor').mkdir(parents=True);outside=self.base/'other';outside.mkdir();(self.tree/'vendor/samsung').symlink_to(outside)
  with self.assertRaisesRegex(ValueError,'escapes requested tree'):self.run_prepare(True)
 def test_combined_inventory_counts_actual_missing_sources(self):
  (self.system/'lib/hw/camera.msm8916.so').unlink();self.run_prepare(True);r=json.loads((self.stage/'extraction/inventory.json').read_text())
  self.assertEqual(r['summary']['requested'],3);self.assertEqual(r['summary']['extracted'],1);self.assertEqual(r['summary']['missing'],2)
 def test_fetch_report_crc_is_required(self):
  (self.system.parent/'fetch-result.json').write_text(json.dumps(dict(success=True,ap_archive=dict(zip_entry_crc_verified=False,zip_entry_fully_consumed=True),system_identity=dict(model='SM-A700FD',build_prop_sha256=ci.digest(self.system/'build.prop')))))
  with self.assertRaisesRegex(ValueError,'complete AP ZIP entry CRC'):self.run_prepare(True)
 def test_valid_fetch_report_is_preserved_with_exact_identity_hash(self):
  (self.system.parent/'fetch-result.json').write_text(json.dumps(dict(success=True,ap_archive=dict(zip_entry_crc_verified=True,zip_entry_fully_consumed=True),system_identity=dict(model='SM-A700FD',build_prop_sha256=ci.digest(self.system/'build.prop')))))
  r=self.run_prepare();self.assertEqual(r['source_provenance']['verification_level'],'successful-full-AP-acquisition-report');self.assertFalse(r['source_provenance']['firmware_signature_verified'])

if __name__=='__main__':unittest.main(verbosity=2)
