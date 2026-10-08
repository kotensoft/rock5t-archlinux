# ROCK5T eMMC 安装与兼容性

## 结论及验证边界

2026.10.08-landlock1 的 CLI/KDE 整盘 raw 镜像采用与介质无关的 GPT、FAT32 `/boot`、ext4 根分区及 `PARTUUID` 启动配置。现阶段应复用通过完整发行验证的同一 `.img`，不制作仅改文件名的“eMMC 专版”。eMMC 安装支持属于**软件静态检查通过、实机待测**，不是硬件可用性保证。

本目录的 `payload-emmc-audit.json` 记录对真实新内核资产的只读检查：

- ROCK5T DTB 中 `/mmc@fe2e0000` 为启用的 `rockchip,rk3588-dwcmshc`，8 位、固定 MMC，含 HS400 配置。
- MMC、SDHCI、DWCMSHC、Rockchip pinctrl、固定电压 regulator、ext4 等必要驱动内建；Landlock 默认启用。
- Image、DTB、原有 U-Boot 均符合已有发行 SHA256 锁定。
- 32 KiB 处放置既有 Rockchip combined loader；16 MiB 处开始 1 GiB FAT32；1040 MiB 处开始 ext4。没有写入 eMMC boot0、boot1、RPMB 或 SPI 的设计。

这些检查不能证明 Boot ROM 实际取到该 loader、SPI 中已有引导程序的扫描顺序、eMMC 电气/HS400 时序、板载芯片容量、冷启动或断电恢复。QEMU virt 测试也不能验证这些。ROCK5T 某些配置没有焊接 eMMC，先核实硬件。

本轮没有操作任何实体存储设备。最终整盘尚需主构建的 `release_image.py verify` 结果；payload-only 报告不替代最终 root、initramfs、extlinux、GPT、文件系统和压缩镜像验证。

## 发行集成方式

本目录可原样放入仓库的 `emmc-work/`，不需要复制大镜像。构建目录仍须包含现有 `packaging-work/`、`kernel-next/payload/`、经过验证的 loader 和 host-tools。

```sh
python3 -m unittest discover -s emmc-work -v
python3 emmc-work/check_emmc.py --build-root . --variant cli
# 最终根镜像离线、无 QEMU/挂载写入后，再执行完整准备检查：
python3 emmc-work/check_emmc.py --build-root . --variant cli \
  --rootfs <offline-cli.ext4> --boot-dir <actual-cli-boot-directory>
# 对 KDE 重复上述步骤，再运行现有发行整盘 verify。
```

标准输出为 JSON，可由调用方保存到新的证据文件。工具仅作检查，不改 UUID、不扩容、不挂载、不打开块设备进行写入，也不上传。最终准备检查复用发行门禁，核对 fstab、kernel.json、实际 extlinux 及板级 initramfs；它仍不代替最终整盘验证。

`inspect_emmc_target.py` 是给之后**在板上实际安装时**用的只读预检，当前未在真实 ROCK5T 上执行。它检查 native MMC/CID、整盘用户区、512 字节逻辑扇区、容量、只读状态、当前命名空间挂载、swap 及 device-mapper 等 holders。应在宿主 Linux 上运行，不在容器里运行；检查到写盘之间仍可能发生自动挂载，因此没有自动写盘功能。10 项测试是合成输入和非目标路径的策略测试，不是设备测试。

## 首选方法：从救援 microSD 安装

