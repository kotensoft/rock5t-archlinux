declare -a UBOOT_TARGET_BINS=('u-boot-rockchip.bin' 'u-boot-rockchip-spi.bin')
declare UBOOT_TARGET_MAKE='BL31=bl31.elf ROCKCHIP_TPL=/armbian/cache/sources/rkbin-tools/rk35/rk3588_ddr_lp4_2112MHz_lp5_2400MHz_v1.20_20250926.bin'
declare UBOOT_TARGET_CONFIG="u-boot-config-target-1"
declare UBOOT_TARGET_DEFCONFIG="u-boot-defconfig-target-1"
