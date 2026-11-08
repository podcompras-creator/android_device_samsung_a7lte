#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
export PATH="$ROOT/host/usr/bin:$PATH"
mkdir -p out/kernel logs
make -C sources/kernel O="$ROOT/out/kernel" ARCH=arm CROSS_COMPILE="$ROOT/sources/toolchain/bin/arm-eabi-" VARIANT_DEFCONFIG=msm8939_sec_a7_eur_defconfig SELINUX_DEFCONFIG=selinux_defconfig msm8916_sec_defconfig 2>&1 | tee logs/kernel-config-latest.log
make -C sources/kernel O="$ROOT/out/kernel" ARCH=arm CROSS_COMPILE="$ROOT/sources/toolchain/bin/arm-eabi-" -j3 zImage dtbs 2>&1 | tee logs/kernel-build-latest.log
