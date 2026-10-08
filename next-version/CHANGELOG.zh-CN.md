# ROCK5T 下一版改动清单（源码快照）

状态：源码实现、内核编译和下述自动测试已完成；pacman 默认沙箱小包下载与签名验证已通过。CLI 200 包、KDE 748 包已实际安装；root 策略审计分别 28/34 项通过。CLI 整盘检查及真实首启 snapshot 27/27 项已通过，原始镜像 SHA256 前后保持一致，VM 正常关闭且 snapshot 已销毁；KDE root/boot/eMMC 软件门禁通过，整盘封装、压缩及解压回读哈希校验也已完成，最终清单见 evidence/final-release-summary.json；Git 不包含安装镜像。新版尚未进行 ROCK5T 实机测试，不能算作实机通过。

## 1. 基础与内核

- 继续采用 Arch Linux ARM 用户空间，以及 Armbian 的 ROCK5T 板级内核/启动支持；这是社区组合方案，不是 Arch 官方支持镜像。
- 内核基础仍为 Linux 6.18.44，对应 Armbian 26.8.3 的来源与补丁。匹配 Armbian commit fd4ebfd1e107d5b89f7a672c7d609789565753b2、Linux commit 1efe5d048a391de3ead2804b2e7f86376c356cc5。
- 保留 240 个板级补丁、21 个驱动整合入口、7 个固定版本外部驱动来源与 48 个驱动补丁；没有用无补丁 vanilla 内核替换 RK3588 VPU 支持。
- 新增 CONFIG_SECURITY_LANDLOCK=y，并将 landlock 加入默认 LSM 列表。新 release 为 6.18.44-current-rockchip64-landlock1，避免模块目录与旧内核冲突。
- 3577 个模块的相对路径与原版完全一致，缺失 0、新增 0；ROCK5T DTB 与原版逐字节相同。Rust 编译器探测元数据不同，但原内核没有启用 Rust。
- 保持已测的 rt_group_sched=0；实时调度预算仍为 950000/1000000 微秒，不设为无限。没有增加其他实时权限或调试 sudo。

## 2. 内核升级与回退

- 每代独立保留 Image、全部对应 modules、所选 ROCK5T DTB、initramfs 和校验元数据，位置独立于 pacman 包 payload。
- 更新时在未发布的 staging 中运行 depmod，再提交启动菜单；目录链接同步后才切换选择。
- 中断后重试核对完整模块清单；拷贝损坏、文件缺失、相同 release 的 DTB/initramfs 被替换都会拒绝。
- 当前代 Image 或 modules 损坏时，仍可选择完整旧代回退；不再把已知损坏代列为可用回退目标。
- pacman 前置检查覆盖安装、升级和删除。选中的当前代/旧代不会因为包 payload 删除而丢失。
- 不会默默覆盖手工修改的启动菜单。已有自定义菜单的系统需要在安装前单独审阅迁移。
- 这是可选回退机制，不是启动失败自动检测或无人值守自动回滚。

## 3. 首次向导与稍后配置

- 仍在本机 tty1 或串口 ttyS2 创建唯一管理员、密码与 hostname；保留互斥锁和中断恢复。恢复未完成账户时重新要求设置密码。
- 在本机生成独立 machine-id、SSH host keys 和 pacman 本地信任状态，不随镜像复制共享密码、私钥或预置用户 SSH key。
- 首次用户尚未完成前，桌面登录和 SSH 都有 provisioned 门禁。
- Wi-Fi 阶段只在本机账户及密钥/包信任准备完毕后暂时允许 NetworkManager；向导中断会关闭未提交的临时网络阶段。
- 保留扩展 root 分区选项，默认不扩展；它不是此次新增的强制磁盘操作。

### Wi-Fi

- NetworkManager 统一管理网络，提供设备选择、扫描、隐藏 SSID、连接失败重试、跳过和稍后配置。
- 默认跳过 Wi-Fi；稍后可运行 sudo rock5t-configure-network。
- 密码由 nmcli --ask 的隐藏输入直接读取，不进命令参数或向导自己的日志；NetworkManager 会为本设备保存连接及凭据，界面明确告知。
- 以太网使用正常自动配置。企业 Wi-Fi 需登录后建立合适的 NetworkManager profile。
- “连接激活”不等于验证互联网可用。

