// Samsung SM-A700FD only: uses the Galaxy-MSM8916 Pie libinit extension.
#include <init_msm8916.h>
void init_target_properties() {
    set_target_properties("a7lte", "SM-A700FD");
    set_lte_properties();
    set_dsds_properties();
    // SM-A700FD uses GSM/WCDMA/LTE, with no CDMA radio modes.
    property_override("ro.telephony.default_network", "9,9");
}
