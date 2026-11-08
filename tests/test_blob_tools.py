#!/usr/bin/env python3
"""Synthetic fixtures, NOT firmware or hardware validation."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


extract = load('extract-stock')
generate = load('generate-vendor')


class BlobTools(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.elf = tempfile.TemporaryDirectory(prefix='a7-elf-')
        d = Path(cls.elf.name)
        tool = ROOT / 'sources/toolchain/bin/arm-eabi-gcc'
        if not tool.is_file():
            raise RuntimeError('saved ARM toolchain required for real ELF fixture audit')
        (d / 'provider.c').write_text('int stock_provider(void) { return 7; }\n')
        (d / 'consumer.c').write_text('extern int stock_provider(void); int call_stock(void) { return stock_provider(); }\n')
        subprocess.run([str(tool), '-shared', '-nostdlib', '-Wl,-soname,libstockprovider.so', str(d / 'provider.c'), '-o', str(d / 'libstockprovider.so')], check=True)
        subprocess.run([str(tool), '-shared', '-nostdlib', '-Wl,-soname,camera.msm8916.so', str(d / 'consumer.c'), '-L' + str(d), '-lstockprovider', '-o', str(d / 'camera.msm8916.so')], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.elf.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='a7-blob-test-')
        self.base = Path(self.tmp.name)
        self.system = self.base / 'system'
        self.system.mkdir()
        self.props = {'ro.product.model': 'SM-A700FD', 'ro.product.manufacturer': 'samsung',
                      'ro.product.device': 'a7lte', 'ro.build.PDA': extract.VERSION,
                      'ro.build.version.incremental': extract.VERSION}
        self.write_props()
        (self.system / 'etc').mkdir()
        (self.system / 'etc/settings.xml').write_text('<test/>')
        (self.system / 'lib/hw').mkdir(parents=True)
        shutil.copyfile(Path(self.elf.name) / 'camera.msm8916.so', self.system / 'lib/hw/camera.msm8916.so')
        shutil.copyfile(Path(self.elf.name) / 'libstockprovider.so', self.system / 'lib/libstockprovider.so')
        self.file_list = self.base / 'files.txt'
        self.file_list.write_text('etc/settings.xml\nlib/hw/camera.msm8916.so:lib/hw/camera.vendor.msm8916.so\nlib/libstockprovider.so\n')
        self.output = self.base / 'extracted'

    def tearDown(self):
        self.tmp.cleanup()

    def write_props(self):
        (self.system / 'build.prop').write_text(''.join(f'{k}={v}\n' for k, v in self.props.items()))

    def run_extract(self):
        return extract.extract(self.system, self.output, self.file_list)

    def reviewed_plan(self):
        plan = json.loads((self.output / 'vendor-review.candidate.json').read_text())
        plan['reviewed'] = True
        for row in plan['files']:
            row['action'] = row.pop('suggested_action')
            if row['action'] == 'module':
                row['module'] = row['suggested_module']
        path = self.base / 'reviewed.json'
        path.write_text(json.dumps(plan))
        return path

    def test_arm_elf_and_dependency_inventory(self):
        result = self.run_extract()
        self.assertEqual(result['summary']['abi_or_elf_audit_errors'], 0)
        row = next(r for r in result['files'] if 'camera.' in r['source'])
        self.assertEqual(row['elf']['bits'], 32)
        self.assertEqual(row['elf']['machine'], 40)
        self.assertIn('libstockprovider.so', row['elf']['needed'])
        self.assertIn('stock_provider', row['elf']['undefined_dynamic_symbols'])
        deps = json.loads((self.output / 'elf-dependencies.json').read_text())['dependencies']
        self.assertEqual(deps[0]['resolution'], 'candidate-present')
        self.assertEqual(result['summary']['extracted'], 3)
        self.assertFalse(result['pie_abi_compatible'])

    def test_wrong_model_refused(self):
        self.props['ro.product.model'] = 'SM-A700F'; self.write_props()
        with self.assertRaisesRegex(ValueError, 'SM-A700FD'):
            self.run_extract()

    def test_substring_only_not_firmware_identity(self):
        self.props['ro.build.PDA'] = 'WRONG-' + extract.VERSION
        self.props['ro.build.version.incremental'] = 'OTHER'; self.write_props()
        with self.assertRaises(ValueError): self.run_extract()

    def test_conflicting_pda_incremental_refused(self):
        self.props['ro.build.version.incremental'] = 'A700FDXXU1CQC3'; self.write_props()
        with self.assertRaisesRegex(ValueError, 'disagree'): self.run_extract()

    def test_mapping_path_traversal_refused(self):
        for line in ['../escaped', '/etc/passwd', '.', 'etc/settings.xml:../escaped']:
            with self.subTest(line=line):
                self.file_list.write_text(line + '\n')
                with self.assertRaises(ValueError): self.run_extract()

    def test_external_symlink_refused(self):
        (self.system / 'etc/settings.xml').unlink()
        (self.base / 'outside').write_text('secret')
        (self.system / 'etc/settings.xml').symlink_to(self.base / 'outside')
        with self.assertRaisesRegex(ValueError, 'escapes'): self.run_extract()

    def test_confined_symlink_materialized_and_reported(self):
        (self.system / 'etc/link.xml').symlink_to('settings.xml')
        self.file_list.write_text('etc/link.xml\n')
        result = self.run_extract()
        self.assertEqual(result['files'][0]['symlink_target'], 'settings.xml')
        self.assertFalse((self.output / 'proprietary/etc/link.xml').is_symlink())

    def test_existing_output_preserved(self):
        self.output.mkdir(); sentinel = self.output / 'keep'; sentinel.write_text('keep')
        with self.assertRaisesRegex(ValueError, 'empty'): self.run_extract()
        self.assertEqual(sentinel.read_text(), 'keep')

    def test_missing_file_inventory(self):
        self.file_list.write_text('etc/nope\n')
        result = self.run_extract()
        self.assertEqual(result['summary']['missing'], 1)
        self.assertEqual(result['files'][0]['status'], 'missing')

    def test_vendor_review_and_camera_rename(self):
        self.run_extract(); plan = self.reviewed_plan()
        output = self.base / 'vendor'
        report = generate.generate(self.output, plan, output)
        mk = (output / 'Android.mk').read_text()
        self.assertIn('LOCAL_MODULE := camera.vendor.msm8916', mk)
        self.assertIn('LOCAL_MODULE_PATH := $(TARGET_OUT)/lib/hw', mk)
        self.assertIn('LOCAL_SRC_FILES := proprietary/lib/hw/camera.msm8916.so', mk)
        self.assertIn('system/etc/settings.xml', (output / 'a7lte-vendor.mk').read_text())
        self.assertTrue(report['ready_for_diagnostic_build'])
        self.assertFalse(report['release_ready'])

    def test_vendor_refuses_unreviewed_plan(self):
        self.run_extract()
        with self.assertRaisesRegex(ValueError, 'reviewed=true'):
            generate.generate(self.output, self.output / 'vendor-review.candidate.json', self.base / 'vendor')

    def test_vendor_rechecks_hashes(self):
        self.run_extract(); plan = self.reviewed_plan()
        (self.output / 'proprietary/etc/settings.xml').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'hash changed'):
            generate.generate(self.output, plan, self.base / 'vendor')

    def test_missing_can_be_explicit_system_provider_skip(self):
        self.file_list.write_text(self.file_list.read_text() + 'bin/rild\n')
        self.run_extract(); plan = self.reviewed_plan()
        data = json.loads(plan.read_text())
        for row in data['files']:
            if row['source'] == 'bin/rild': row.update(action='skip', reason='Provided by Pie source-built rild')
        plan.write_text(json.dumps(data))
        report = generate.generate(self.output, plan, self.base / 'vendor')
        self.assertEqual(len(report['skipped']), 1)
        self.assertFalse((self.base / 'vendor/proprietary/bin/rild').exists())

    def test_non_arm_elf_is_reported_and_rejected_for_generation(self):
        shutil.copyfile('/usr/bin/true', self.system / 'lib/libstockprovider.so')
        result = self.run_extract()
        self.assertEqual(result['summary']['abi_or_elf_audit_errors'], 1)
        with self.assertRaisesRegex(ValueError, 'ELF32 ARM'):
            generate.generate(self.output, self.reviewed_plan(), self.base / 'vendor')

    def test_dependency_present_in_stock_but_not_selected(self):
        self.file_list.write_text('lib/hw/camera.msm8916.so:lib/hw/camera.vendor.msm8916.so\n')
        self.run_extract()
        rows = json.loads((self.output / 'elf-dependencies.json').read_text())['dependencies']
        self.assertEqual(rows[0]['resolution'], 'stock-present-not-selected')
        self.assertIn('lib/libstockprovider.so', rows[0]['providers_in_stock_system'])

    def test_csc_not_inferred_from_ap_version(self):
        result = self.run_extract()
        self.assertFalse(result['csc_identity']['region_verified_from_metadata'])

    def test_explicit_zto_metadata_reported(self):
        (self.system / 'csc').mkdir()
        (self.system / 'csc/sales_code.dat').write_text('ZTO\n')
        result = self.run_extract()
        self.assertTrue(result['csc_identity']['region_verified_from_metadata'])

    def test_other_csc_is_not_reported_as_zto(self):
        self.props['ro.csc.sales_code'] = 'XEO'; self.write_props()
        result = self.run_extract()
        self.assertFalse(result['csc_identity']['region_verified_from_metadata'])

    def test_duplicate_destination_refused(self):
        self.file_list.write_text('etc/settings.xml:same\nlib/libstockprovider.so:same\n')
        with self.assertRaisesRegex(ValueError, 'duplicate installation'):
            self.run_extract()

    def test_elf_cannot_be_copied_past_module_audit(self):
        self.run_extract(); plan = self.reviewed_plan()
        data = json.loads(plan.read_text())
        for row in data['files']:
            if 'camera.' in row['source']: row['action'] = 'copy'
        plan.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'prebuilt module'):
            generate.generate(self.output, plan, self.base / 'vendor')


if __name__ == '__main__':
    unittest.main(verbosity=2)
