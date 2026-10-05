# H1 GBA v0.6 JIT 有声版验证

2026-10-05，当前正式包：

- `H1GBA.bda`：867,072 字节，SHA-256
  `1e0884468ae5e1030c6eadbb156531984cb9abe2ca9d2ca95c0baa52cefd6a87`。
- 固定入口 `0x83C00020`；ELF text 766,696、data 69,444、BSS 1,514,112 字节，
  包含独立 128 KiB 栈；BSS 结束 `0x83E3DD80`，入口地址和加载窗口断言通过。
- `H1GBA-interpreter.bda`：456,008 字节，SHA-256
  `387bf635a60e2ed2aee1124584fc6a9a62e7cc28a23596f6a41931bff2f6bd4e`，同版解释器对照包。
- 项目自身代码 `-Werror` 通过；SDK BDA 格式校验通过；子模块保持固定提交且无改动。

## JIT 和平台回归

实际 MIPS BDA 在 Unicorn 中通过以下验证，固件服务由替身提供：

- 从堆内的生成代码执行 2,066,555 个 MIPS block；ARM、Thumb 的 RAM 自修改生效。
- ARM/Thumb 栈压入和弹出期间主动改写 GP，GBA 栈和结果不受影响；SRAM 为 `5A 11 22 33 44`。
- JIT 分配失败退回解释器，输出一致；退出后恢复宿主栈/寄存器，无句柄、堆或 PCM 引用泄漏。
- 正式 BDA 的选择器、取消、中文路径、M 换 ROM、Esc 退出、按键、保存和恢复通过。
- PCM 延迟消费和停滞测试通过；未播放的数据不被覆盖，停滞时自动静音并可退出。
- 分配、ROM 读取和显示服务被阻塞时，最后一条 BEGIN 记录已经关闭落盘；日志打开失败时保留
  已写日志并继续游戏。日志位置仍为 `A:\GBA\h1gba.log`。
- 平台测试覆盖键别名/重复事件、CRC、非紧密 pitch、两种缩放、存档双槽和短写保留。

40 个相同原创 ROM 逻辑帧的有界对比，关闭声音与限速，前 10 帧热身：
解释器每帧 4,080,345.73 条 MIPS block 指令，JIT 2,213,673.87 条，减少 45.75%，
比值 1.843；画面和 SRAM SHA-256 相同。这是指令统计，不是实体 CPU 周期或真机 FPS。

证据：`build/verification/jit-smoke.json`、`jit-benchmark.json`、`mips-smoke.json`、
`menu-smoke.json`、`audio-smoke.json` 和 `diagnostics-smoke.json`。

## 完整 H1 V1.41 固件

使用本机 dump 和原恢复包内核、可写私有 NAND、QEMU bbkh1 的实际文件/输入/音频服务：

- 中文 16 MiB《绿宝石》开启 JIT，开场动画和音乐运行，Start 进入电池提示，A 可继续。
- 测试音调 ROM 开启 JIT；M 换 ROM，再次启动恢复 SRAM，Esc 返回桌面。
- 每次 ROM 结束均停止音频、取消描述符引用、关闭窗口并释放 JIT；日志最终 `APP_END result=0`。
- 录音保存实际 AIC 输出的 32,000 Hz PCM；音频和画面数据见复核报告。

证据：`build/h1-emulator-test/evidence/jit-native-verification.json`、`v06-native-run.log`、
`v06-emerald.wav`、`v06-tone.wav`、`v06-AUDIO.gba.s0` 及 `build/h1-emulator-test/v06-*.png`。
复核命令为 `python tests/check_jit_native_evidence.py`，实现说明见 `docs/h1-jit.md`。

模拟器不完整模拟实体 CPU 缓存时序，尚未进行真机 FPS、缓存一致性、音质或长期稳定性测试。
不能保证所有游戏全速；仍可能断音。RTC 关闭，《绿宝石》仍有电池提示。
v0.4/v0.5 历史记录保留在 `docs/verification-v05.md`、`docs/h1-audio.md` 和原证据目录。
