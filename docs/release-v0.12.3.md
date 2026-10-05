# v0.12.3 发布验证

验证日期：2026-10-06。应用标题 GameBoy，普通及性能版都使用 Noto Sans CJK SC 菜单字体。
本记录只描述本次确切构建；历史真机日志与旧版模拟器记录见性能文档，不能代替本次验证。

| 文件 | 字节 | SHA-256 |
| --- | ---: | --- |
| H1GBA.bda | 981944 | `0bb0b44bc696baea72ba287ec53b5e2a40bbca81374c036c153e5782a1e79c87` |
| H1GBA-profile.bda | 992248 | `92a921f8531782fcf7eebd019849c79f71a5c753edd8c03d4173870e12c0a586` |

固定依赖提交列于 README、构建脚本及生成的 `.build.json`。构建使用 GNU MIPS GCC 15.2.0、
Pillow 12.3.0，BDA 头部时间固定，图标资源、标题、入口及校验通过 H1 SDK 检查。
CI 标签构建必须逐字节重现上述经过运行验证的 BDA 才能发布。

另建干净 Git 检出，三个子模块从公开远端取得固定提交，重新运行安装脚本及普通/性能
构建，两份 BDA 和构建 JSON 的 SHA-256 均与运行验证一致，没有复用对象缓存。
本地 Python 为 3.11.5，CI 使用 Python 3.12，Pillow/Unicorn 按 requirements.txt 固定。
完整依赖源码包和 UTF-8 安装目录已核对；生成的 BDA、工具链、固件、NAND、ROM 与个人存档
没有作为应用仓库源码提交。

## 平台与实际 MIPS 回归

- 本机 GCC 平台测试：输入、RGB565/RGB32 缩放、选择器、GBK 路径、CRC、双槽保存、损坏保护和短写失败。
- 普通 BDA 的选择器：打开、取消、中文路径、换 ROM、加载进度、按下/松开、退出及栈/寄存器恢复。
  [选择器记录](evidence/selector.json)。
- 普通 BDA 的 GBA/GB/GBC 三核心触摸暂停、37 个菜单操作、映射、即时保存/恢复完整 CPU/RAM/SRAM、
  配置重新打开、空槽/损坏槽保护、拖动取消及 P 键：[菜单记录](evidence/pause-menu.json)。
- 实际 MXU 汇编：全部 1～255 权重，1/2/3/4/63/302/408 像素长度，56,394 个像素；
  IRQ 初始开/关、XR 和控制寄存器恢复、尾部哨兵、源数据不变：[MXU 记录](evidence/linear-mxu.json)。
- 音频延迟消费、PCM 不消费的停用保护：[音频记录](evidence/audio.json)。
- GB/GBC mapper、SRAM、MBC2、小 RAM、MBC3 RTC 及坏卡带；GBA RTC GPIO/BCD、时间设置、
  离线补偿、时钟回拨与损坏保护：[GB/GBC](evidence/gb-gbc.json)、[GBA RTC](evidence/gba-rtc.json)。
  需要精确帧数的测试使用同源码的 `--test-frames 20` 有界包，记录包含其不同哈希，未当作 Release 资产。

上述 MIPS 检查通过 Unicorn 执行真实交叉编译代码，H1 服务由替身提供。
MXU 使用独立的 Python lane 模型；不能据此测量真机速度。线性路径增加测试宿主开销，
测试仍保留 5 亿指令和 180 秒上限。换 ROM 的合成 M 键在选择器中释放，模拟真实 tap。

## 完整 H1 V1.41 固件模拟器

私有测试 NAND 根据用户自行提供的 dump/恢复包生成，不修改或发布原文件。
H1 模拟器提交 `2416cfc4bb5295a1dad44c1129159620416b3862`，使用本地 QEMU H1 overlay
及经过验证的 TCU 调度修正。QEMU SHA-256：
`eebb8dceafd707c90d8dec761eecde6484d412cab040c1604f7cce3e2ae9f4d3`；
TCU 源码哈希见原生记录。采用 QEMU 自己的 MXU 解码器，没有注入宿主固件服务替身。

普通 Release BDA 在三个核心中，通过真实触摸菜单绑定 A=K、右=D，验证 D+K 两种按下顺序、
分别松键、暂停核心冻结、继续推进、跨核心换游戏和正常退出：
[普通包记录](evidence/native-normal.json)。

性能 Release BDA 使用原创音频测试 ROM，通过 MXU 全权重启动自检、正常运行、长时间暂停、
切换保持比例线性平滑、继续游戏、TCU 原状态恢复及重新借用、退出并停止模拟器。
1020 个输出画面，显示 errors=0，TCU/profiler fault=0，NAND torn records=0。
PCM 实际采集 8.016 秒（32000 Hz），非零样本，退出统计 dropped=0、failures=0、underruns=1。
该次记录没有以“完全无欠载”作为结论。
[性能包原生记录](evidence/native-profile.json)、[耗时统计](evidence/profile-accounting.json)。

暂停与显示设置截图来自上述性能 BDA 的实际帧缓冲，保留的 `gbc-homebrew.png` 来自普通
BDA 在 Unicorn 中运行原创 SM83 homebrew。README 后续更新展示了用户提供的 GBA 绿宝石
截图，未附版本与运行环境，不用于补充本次发布的验证结论。
图片 SHA-256 和来源见 [截图记录](evidence/screenshots.json)。

## 验证边界

本次确切发布包尚无新的真机测试。此前 v0.12.2 真机日志证实平滑缩放仍有预算压力，
本次 MXU 改善的实际 FPS、音频稳定性和大 ROM 表现需在真机继续测量。
模拟器的 homebrew 帧率不代表商业游戏或真实 CPU/MXU/存储的性能。其他固件版本未验证。
