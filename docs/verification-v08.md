# H1 GB/GBC/GBA v0.8 RTC 验证

2026-10-05 当前包：

- `H1GBA.bda`：923,448 字节，SHA-256
  `ce81e84707432ae270e9230d770ff7769086a261169f7c22d6ab7f77da131c46`。
- `H1GBA-interpreter.bda`：512,400 字节，SHA-256
  `cab0f97312cbc4476474a5b37e1356a960f0c21951313dcec966b6cb606ecc7d`。
- 两者支持 GB/GBC/GBA、声音与存档，GBA RTC 实现相同；主包启用 GBA MIPS JIT。
- SDK 校验通过，入口 `0x83C00020`，BSS 结束 `0x83ED0410`，4 MiB 加载窗口断言通过。
  ELF text 822,740、data 69,820、BSS 2,057,488 字节，含 128 KiB 独立栈。
- 项目代码 `-Werror` 编译通过，三项固定版本依赖子模块无修改。

## RTC 测试

原创 ARM 卡带通过实际 MIPS 包的 GPIO 串行 RTC 读写，验证 reset/状态、日期、
12/24 小时格式、年份 BCD、两种命令位序、离线 +120 秒、日期回退、旧 SRAM、
无效硬件时钟回退、损坏 RTC 保留且不影响 SRAM、非 RTC 卡带无额外文件。
正式 JIT 与解释器包均执行上述测试。
报告：`build/verification/rtc-smoke-jit.json`、`rtc-smoke-interpreter.json`。

完整 H1 V1.41 固件模拟器使用与正式包相同 SHA-256 的应用，运行用户提供的中文《绿宝石》：

- 自动启用卡带 RTC，实际读取 H1 JZ4740 硬件时钟。
- 从标题按 Start 直接进入“新游戏／设置”，无内置电池耗尽提示。
- 两次加载分别提交 886 / 1001 张画面，显示错误均为 0。
- 第二次加载恢复 RTC 双槽，并补上 18 秒离线时间。
- 两个 RTC 槽均为 60 字节，格式、头部和数据 CRC 正确，序号 5 / 4。
- JIT、PCM、窗口两次开关成对，正常退出，`APP_END result=0`。
- 停机读取私有 NAND，未发现未完成 FTL 提交；原 E 盘 dump、F 盘应用未修改。

复核：`python tests/check_rtc_native_evidence.py`。报告
`build/h1-emulator-test/evidence/rtc-native-verification.json`；截图
`build/h1-emulator-test/v08-menu-check.png`，日志 `evidence/v08-native-run.log`。

## 回归与限制

实际生成的 MIPS JIT、自修改 ARM/Thumb、固件 GP 改写和低内存回退通过；
系统选择器、中文路径、原 SRAM 双槽保存恢复、音频延迟/停滞及诊断日志故障测试通过。
GB/GBC 单色/彩色图形、双速、按键、音调、MBC1/2/3/5、MBC2/小 RAM 镜像、
RTC 高位及停止位、SRAM 恢复、跨核心切换继续通过。

实体 H1、其他商业 RTC 游戏、长期树果事件及真机速度尚未验证。
GB/GBC MBC3 仍只在游戏运行时推进，没有离线补时。
时钟与存档说明见 [GBA RTC](../docs/h1-gba-rtc.md)。日志为 `A:\GBA\h1gba.log`。
v0.7 记录见 `docs/verification-v07.md`，包在 `build/v07-release/`；
v0.6 记录见 `docs/verification-v06.md`。历史证据对应旧版本，不代表 v0.8 的完整固件 GB/GBC 实测。
