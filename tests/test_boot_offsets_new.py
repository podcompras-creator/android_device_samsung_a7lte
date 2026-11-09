"""Exercise real Pie/Samsung argument propagation with temporary NONFLASHABLE bytes.

No kernel is compiled. No fixture is retained in PRODUCT_OUT or artifacts/.
The configured platform sources must be available (ANDROID_TREE or verification/platform).
"""
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = Path(os.environ.get('ANDROID_TREE', ROOT/'verification/platform'))


def section(text, start, end):
    return text[text.index(start):text.index(end, text.index(start))]


class BootOffsetPropagationTests(unittest.TestCase):
    def test_native_board_offsets_reach_boot_and_recovery_headers(self):
        core = PLATFORM/'build/make/core/Makefile'
        samsung = PLATFORM/'hardware/samsung/mkbootimg.mk'
        self.assertTrue(core.is_file() and samsung.is_file(),
                        'selected platform build/make and hardware/samsung sources required')
        qcom_policy = PLATFORM/'device/qcom/sepolicy-legacy/sepolicy.mk'
        if not qcom_policy.is_file():
            # The small pinned policy checkout also supports a partial local sync.
            qcom_policy = ROOT/'sources/sepolicy-legacy/sepolicy.mk'
        text = core.read_text()
        boot_args = section(text, 'INTERNAL_BOOTIMAGE_ARGS :=',
                            '# BOARD_USES_RECOVERY_AS_BOOT = true')
        recovery_args = section(text, 'INTERNAL_RECOVERYIMAGE_ARGS :=',
                                '# Keys authorized to sign OTA packages')
        with tempfile.TemporaryDirectory(prefix='a7lte-offsets-NONFLASHABLE-') as temp:
            work = Path(temp)
            for source, destination in (
                (ROOT/'android/device/samsung/a7lte/BoardConfig.mk',
                 'device/samsung/a7lte/BoardConfig.mk'),
                (ROOT/'android/device/samsung/msm8916-common/BoardConfigCommon.mk',
                 'device/samsung/msm8916-common/BoardConfigCommon.mk'),
                (PLATFORM/'device/samsung/qcom-common/BoardConfigCommon.mk',
                 'device/samsung/qcom-common/BoardConfigCommon.mk'),
                (qcom_policy,
                 'device/qcom/sepolicy-legacy/sepolicy.mk'),
            ):
                target = work/destination
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
            # Opaque marker bytes only: these cannot be used as kernel/ramdisk/DT.
            for name in ('kernel.NONFLASHABLE', 'ramdisk.NONFLASHABLE', 'dt.img'):
                (work/name).write_bytes(b'NONFLASHABLE offset-propagation fixture\n')
            # The recipe treats MKBOOTIMG as one prerequisite executable path.
            # This shim only invokes the preserved upstream Python program.
            launcher = work/'mkbootimg-upstream'
            launcher.write_text('#!/usr/bin/env python3\nimport runpy\n'
                                'runpy.run_path('+repr(str(ROOT/'tooling/boot-sources/mkbootimg'))
                                +', run_name="__main__")\n')
            launcher.chmod(0o755)
            (work/'core-args.mk').write_text(boot_args+recovery_args)
            lines = [
                'TARGET_BUILD_VARIANT := userdebug',
                'PLATFORM_VERSION := 9.0.0',
                'PLATFORM_SECURITY_PATCH := 2022-01-05',
                'include device/samsung/a7lte/BoardConfig.mk',
                'BOARD_KERNEL_PREBUILT_DT := true',
                'BOARD_MKBOOTIMG_ARGS += --board NONFLASHABLE',
                f'PRODUCT_OUT := {work}',
                f'INSTALLED_KERNEL_TARGET := {work}/kernel.NONFLASHABLE',
                f'INSTALLED_RAMDISK_TARGET := {work}/ramdisk.NONFLASHABLE',
                'recovery_kernel := $(INSTALLED_KERNEL_TARGET)',
                'recovery_ramdisk := $(INSTALLED_RAMDISK_TARGET)',
                'include core-args.mk',
                f'MKBOOTIMG := {launcher}',
                f'INSTALLED_BOOTIMAGE_TARGET := {work}/boot.NONFLASHABLE.img',
                f'INSTALLED_RECOVERYIMAGE_TARGET := {work}/recovery.NONFLASHABLE.img',
                f'RECOVERYIMAGE_ID_FILE := {work}/recovery.NONFLASHABLE.id',
                'my-dir = $(patsubst %/,%,$(dir $(lastword $(MAKEFILE_LIST))))',
                'hide :=',
                'pretty = @echo $(1)',
                # This test checks offset propagation only, not partition limits.
                # Real output capacity is checked by validate-built-artifacts.py.
                'assert-max-image-size = test -s $(1)',
                f'include {samsung}',
                '$(info EFFECTIVE_BOARD_MKBOOTIMG_ARGS=$(BOARD_MKBOOTIMG_ARGS))',
                '.PHONY: audit',
                'audit: $(INSTALLED_BOOTIMAGE_TARGET) $(INSTALLED_RECOVERYIMAGE_TARGET)',
            ]
            (work/'OffsetAudit.mk').write_text('\n'.join(lines)+'\n')
            result = subprocess.run(['make', '--no-print-directory', '-f',
                                     'OffsetAudit.mk', 'audit'], cwd=work,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            for kind in ('boot', 'recovery'):
                data = (work/(kind+'.NONFLASHABLE.img')).read_bytes()
                values = struct.unpack_from('<10I', data, 8)
                self.assertEqual(data[:8], b'ANDROID!')
                self.assertEqual(data[48:64].split(b'\0', 1)[0], b'NONFLASHABLE')
                self.assertEqual(values[1], 0x80008000)
                self.assertEqual(values[3], 0x82000000)
                self.assertEqual(values[6], 0x81E00000)
                self.assertEqual(values[7], 2048)
                self.assertEqual(data[-16:], b'SEANDROIDENFORCE')
            self.assertIn('--ramdisk_offset 0x02000000', result.stdout)
            self.assertIn('--tags_offset 0x01E00000', result.stdout)
            print('PASS: native BoardConfig + selected core args + Samsung recipe '
                  'propagate verified offsets to both temporary NONFLASHABLE headers')


if __name__ == '__main__':
    unittest.main()