Radxa 的 ROCK5T 官方说明支持：从 microSD 启动，将解压后的系统整盘镜像写入板载 eMMC，完成后关机、拔掉 SD 再开机。[官方 eMMC 安装说明](https://docs.radxa.com/en/rock5/rock5t/getting-started/install-os/emmc_boot)

下面是本项目的附加安全检查和人工操作流程。**写入将覆盖目标 eMMC 用户区现有分区和数据。先备份并确认备份可读。不要在当前根文件系统所在盘上执行。**

1. 准备能够独立启动的救援 microSD，最好使用不同发行镜像。把本次 `.img.xz`、官方发布的校验文件及本目录工具放在救援 SD 或 USB 存储上。校验压缩包 SHA256，执行 `xz --test`，保留压缩包并用 `xz --decompress --keep` 解压。再次核对完整 raw 镜像 SHA256。不得直接把 `.xz` 当 raw 写入。
2. 在 ROCK5T 上从救援 SD 启动，查看 `findmnt /`、`findmnt /boot`、`lsblk -o NAME,PATH,SIZE,TYPE,FSTYPE,MOUNTPOINTS,MODEL,SERIAL`。逐一核对 `/sys/class/block/mmcblk*/device/type` 和 `cid`；eMMC 类型应为 `MMC`，microSD 为 `SD`。不能按 `mmcblk0/mmcblk1` 编号推断用途。
3. 镜像采用 512 字节逻辑扇区，目标必须相同。4 KiB **物理**扇区且 512 字节**逻辑**扇区不因此被拒绝。若逻辑扇区为 4096，停止；不能以更改 eMMC 永久配置为“修复”。目标真实字节数须不小于解压后整盘文件，不能只比较压缩大小或产品标称 GB。
4. 对经人工确认的目标整盘运行下方只读检查。不要使用 `p1/p2`、`boot0/boot1`、RPMB、SPI 路径。卸载该盘所有分区，关闭其 swap，并退出可能自动挂载它的桌面磁盘工具；无法确认目标时停止。

```sh
# 人工填写路径；下面的占位符故意不是可用设备。
IMAGE='./archlinux-rock5t-cli-2026.10.08-landlock1.img'
EMMC='/dev/REPLACE_WITH_VERIFIED_EMMC_USER_DISK'
BYTES=$(stat -c %s -- "$IMAGE")
python3 inspect_emmc_target.py --device "$EMMC" --image-bytes "$BYTES"
```

5. 预检通过后，再次核对设备 CID、挂载状态及备份。**以下是需要操作者明确同意覆盖之后才执行的写盘命令，不是预检工具自动执行的操作。**使用整个 raw 文件，从用户区字节 0 写入；不单独刷入其他 loader。

```sh
test -f "$IMAGE" && test -b "$EMMC" || exit 1
sudo dd if="$IMAGE" of="$EMMC" bs=4M conv=fsync status=progress
sync
# 精确比较写入的前 BYTES 字节；目标可大于镜像。
sudo cmp -n "$BYTES" -- "$IMAGE" "$EMMC"
```

`cmp` 返回 0 才表示读取内容与镜像一致。非零或 I/O 错误时不要启动/扩容，先排查存储、电源和写入过程。不要向后半段未写入空间做盲目擦除。由于缓存存在，这不是冷断电后的介质保持性测试。需要更强验证时可在安全关机重启回不同身份的救援介质后重新只读比较。

6. 安全关机、断电，拔掉安装用 microSD，然后冷启动 eMMC。首次验收记录 `/proc/cmdline`、`findmnt /`、`findmnt /boot`、`lsblk -o NAME,SIZE,FSTYPE,UUID,PARTUUID,MOUNTPOINTS`，确认 `/` 和 `/boot` 都来自预期 eMMC。检查 `dmesg` 的 MMC timeout、CRC、I/O error、tuning 错误；完成至少一次正常重启与冷启动。再验收实际应用、Wi-Fi/SSH/KDE。这些结果目前全部待测。

## UUID、双介质与扩容

- 当前 CLI/KDE/发行版本分别使用不同的确定性 UUID；**同一镜像的所有克隆仍拥有相同 GPT disk GUID、分区 GUID、ext4 UUID 和 FAT serial**。不应让同版同变体 SD 与 eMMC 同时参与正常启动。`PARTUUID` 能避免 mmc 编号变化，不能消除重复 ID。
- 写盘后不要在双克隆都在线时依赖 `/dev/disk/by-uuid`、`/dev/disk/by-partuuid` 或 label 自动定位；不要直接重启而保留同镜像 SD。仅拔 SD 不能防止另一份同 ID USB/NVMe 克隆，所有同 ID 介质均需移除。
- 不提供“只运行 sgdisk -G/tune2fs -U random”捷径。这样会使 extlinux、fstab、内核管理器配置及元数据指向旧 ID。未来若做双介质独立镜像，必须在**离线**根准备阶段统一生成 disk/boot/root GUID、根 UUID/FAT serial，更新所有 root 引用，重新生成全部受管内核启动项与相关 initramfs，并重新跑完整发行校验。不得对运行中的根盘随机化 UUID。
- 镜像写入更大的 eMMC 后，备份 GPT 起初仍位于原镜像末尾，尾部额外空间未分配。不要在写入内容比对之前接受自动“修复 GPT”操作；修复会改变字节，导致原镜像比较不再相等。
- 现有首次配置程序的扩容默认选项是 `N`。第一次 eMMC 验收建议选 `N`。确认实际启动来源、无重复 ID，并备份数据后，再人工选择现有 `sudo rock5t-grow-root`。它根据当前根分区及父盘操作，仅允许普通 ext4 且根分区是最后一个分区，不假设 mmc 编号；仍是写分区表/文件系统操作，不能称为无风险。
- 如果 growpart 因备份 GPT 位置或内核重读分区失败而报错，停止并保留错误，不追加盲目 `sgdisk -e`/重建分区。应回到唯一身份的救援介质，核对起始扇区、分区 GUID 和备份后制定离线修复。当前未实测 eMMC 扩容和断电中断恢复。

## 无法启动时

先保留独立救援 SD 和原始备份；不要把清空 SPI/eMMC 当作安装前置步骤。检查电源、HDMI/串口和是否有不同引导栈从 SPI 抢先运行。板载 eMMC 不能按 ROCK5B 可拆卸模块的方法硬拔。

若 microSD 救援无法进入，官方提供 ROCK5T Maskrom 的 Linux 与 Windows 流程。它需要断电/移除 SD、按住 Maskrom，并按板级接线说明连接 USB 和供电。只在明确识别设备、目标介质和 loader 后采取恢复写入。`u-boot-rockchip.bin` 是盘内 loader，**不是** Maskrom `db` 使用的 SPL USB 下载 loader，不能混用。

- [ROCK5T Linux Maskrom](https://docs.radxa.com/en/rock5/rock5t/low-level-dev/maskrom/linux)：官方警告其 rkdeveloptool 流程不能选择目标设备/存储，应只连接明确的目标；还需先解压镜像。页面下载区域与旧命令示例的 loader 版本不一致，使用 ROCK5T 当前下载链接并核对，不能照抄旧文件名。这里不提供盲目写入的一行命令。
- [ROCK5T Windows Maskrom](https://docs.radxa.com/en/rock5/rock5t/low-level-dev/maskrom/windows)：按官方当前 RKDevTool/驱动和板级步骤，确认 eMMC 用户区与地址 0 后才写 raw。
- [ROCK5T 擦除说明](https://docs.radxa.com/en/rock5/rock5t/low-level-dev/maskrom/erase)：仅作最后恢复参考。擦除 eMMC/SPI 会破坏现有数据或启动链，不属于本方案默认安装步骤，未执行或验证。

## 来源与许可

官方安装/Maskrom文档来自 Radxa Computer (Shenzhen) Co., Ltd.，页面注明 CC BY 4.0。本说明为独立总结与本项目检查，不是官方对本 Arch 镜像的认证。DTB 来源为既有 Armbian 补丁内核，继续保留仓库中的 Linux/DT/U-Boot/固件来源锁、版权和许可证，不能因 eMMC 支持而去掉。上述来源核查日期：2026-10-08。

## 当前发行快照补充

CLI/KDE 的 root-and-boot eMMC 软件 preflight 均已通过，脱敏结果见仓库 evidence/emmc-cli-audit.json 与 evidence/emmc-kde-audit.json。CLI 整盘检查与通用 ARM64 QEMU 首启已通过；KDE 整盘封装/压缩与解压回读哈希验证也已完成，合并结果见 evidence/emmc-final-image-validation.json。以上仍不构成 eMMC 实机启动、写入或电气时序验证。