### SSH

- 单独询问“现在启动”“开机自启”“允许所选管理员使用密码登录”。默认关闭、关闭、仅公钥。
- 始终禁止 root 和旧 alarm 用户远程登录；AllowUsers 只允许选择的非 root 管理员。
- 密码登录只有首次用户明确选择后才开启；未植入任何共享公钥，公钥模式需用户自行配置授权 key。
- 先验证策略，再提交；冲突/解析失败时回滚并保持安全关闭。首次 SSH 启动发生在最终 provisioned 标记提交之后。
- 稍后可运行 sudo rock5t-configure-ssh 修改这些选择。

## 4. CLI 与 KDE

CLI 继续提供 sudo、Python、mkinitcpio、kmod、OpenSSH、NetworkManager、vim/nano、常用网络/磁盘工具以及对应无线固件。

KDE 在 CLI 基础上采用：plasma-meta、plasma-login-manager、konsole、dolphin、chromium、noto-fonts、noto-fonts-cjk、pipewire、wireplumber、pipewire-pulse、mesa、vulkan-panfrost、qt6-wayland。

- 登录管理器只用 Plasma Login Manager。构建准备会拒绝仍安装的 sddm/sddm-kcm 或残留 SDDM 可执行程序，清除旧 SDDM 配置、服务/PAM/状态路径；不保留可运行的 SDDM 备用入口。
- 使用 PLM 包自带的 service、PAM、sysusers 和 tmpfiles。PLM 等待首启完成，且不与正常 tty1 getty 抢控制台。
- Firefox 从 KDE 构建依赖移除，默认浏览器改 Chromium。
- 新用户 Chromium flags 为 --enable-features=AcceleratedVideoDecoder；没有关闭 Chromium sandbox，不包含 GPU sandbox 特例或硬件视频验收结论。
- 这是构建源和包策略变更；新版 KDE 已实际安装 748 包并通过 root/boot/eMMC 软件检查；尚未在实机测试 PLM/Chromium 会话。

### plasma-meta 的实际依赖清单

依据本次已验证签名的 ALARM plasma-meta 6.7-2 包 .PKGINFO，必选依赖共 56 项：

aurorae, bluedevil, breeze, breeze-gtk, discover, drkonqi, flatpak-kcm, kactivitymanagerd, kde-cli-tools, kde-gtk-config, kdecoration, kdeplasma-addons, kglobalacceld, kinfocenter, kmenuedit, knighttime, kpipewire, krdp, kscreen, kscreenlocker, ksshaskpass, ksystemstats, kwallet-pam, kwayland, kwin, kwrited, layer-shell-qt, libkscreen, libksysguard, libplasma, milou, ocean-sound-theme, oxygen, oxygen-sounds, plasma-activities, plasma-activities-stats, plasma-browser-integration, plasma-desktop, plasma-disks, plasma-firewall, plasma-integration, plasma-keyboard, plasma-login-manager, plasma-nm, plasma-pa, plasma-systemmonitor, plasma-thunderbolt, plasma-vault, plasma-welcome, plasma-workspace, polkit-kde-agent, powerdevil, print-manager, spectacle, systemsettings, xdg-desktop-portal-kde。

可选依赖（构建脚本不会额外请求安装）为：

- breeze-grub: Breeze theme for GRUB
- breeze-plymouth: Breeze theme for Plymouth
- kgamma: Adjust gamma settings on X
- kwin-x11: X11 window manager
- plasma-workspace-wallpapers: Additional wallpapers
- plasma-x11-session: Plasma X11 session
- plymouth-kcm: Configure Plymouth from systemsettings
- plasma-sdk: Development tools
- sddm-kcm: SDDM configuration module
- union: Next generation QtQuick/QtWidgets style engine
- wacomtablet: Drawing tablet settings on X

