#!/usr/bin/env python3
"""Exercise the patched native sensors wrapper with a host-only mock vendor HAL.

The small headers model only the members used here. This checks ownership and
error paths, not Android ABI compatibility, a sensor implementation, or a build
of the Android target. The pinned upstream file and actual common patch are used.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

HARDWARE_H = r'''
#pragma once
#include <stdint.h>
struct hw_module_t;
struct hw_device_t;
struct hw_module_methods_t {
    int (*open)(const struct hw_module_t *, const char *, struct hw_device_t **);
};
typedef struct hw_module_t {
    uint32_t tag;
    uint16_t version_major, version_minor;
    const char *id, *name, *author;
    struct hw_module_methods_t *methods;
} hw_module_t;
typedef struct hw_device_t {
    uint32_t tag, version;
    struct hw_module_t *module;
    int (*close)(struct hw_device_t *);
} hw_device_t;
#define HARDWARE_DEVICE_TAG 0xface
#define HARDWARE_MODULE_TAG 0xbeef
#define HAL_MODULE_INFO_SYM HMI
int hw_get_module_by_class(const char *, const char *, const hw_module_t **);
'''

SENSORS_H = r'''
#pragma once
#include "hardware.h"
#define SENSORS_HARDWARE_MODULE_ID "sensors"
#define SENSORS_DEVICE_API_VERSION_1_3 0x0103
struct sensor_t { int unused; };
typedef struct sensors_event_t { int unused; } sensors_event_t;
struct sensors_poll_device_t;
struct sensors_poll_device_1 {
    struct hw_device_t common;
    int (*activate)(struct sensors_poll_device_t *, int, int);
    int (*setDelay)(struct sensors_poll_device_t *, int, int64_t);
    int (*poll)(struct sensors_poll_device_t *, sensors_event_t *, int);
    int (*batch)(struct sensors_poll_device_1 *, int, int, int64_t, int64_t);
    int (*flush)(struct sensors_poll_device_1 *, int);
};
typedef struct sensors_poll_device_1 sensors_poll_device_1_t;
struct sensors_module_t {
    struct hw_module_t common;
    int (*get_sensors_list)(struct sensors_module_t *, struct sensor_t const **);
};
'''

HARNESS = r'''
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "hardware/sensors.h"

static void *tracked_malloc(size_t);
static void tracked_free(void *);
#define malloc tracked_malloc
#define free tracked_free
#include "sensorswrapper.c"
#undef malloc
#undef free

static struct sensors_poll_device_1 vendor_device;
static int lookup_result, open_result, close_result, null_vendor;
static int opened, open_calls, close_calls, free_calls, allocation_failure;
static void *wrapper_allocation;

static void *tracked_malloc(size_t count) {
    if (allocation_failure) return NULL;
    assert(!wrapper_allocation);
    wrapper_allocation = malloc(count);
    assert(wrapper_allocation);
    return wrapper_allocation;
}
static void tracked_free(void *ptr) {
    /* The wrapper owns only its allocation. Vendor close owns its own device. */
    assert(ptr && ptr == wrapper_allocation);
    ++free_calls;
    free(ptr);
    wrapper_allocation = NULL;
}
static int mock_close(struct hw_device_t *device) {
    assert(device == &vendor_device.common);
    assert(opened);
    opened = 0;
    ++close_calls;
    return close_result;
}
static int mock_activate(struct sensors_poll_device_t *device, int handle, int enabled) {
    assert((void *)device == (void *)&vendor_device);
    assert(handle == 4 && enabled == 1);
    return 73;
}
static int mock_open(const struct hw_module_t *module, const char *id, struct hw_device_t **out) {
    (void)module;
    assert(!strcmp(id, "poll"));
    ++open_calls;
    *out = NULL;
    if (open_result) return open_result;
    if (null_vendor) return 0;
    assert(!opened);
    memset(&vendor_device, 0, sizeof(vendor_device));
    vendor_device.common.close = mock_close;
    vendor_device.activate = mock_activate;
    opened = 1;
    *out = &vendor_device.common;
    return 0;
}
static struct hw_module_methods_t vendor_methods = {.open = mock_open};
static struct sensors_module_t vendor_module = {.common = {.methods = &vendor_methods}};
int hw_get_module_by_class(const char *name, const char *variant, const hw_module_t **out) {
    assert(!strcmp(name, "sensors") && !strcmp(variant, "vendor"));
    *out = lookup_result ? NULL : &vendor_module.common;
    return lookup_result;
}
static int open_wrapper(struct hw_device_t **out) {
    return HMI.common.methods->open(&HMI.common, "poll", out);
}

int main(void) {
    struct hw_device_t *device = (void *)1, *second = (void *)1;
    assert(open_wrapper(NULL) == -EINVAL);
    assert(open_calls == 0);

    lookup_result = -ENOENT;
    assert(open_wrapper(&device) == -ENOENT && !device);
    assert(!opened && !close_calls && !free_calls);
    lookup_result = 0;

    open_result = -EIO;
    assert(open_wrapper(&device) == -EIO && !device);
    assert(!opened && !close_calls && !free_calls);
    open_result = 0;

    null_vendor = 1;
    assert(open_wrapper(&device) == -ENODEV && !device);
    assert(!opened && !close_calls && !free_calls);
    null_vendor = 0;

    allocation_failure = 1;
    assert(open_wrapper(&device) == -ENOMEM && !device);
    assert(!opened && close_calls == 1 && !free_calls && !samsung_hw_dev);
    allocation_failure = 0;

    assert(open_wrapper(&device) == 0 && device && opened);
    assert(device != &vendor_device.common);
    assert(((struct sensors_poll_device_1 *)device)->activate((void *)device, 4, 1) == 73);
    int calls_before = open_calls;
    assert(open_wrapper(&second) == -ENODEV && !second);
    assert(open_calls == calls_before && opened && close_calls == 1 && !free_calls);
    assert(wrapper_sensors_module_close(NULL) == -EINVAL && opened);
    assert(device->close(device) == 0);
    assert(!opened && close_calls == 2 && free_calls == 1 && !samsung_hw_dev);

    assert(open_wrapper(&device) == 0 && opened);
    close_result = -EIO;
    assert(device->close(device) == -EIO);
    assert(!opened && close_calls == 3 && free_calls == 2 && !samsung_hw_dev);
    close_result = 0;

    assert(open_wrapper(&device) == 0 && opened);
    assert(device->close(device) == 0);
    assert(!opened && close_calls == 4 && free_calls == 3 && !samsung_hw_dev);
    assert(!wrapper_allocation);
    puts("PASS: module/open/allocation failures, active-open rejection, ownership, callback forwarding, close errors and reopen");
    return 0;
}
'''


class SensorsWrapperLifecycle(unittest.TestCase):
    def test_real_patched_wrapper_ownership(self):
        compiler = shutil.which('cc')
        self.assertIsNotNone(compiler, 'host C compiler required for lifecycle mock')
        with tempfile.TemporaryDirectory(prefix='a7lte-sensors-') as temp:
            work = Path(temp)
            source = work/'sensors_wrapper/sensorswrapper.c'
            source.parent.mkdir()
            shutil.copyfile(ROOT/'sources/common/sensors_wrapper/sensorswrapper.c', source)
            apply = subprocess.run(
                ['git', 'apply', '--include=sensors_wrapper/sensorswrapper.c',
                 str(ROOT/'patches/common-lineage16.patch')], cwd=work,
                capture_output=True, text=True)
            self.assertEqual(apply.returncode, 0, apply.stderr)
            (work/'hardware').mkdir()
            (work/'cutils').mkdir()
            (work/'hardware/hardware.h').write_text(HARDWARE_H)
            (work/'hardware/sensors.h').write_text(SENSORS_H)
            (work/'cutils/log.h').write_text('#define ALOGE(...) ((void)0)\n#define ALOGI(...) ((void)0)\n')
            (work/'harness.c').write_text(HARNESS)
            command = [compiler, '-std=gnu11', '-O1', '-g',
                       '-Werror=implicit-function-declaration', '-Werror=uninitialized',
                       '-Wno-incompatible-pointer-types', '-I', str(work),
                       '-I', str(source.parent), str(work/'harness.c'),
                       '-o', str(work/'lifecycle')]
            built = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            result = subprocess.run([str(work/'lifecycle')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            print(result.stdout.strip())


if __name__ == '__main__':
    unittest.main()
