# v0.7 GB/GBC 支持

同一个 `dist/H1GBA.bda` 可运行 GBA、GB 和 GBC。系统选择器传入 `gba;gb;gbc`，
选择 `.gba` 使用原 gpSP 核心；`.gb` / `.gbc` 使用 gnuboy。GB/GBC 的彩色模式根据卡带头判断，
因此支持把彩色卡带命名为 `.gb`。GBA 保留 MIPS JIT；GB/GBC 当前使用 SM83 解释器。

## H1 接入

- 核心固定为 rofl0r/gnuboy 提交 `c367bb4ba96fb07cd62f72f5ecb43aeff7012564`，保留其 GPL-2.0 许可。
- `src/platform/gb_core.c` 提供 H1 ROM 读取、启动寄存器、每帧执行、输入、PCM、卡带 RAM 和 RTC。
  不加载商业 BIOS，不使用上游桌面窗口、POSIX 文件或菜单接口。
- 160×144 RGB565，等比例放大到 302×272 或原尺寸居中。帧跳过只减少显示，CPU/音频/计时继续运行。
- 四通道音频由 gnuboy 合成为 32,768 Hz、8 位双声道，转换为 16 位后交给现有 H1 PCM 层；
  最终输出 32,000 Hz 单声道，按原生播放进度限速。
- Z/确认=A、X=B、方向键、Enter=Start、空格=Select；V、F、M、Esc 与 GBA 一致。
- 文件关闭、音频描述符释放、窗口关闭均在核心切换前完成。GB/GBC 固定缓冲与 gpSP 分离，
  链接时重命名 gnuboy 的外部符号，避免同名 `cpu`、`ram`、`sound` 等覆盖 gpSP。

## 卡带与存档

加载器接入无 MBC、MBC1、MBC2、MBC3、MBC5、带震动的 MBC5 映射和 HuC1。
ROM 容量为标准 32 KiB～8 MiB，完整读入堆，容量头与文件长度必须一致；未支持压缩包、
非标准 ROM 容量编号、MBC7 倾斜传感器、相机、HuC3、联机、SGB 边框或震动输出。
这是接入范围，不代表这些映射器的所有卡带都已验证兼容。

`tools/prepare_gnuboy.py` 在构建副本中修复 MBC2 的 512 字节镜像、4 位写入/高 4 位读为 1，
以及 2 KiB SRAM 镜像；原子模块保持干净。无 MBC 的 RAM 卡带无需写入 RAM 使能寄存器。

GB/GBC 电池 RAM 使用原 `.s0` / `.s1` 双槽格式，容量按卡带头决定。
ROM 身份检查读取前 512 字节，包含 GB 的标题、类型与校验字段；更换同名卡带时保护旧存档。
GBA 仍采用原前 192 字节的身份算法，已有 GBA 存档继续可读。
无电池且无 RTC 的卡带不生成存档文件。

MBC3 计时器状态作为 32 字节小端 trailer 与 SRAM 一起校验、写入和恢复。计时按每帧 70,224
时钟累计，512 天回绕，支持停止位和第 9 位天数。每次保存前同步，恢复 SRAM 后恢复计时器。
GB/GBC 关闭游戏期间时钟暂停；尚未调用 H1 日历或实现离线补时。
GBA 在 v0.8 单独接入了 H1 硬件 RTC，见 [GBA RTC 说明](h1-gba-rtc.md)。
这里只保存电池数据和计时器，不是游戏运行状态快照。

## 验证

```powershell
python tools/build.py --toolchain .tools/toolchain/bin --test-frames 20
python tests/gb_smoke.py
python tests/jit_smoke.py
python tests/mips_smoke.py --bda dist/H1GBA.bda --menu
python tests/audio_smoke.py
```

实际 MIPS BDA 测试覆盖 GB 四色、GBC 彩色及 CPU 双速、音调、按键、ROM 分页、
SRAM/RTC 恢复、小 SRAM/MBC2 镜像、MBC3 天数高位与停止、无电池不保存、损坏或不支持的
ROM 拒绝、替换同名卡带后旧存档保护，以及 GBA JIT → GB → GBC → GBA JIT 的资源释放。
GBA JIT 自修改代码、固件 GP 改写和低内存解释器回退继续通过。

完整 H1 V1.41 固件采用私有可写 NAND，由原创 `GBTEST.gb`、`GBCTEST.gbc` 和 `AUDIO.gba`
验证系统选择器三种扩展名、原生图形、A/方向键及松开、AIC 实际 PCM、双槽恢复、GBC 双速、
切回 GBA JIT 和正常退出桌面。复核命令：

```powershell
python tests/check_gb_native_evidence.py
```

证据位于 `build/verification/gb-smoke.json` 和
`build/h1-emulator-test/evidence/gb-native-verification.json`；后者同时复核当前 BDA 与测试镜像 SHA-256。
完整固件录音为 `v07-gb.wav` / `v07-gbc.wav` / `v07-gba.wav`，截图为 `v07-*.png`。
日志仍保存在设备 `A:\GBA\h1gba.log`。

GB/GBC 尚未用商业游戏或实体 H1 测试。核心不是逐周期精确实现，仍可能出现游戏兼容性问题和断音；
模拟器结果不能作为真机 FPS 或音质承诺。
