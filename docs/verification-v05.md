# H1 GBA v0.5 有声诊断版验证记录

验证日期：2026-10-05。当前包为解释器测试版，包含 H1 原生 PCM 声音。

- 正式 BDA：455,564 字节，入口 `0x83C00020`，菜单分类 `0x48`。
- SHA-256：`f29555ab4343a1c77b39d8db8f721c048a2ef295662624eb8e84644f03122061`。
- ELF：text 394,728 字节，data 30,024 字节，BSS（含独立 128 KiB 栈）1,278,848 字节。
- 应用区结束地址 `0x83D9FEE0`，链接窗口上限检查通过。
- 本项目 C/汇编文件启用 `-Werror`，编译通过；上游 gpSP 保留原代码及其编译警告。
- H1 SDK BDA 头部/资源校验通过；SDK 的 header/validate 共 8 个回归测试在 v0.2 验证时通过，SDK 未修改。
- 本机平台测试通过：选择器参数、取消、未终止和错误扩展名输出、GBK 路径、CRC 标准向量、按键别名与重复事件、
  非紧密输入 pitch、两种缩放、双槽读写、损坏回退及短写保留。
- MIPS 服务表测试通过：执行实际测试 BDA 20 帧，随后退出并重新运行，
  验证画面颜色、A 键、SRAM 保存和恢复、CRC、宿主栈及寄存器恢复、无文件或堆分配泄漏。
- 正式 BDA 的系统选择器调用测试通过：选择游戏、运行、Escape 退出及再次启动恢复存档；
  M 键再次选择保留当前目录，中文路径的 ROM 加载、存档及恢复通过，不再读取 roms.txt。
- 日志位于 `A:\GBA\h1gba.log`；验证启动、选择器、ROM 读取、存档、首帧和退出记录存在。
- 在模拟固件服务内部停止执行，确认内存申请、ROM 读取、显示提交卡住之前的 `BEGIN`
  记录已关闭落盘，且没有未关闭的日志句柄。模拟追加打开失败后，已写记录保留，游戏继续运行。
- 原 BB 虚拟机启动跟踪通过：GUI+0x9EC 参数为目录、扩展名、sp+64 输出区。
  原程序 SHA-256 与用户提供文件相符，未修改原文件。此项为 v0.2 的参考证据。

运行证据：`build/verification/mips-smoke.json`、`menu-smoke.json`、
`bbvm-selector-trace.json`、`diagnostics-smoke.json`、`h1gba-example.log` 及对应 PNG；
ABI 分析见 `docs/h1-file-selector.md`。

上述 MIPS 服务表测试用 Unicorn 模拟 CPU，并以替身提供固件服务。

v0.5 新增音频验证：

- gpSP 的 65,536 Hz 双声道 PCM 重采样为 H1 原生 32,000 Hz 单声道，使用 32 字节对齐的
  完整描述符和持久环形缓冲；通过实际播放游标控制帧节奏。
- 实际 MIPS BDA 的延迟消费和停滞消费测试通过：产生非零音频；未消费 PCM 不被覆盖；
  设备停滞时退回静音并正常退出；结束后无活动描述符引用。
- 完整 H1 V1.41 固件录到了测试 ROM 的 1024 Hz 方波和中文《绿宝石》的音乐，
  使用模拟器 AIC 输出的 H1AU 流保存 WAV，没有替换固件音频服务。
- 两次换 ROM 前均完成音频停止、取消引用和设备关闭；日志中音频服务错误和丢弃样本均为 0。
- 连续录音仍有短暂静音，日志中存在欠载。测试 ROM 的 12.02 秒录音中非零样本占 90.27%，
  最长连续零样本为 257.63 ms，不能视为无断音或全速验证。

音频实现和复核见 `docs/h1-audio.md`；证据为 `build/verification/audio-smoke.json`、
`build/h1-emulator-test/evidence/v05-final-tone.wav`、`v05-final-emerald.wav`、
`v05-sound-captures.log`、`v05-clean-exit.log` 和 `audio-native-verification.json`。

以下为 v0.4（SHA-256 `07ab1ec5c02c74243a16a7e05c6ec73f69a4f95f1d16318752dc7559811dceee`）
使用用户本机固件和 dump 在 QEMU bbkh1 完整 H1 V1.41 固件中的历史图像和存档证据：

- 系统选择器、H1TEST 的 A 键图像变化、M 换 ROM、Escape 退出桌面通过。
- 关闭文件选择器取消通过，固件返回空路径，日志为 `ROM_SELECT_END status=0` 和 `APP_END result=0`。
- 中文路径的本机 16 MiB《绿宝石》显示标题，Start 可以继续；累计 1973 次画面提交，错误数为 0。
- 实际 NAND 中的 H1TEST 存档为 131,100 字节，SRAM 首字节 0x5A，头部和数据 CRC 通过；
  再次运行确认 `SAVE_LOAD_END status=1 slot=0 generation=1`。
- 窗口关闭三次，日志最后为 `APP_END result=0`；首次完整测试的 FTL 读取未发现未提交记录。
- 修复选择 ROM 后画面停在选择器：改用原生游戏窗口和 32 位帧缓冲，不再依赖游戏模式下被跳过的 RGB565 刷新。

完整证据：`build/h1-emulator-test/evidence/native-verification.json`、`v04-native-run.log`、
`H1TEST.gba.s0` 和 `build/h1-emulator-test/v04-*.png`。
打包、运行和只读提取说明见 `docs/h1-emulator-test.md`；原始 dump 未修改。

尚未获得真机日志或完成真机验证；不能据模拟器结果保证真机 FPS、所有商业游戏兼容性或长期稳定性。
当前 RTC 关闭，《绿宝石》可以继续游戏但有电池提示。真机声音及音量尚未实测。
