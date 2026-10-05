# H1 GBA 音频（当前 v0.9）

平台实现：`src/platform/audio.c`。接口依据固定 SDK 提交中的
`vendor/h1-sdk/reverse/docs/audio_api.md`，并检查实际 V1.41 `project.bin` 的实现。
没有直接操作 AIC、DMA、编解码器寄存器，也没有修改固件。

## 音频格式和生命周期

v0.9 构建补丁将 gpSP 混音率从 65,536 改为 32,768 Hz，减少核心和重采样工作。
gpSP libretro 提供 32,768 Hz、16 位双声道 PCM。平台将左右声道平均合为单声道，
采用整数加权平均重采样至 32,000 Hz，跨回调保留相位与累加器。
输出配置为九个 32 位字，前三个字为 `{32000, 1, 4096}`，其余清零。

SYS 服务表由运行时 `0x83C0000C` 提供：

| 偏移 | 使用方式 |
| --- | --- |
| +0x50 / +0x54 | 初始化 / 销毁完整的 32 字节 PCM 描述符 |
| +0x58 | 初始化设备 |
| +0x5C | 提交环形描述符；退出时提交空描述符取消引用 |
| +0x60 / +0x64 / +0x68 | 开始 / 停止 / 关闭设备 |

描述符和 PCM 数组均按 32 字节对齐，描述符的后 24 字节保留给系统。
16 KiB 环形缓冲包含 8192 个单声道样本，即 256 ms 容量；先积累 4096 样本
（128 ms），再提交 route=0、repeats=0、flags=0，让固件连续读取该环。
相比旧包增加约 64 ms 目标音频延迟，换取更多短暂停顿余量。
每次换 ROM 和退出均先停止并取消播放，再关闭设备和销毁描述符，随后释放核心。

## 缓冲所有权和帧节奏

V1.41 的短块追加队列会增加一个内部计数，但连续消费链表时不能按块正确减回，
因此使用一个持久环，而不反复追加短块。固件播放游标走过的区域才归生产者复用；
未读样本不能覆盖。已消费区域清零，避免缺少新数据时重复旧内容。

SDK 没有公开 PCM 完成查询函数。平台从运行时提供的 SYS+0x5C 实现中验证
三条 MIPS 指令并解析队列地址，只读查询首节点的描述符和游标。
不硬编码固件 RAM 地址，不写队列或固件内部计数。节点地址、PCM 游标及范围均有检查。
这是 V1.41 平台实现，其他固件指令模式不匹配时记录原因并继续静音运行。

开启 PCM 后，固件软件毫秒计时器的进度会落后于实际 AIC 播放进度。
音频启用时，用环内待播样本数控制帧节奏，维持约 128 ms 音频领先量；
静音回退时仍使用原来的 59.7275 Hz 计时节奏。播放游标持续停滞超过 80 个原始
80 Hz 时钟计数时自动停用输出，并保持按键和退出可用。
慢设备仍可能出现音频欠载；这套实现不保证所有 ROM 全速。

## 复核

```powershell
python tools/build.py --toolchain .tools/toolchain/bin
python tests/audio_smoke.py
python tests/mips_smoke.py --bda build/release/H1GBA.bda --menu
python tools/build.py --verbose-log
python tests/diagnostics_smoke.py
```

音频测试执行实际 MIPS BDA，模拟游标消费及停滞，检查格式、对齐、初始化/清理配对、
非零正负样本、未读数据保护和设备停滞时回退，结果在 `build/verification/audio-smoke.json`。

原创音频 ROM 可用 `tests/make_test_rom.py` 的 `make_rom(tone=True)` 生成。
它延续红色画面、A 键和 SRAM 测试，并打开 GBA PSG 通道 1，输出 1024 Hz 方波。
不含商业 ROM 或商业 BIOS。

完整固件测试环境沿用 `h1-emulator-test.md` 的私有镜像。运行音频 ROM 后，从模拟器
实际 AIC 输出的 WebSocket 录取 PCM：

```powershell
python tools/capture_h1_audio.py build/h1-emulator-test/evidence/v05-final-tone.wav --seconds 12
```

该工具使用模拟器已有的 H1AU 协议，保存 16 位双声道 WAV 和统计 JSON；双声道来自
模拟器编解码器输出，应用本身提交的是单声道。需已准备 `.tools/h1-emulator`。

日志仍位于 `A:\GBA\h1gba.log`：包含 AUDIO_OPEN、DESCRIPTOR、DEVICE、START、
STALL 和 CLOSE 记录；详细诊断包另有 SUBMIT 和首帧记录。停止记录中提供回调次数、提交次数、非零样本、
丢弃样本、错误和欠载次数。设备不可用时记录原因并继续游戏。

完整固件的最终录音、日志和复核报告在 `build/h1-emulator-test/evidence/`。
2026-10-05 的 v0.5 历史 BDA（SHA-256 见 `docs/verification-v05.md`）录取结果：

- `v05-final-tone.wav`：32,000 Hz，12.0195 秒，最小 -3904、最大 3640，
  约 1024 Hz 的测试方波；非零样本占 90.27%，最长连续零样本 257.625 ms。
- `v05-final-emerald.wav`：32,000 Hz，15.0065 秒，最小 -6967、最大 5291；
  中文《绿宝石》开场动画和音乐同时运行。
- `v05-sound-captures.log` 的前两次运行：测试 ROM 5087 次、绿宝石 1360 次画面提交，
  图像错误均为 0；换 ROM 前音频描述符均被关闭，音频错误和丢弃样本为 0。
  音频欠载分别为 94、29 次，因此仍会断音。这份日志的第三次运行被测试停机中断，
  不能用它证明最后一次正常退出；单独的 `v05-clean-exit.log` 用于复核退出和存档恢复。

执行 `python tests/check_audio_native_evidence.py` 可复核录音、日志与 `build/baseline-v05/`
已归档 v0.5 BDA 的身份。v0.6 的完整固件 JIT / 音频记录见 `h1-jit.md`。
v0.9 与 v0.8 的同机 AIC 对比见 `dist/VERIFICATION.md`，可用
`python tests/check_loading_audio_native_evidence.py` 复核。普通包播放期间不记录
采样 ROM 访问、RTC 读取和 PCM 提交详情；SRAM 校验改用查表 CRC，RTC 独立槽
每约 60 秒及退出时保存。游戏 SRAM 仍每约 10 秒检查变化，实际写盘可能造成短暂停顿。
真机音量、扬声器音质和运行性能尚未实测。
