# H1 GBA v0.6 MIPS JIT

默认 BDA 使用 gpSP 的 ARM/Thumb 到 MIPS 动态重编译器，解释器仍被编译用于回退。
`--core interpreter` 输出独立解释器 BDA。SDK 和 gpSP 子模块保持原来的固定提交；
`tools/prepare_gpsp.py` 仅在构建副本中重现平台补丁，检查每个补丁的原文上下文。

## H1 平台适配

- 使用 MIPS32 R1、O32、little-endian、soft-float，未启用 MIPS32 R2 专用指令。
- ROM 翻译缓存 2 MiB，RAM 翻译缓存 384 KiB，合计 2,490,368 字节；从 H1 堆分配并
  对齐到 32 字节，验证位于缓存 RAM 且在应用加载区之外。同属 `0x8xxxxxxx` 段，满足
  MIPS J/JAL 的 256 MiB 区域约束。失败时关闭 DRC，并跳过初始化空翻译缓存。
- `src/platform/jit.c` 刷新生成代码：SYNC、D-cache hit writeback/invalidate（0x15）、
  SYNC、I-cache hit invalidate（0x10）、SYNC；采用 16 字节覆盖粒度，依据 SDK 中的 H1
  原生加载器 `examples/v2/v1_game_stage.c`。不调用 Linux syscall，不关闭固件中断。
- 动态内存访问处理器会就地修改 JAL；`jit_patch.S` 在修改后同步相应缓存行，再跳入
  实际处理器。生成的跳板保留 live 寄存器和 RA，每个 patch handler 的固定 64 字节上限
  有检查。显式提供跳转延迟槽。
- 真实 H1 固件中断会恢复自己的 GP。上游把 GBA r13/SP 放在 MIPS GP，导致商业游戏
  栈损坏，模拟固件服务时不会自动暴露。H1 改为使用 MIPS s3 保存 GBA SP，GBA PC 以
  常量生成，汇编与 C emitter 的保存/恢复保持一致。GP 留给固件，未使用内核 k0/k1。
- 链接器单独放置 `.entry`，固定 BDA 入口 `0x83C00020`。JIT 汇编的 64 字节对齐不再
  推动入口；入口地址和 4 MiB 加载窗口都有链接断言。
- 换 ROM / 退出时释放翻译缓存；上游 RAM 自修改失效和 ROM 缓存满时刷新机制保留。
  特殊 1 MiB mini ROM 沿用上游禁用 JIT 的规则。

## 其他性能改动

`scale_frame` 预计算横向缩放映射，重复的输出行直接复制，原尺寸画面按行复制；
保持原来的最近邻像素、pitch 和黑边。平台测试覆盖两种比例和非紧密 pitch。
v0.6 启动阶段仍逐步落盘，运行中每 120 帧只落一条 FRAME_HEARTBEAT，减少多条诊断记录的
反复开关文件。存档检查和故障前的 BEGIN 记录保留。

构建工具缓存已编译对象，依赖源码、头文件、编译参数和工具链版本的签名；修改后
重新编译。核心不受测试帧数宏影响，可复用对象；有界 benchmark 包关闭 PCM 与限速。
正式包仍按实际 PCM 消费进度限速。

v0.9 保留同一 JIT 实现，进一步改为直接缩放到 H1 的 32 位帧缓冲、32,768 Hz 核心混音，
普通日志运行心跳为约 30 秒一次，首帧和分页详情移入 `--verbose-log` 诊断包。
本次完整固件与 AIC 对比见 `dist/VERIFICATION.md`；以下指令统计和完整固件计数为 v0.6 历史记录。

## 验证

`tests/jit_smoke.py` 运行实际 MIPS 测试 BDA，并确认从翻译缓存执行了大量代码块。
原创 ROM 调用 Thumb 和 ARM 的 RAM 函数，两次改写已执行指令；函数包含栈压入/弹出，
测试主动把 GP 改为固件值，检查 SRAM 前五字节仍为 `5A 11 22 33 44`。
同时测试 JIT 分配失败后的解释器回退、按键、存档、宿主寄存器恢复和无引用/内存泄漏。

`tests/benchmark_jit.py` 在相同平台改动、相同原创 ROM、相同 40 个逻辑帧下比较
retro_run 内的 MIPS block 指令数，前 10 帧作为热身，验证最终画面和存档 SHA-256 相同。
它包含 CPU、绘图和前端回调；Python hook 增加的宿主开销不能当作 H1 性能。
报告为 `build/verification/jit-benchmark.json`，不是硬件周期统计或真机 FPS。
最终构建的热身后每帧统计：解释器 4,080,345.73 条、JIT 2,213,673.87 条，
JIT 使用约 54.25% 指令，减少约 45.75%（比值 1.843）。最终画面和 SRAM 一致。
该结果仅适用于此原创测试 ROM；不代表所有商业游戏提速 1.843 倍。

完整固件复核使用 V1.41、可写私有 NAND、模拟器真实文件/输入/显示/音频服务。
相关日志、录音、截图与复核报告在 `build/h1-emulator-test/`。
最终正式包的完整固件运行中，《绿宝石》4455 次、测试 ROM 2727 和 168 次画面提交，
错误均为 0；三次均 `JIT_STATE enabled=1`，换 ROM 与退出完成 JIT 和 PCM 释放。
原生 A 键图像变化、SRAM CRC 与再次启动恢复通过；15 秒《绿宝石》音乐和 12 秒测试音调
已保存为 WAV。仍有音频欠载，不能保证无断音。
复核命令是 `python tests/check_jit_native_evidence.py`。
模拟器不完整模拟实体 CPU 的缓存时序；真机速度、缓存行为、音质和长时间稳定性仍需实测。

日志仍是 `A:\GBA\h1gba.log`。重点检查 `JIT_ALLOC_END`、`JIT_STATE enabled=1`、
`JIT_FREE_BEGIN/END`；释放记录带 `sync_calls` 和 `sync_bytes`。
