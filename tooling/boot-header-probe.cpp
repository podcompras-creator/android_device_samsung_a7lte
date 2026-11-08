// Compile the real pinned Android 9 header and check the legacy binary layout.
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <bootimg/bootimg.h>
static_assert(sizeof(boot_img_hdr_v0) == 1632, "unexpected v0 header size");
static_assert(offsetof(boot_img_hdr_v0, page_size) == 36, "page size offset");
static_assert(offsetof(boot_img_hdr_v0, header_version) == 40, "DT size / version offset");
static_assert(offsetof(boot_img_hdr_v0, os_version) == 44, "OS version offset");
static_assert(offsetof(boot_img_hdr_v0, id) == 576, "header SHA1 offset");
int main() {
  const uint32_t byte_order = 1;
  if (*reinterpret_cast<const unsigned char *>(&byte_order) != 1) return 2;
  puts("{\"result\":\"PASS\",\"endianness\":\"little\",\"header_size\":1632,\"page_size_offset\":36,\"dt_size_or_version_offset\":40,\"os_version_offset\":44,\"sha1_offset\":576}");
  return 0;
}
