# v0.8 GBA RTC

原先前端固定将 `gpsp_rtc` 关闭，GBA 游戏检测不到卡带时钟，《绿宝石》提示
“内置电池已耗尽”。v0.8 改为核心自动识别 RTC 卡带，并接入 H1 日历时钟。
这项改动只针对 GBA；GB/GBC 的 MBC3 仍采用 v0.7 的运行帧计时方式。

## 时间来源

`src/libc/freestanding.c` 的 `h1_wall_clock()` 只读 JZ4740 RTC：
KSEG1 `0xB0003000` 控制寄存器、`0xB0003004` 秒计数器。
H1 V1.41 固件通过相同寄存器读写日历，转换器以 1970 为基准；计数表示 H1 本地日历时间，
无需再次加时区。模拟器设备实现位于
`.tools/h1-emulator/qemu/overlay/hw/rtc/jz4740_rtc.c`，映射由 `bbk9588_create_rtc_device` 建立。
应用不写 H1 的 RTC、闹钟或控制寄存器。

接受 2000–2099 年的系统时间。硬件时钟关闭或日期无效时，从 2000-01-01 开始使用
80 Hz 开机计数推进；如果已有 RTC 状态，从保存时间继续，离线时间无法补算。
设备日历未设置正确时，请先在 H1 系统校准日期和时间。
系统时间向后调整时避免将正在运行的卡带时钟倒退；重新加载时只补非负时间差。

`src/platform/gba_rtc.c` 保存卡带时间相对于 H1 时间的关系。
游戏写入 RTC 只调整虚拟卡带时间，不改变 H1 系统时间。
构建副本通过 `tools/prepare_gpsp.py` 修改：保留核心 GPIO 协议，
补上日期/时间写入、数据低位优先顺序、reset、双向命令位序、年份 BCD 及 12 小时制。
RTC force IRQ 未实现；即时存档尚未开放。
JIT 与解释器使用相同 RTC 实现，原子模块保持固定提交且不修改。

## 存档兼容

- 原电池存档 `.gba.s0` / `.gba.s1` 的容量、身份算法和格式保持不变。
- RTC 保存为同目录 `.gba.rtc.s0` / `.gba.rtc.s1`。
- RTC 数据 32 字节，带格式版本、卡带秒数、保存时的 H1 秒数、控制字；外层使用
  双槽头、ROM 身份、序号及两级 CRC，写后读取验证。
- v0.8 每 10 秒检查；v0.9 将 RTC 独立槽改为约 60 秒检查，换 ROM 和退出时仍保存。
  恢复后补算从保存到重新打开经过的 H1 秒数；SRAM 仍每约 10 秒检查变化。
- 旧版本没有 RTC 文件时，从当前 H1 时间启动，已有 SRAM 仍可恢复。
- RTC 文件损坏时提示并保留文件，此次使用 H1 时间且停止写 RTC 文件；普通 SRAM 保存继续。
- 非 RTC 卡带不生成 RTC 文件。首次运行时间/状态未变化时可能不落盘。

日志为 `A:\GBA\h1gba.log`，新增 `RTC_BEGIN`、`RTC_READ`、`RTC_SET`、
`RTC_SAVE_LOAD`、`RTC_RESTORE`，便于核对时间来源和离线补时。
v0.9 的 `RTC_READ` 详情仅在详细日志包记录，避免正常播放中写盘。

## 验证

`tests/make_rtc_test_rom.py` 生成原创 ARM GPIO 卡带，使用已有 RTC 硬件标识，
不含商业游戏代码。`tests/rtc_smoke.py --bda dist/H1GBA.bda` 执行实际 MIPS 包：
检查串行状态与日期读写、reset、两种命令位序、12/24 小时 BCD、离线 +120 秒、
系统日期回退、旧 SRAM、硬件时钟无效回退、损坏 RTC 保留和非 RTC 卡带。
解释器包使用相同测试。测试中的 H1 服务由 Unicorn 模拟，不代替完整固件验证。

归档 v0.8 在完整 H1 V1.41 固件运行用户提供的中文《绿宝石》：系统文件选择、两次加载，
按 Start 进入“新游戏／设置”，无电池耗尽提示；第二次加载恢复并补上 18 秒离线时间。
两次提交 886 / 1001 张有效画面、显示错误均为 0，正常释放 JIT、关闭 PCM 和窗口，
退出日志 `APP_END result=0`。两个 60 字节 RTC 槽 CRC 正确，FTL 无未完成提交。
证据复核：`python tests/check_rtc_native_evidence.py`。

截图 `build/h1-emulator-test/v08-menu-check.png`、`v08-exit.png`；日志和 RTC 槽在
`build/h1-emulator-test/evidence/v08-*`，报告 `rtc-native-verification.json`。
尚未验证实体 H1、其他商业 RTC 游戏、长期树果事件或真机全速。