没有另选 Kate、Okular、Gwenview、Ark、影音播放器或办公套件。元包会带入 Discover、Spectacle 等桌面工具；上面的13个直接包与此处元包依赖应分开理解。krdp/plasma-firewall/plasma-vault 是元包组件，存在软件包不等于本构建已配置远程访问、启用防火墙或创建保险库。此处列的是直接元包依赖，完整实际 pacman -Q 清单已记录：CLI 200 包、KDE 748 包，见 evidence/packages-*-final.txt。

## 5. 镜像准备清理

- 清理构建时的 Wi-Fi profile、NetworkManager 禁用状态、SSH 选择记录、临时访问策略/网络门禁。
- 清理旧 alarm/sddm 账户痕迹、调试 sudoers 和 NOPASSWD 配置。
- 继续禁止随镜像发布 SSH host 私钥、已初始化机器身份、共享 pacman 本地私钥与构建环境凭据。

## 6. 已验证范围与限制

- 105 项 overlay 全量测试通过，0 跳过；另 7 项内核包门禁测试通过，实际编译产物也通过该门禁。
- 新内核实际在 QEMU ARM64 virt 中启动，默认 Landlock ABI 7 可用；UID1000 对允许路径正常，对禁止路径读写返回 EACCES。
- 173 项选定的上游 Landlock 测试通过，0 跳过。这不是所有可选文件系统/网络组合的全集。
- 初始两项 pivot_root 测试因特殊 initramfs 根限制失败；测试根换为普通 tmpfs 后，同一内核与测试通过，原失败日志保留。
- 双真实内核产物测试核对了每代 3577 个模块及 vermagic，覆盖进程中断、重试、完整保留及双向回退。新 initramfs 是 QEMU 测试版，不能据此宣称板级 initramfs 可启动。
- 实际 ALARM pacman 7.1.0/libalpm16 在新内核 QEMU 中使用默认 alpm UID/GID970、Landlock 与 seccomp；landlock_restrict_self 返回0。core-only 从官方镜像下载 filesystem 和 iana-etc 共0.39MiB，事务 exit0，两包签名有效且 fully trusted、SHA256 匹配。Required、CheckSpace 和原超时保持不变，没有安装软件包。测试本地信任私钥只存在于 guest RAM，关机后销毁。
- 完整默认仓库同步未通过：默认镜像跳转及 extra.db 遇到原低速超时。直连官方镜像时 core/alarm/aur 数据库可下载；core-only 小包成功不能说明 extra 超时已经解决。没有调整下载超时策略。
- SSH 真实配置解析测试用 Debian OpenSSH 10.0p2 解析目标 ALARM OpenSSH 10.6p1 的配置 fixture；没有把它写成目标版本二进制/真实 SSH 登录验证。
- 尚未完成/本轮不做：新内核 ROCK5T 实机启动、真实 Wi-Fi、SSH 远程登录、PLM 桌面会话、完整在用系统升级/回退流程、FAT 断电恢复；板级 mkinitcpio 产物已通过实际 boot preflight，CLI 首启已在通用 ARM64 QEMU 中通过。跳过实机验收只表示未测，不表示通过。

## 当前补充：AC 默认策略

KDE 使用 `/etc/xdg/powerdevilrc` 的 `[AC][SuspendAndShutdown] AutoSuspendAction=0`，仅关闭接电状态的闲置自动挂起默认行为，用户可在设置中修改；不修改电池、手动睡眠、息屏或锁屏策略。7 项新增离线回归测试已通过。

## 最终产物与 KDE 最小快照

两版整盘及压缩/解压回读哈希验证完成，最终大小与 SHA256 见 evidence/final-release-summary.json。KDE 最小 snapshot 31/31 项通过，可见 PLM 登录框；tty2 本地登录及密码 sudo 通过，PLM active/running、零重启、无 failed unit，RT 参数保持不变，正常关机后 snapshot 销毁且原始镜像 SHA256 不变。此结果不包含图形桌面会话认证、GPU/codec 或实机验收；模拟器 DRM/Vulkan 警告已如实保留。
