# H1 GB/GBC/GBA v0.7 验证

2026-10-05，当前正式包：

- `H1GBA.bda`：921,720 字节，SHA-256
  `aa523b0bcd98149dee29e4e5bcb0d40357c5ae783963863e60420a13ed6b5f82`。
- `H1GBA-interpreter.bda`：510,660 字节，SHA-256
  `9cd5e654a21da190640f92fdf2acbdc2e578b2db1c3155445a7b9280a45e52e3`。
  两者均含 GB/GBC；区别是 GBA 是否启用 MIPS JIT。
- SDK BDA 校验、入口 `0x83C00020` 和 4 MiB 加载窗口断言通过；ELF text 821,012、
  data 69,820、BSS 2,057,488 字节（含独立 128 KiB 栈），BSS 结束 `0x83ECFD50`。
- 项目代码 `-Werror` 编译通过；SDK、gpSP、gnuboy 均为固定提交且子模块无修改。

## 实际 MIPS 包测试

`tests/gb_smoke.py` 使用原创 SM83 卡带，通过 GB 四色、GBC 彩色和双速、PCM 音调、
A 按下/松开、ROM 分页、SRAM 恢复、MBC1/2/3/5、2 KiB RAM/MBC2 镜像、
MBC3 天数高位和停止位、无电池不保存、非法或不支持卡带拒绝。
更换同名卡带后存档身份不匹配，旧双槽保持不变。
正式包 GBA JIT → GB → GBC → GBA JIT 切换通过，无文件、堆、PCM 描述符或窗口泄漏。

GBA 的正式包菜单/取消/GBK 中文路径/保存恢复回归、音频延迟/停滞、诊断日志故障测试通过。
JIT 实际生成代码、自修改 ARM/Thumb、固件 GP 改写和低内存解释器回退继续通过。
原 GBA 存档身份算法保持不变。证据：`build/verification/gb-smoke.json`、
`jit-smoke.json`、`menu-smoke.json`、`audio-smoke.json`、`diagnostics-smoke.json`。

## 完整 H1 V1.41 固件测试

当前 BDA 与测试 NAND 中应用的 SHA-256 一致。在 QEMU bbkh1 执行真实固件服务：

- 系统选择器以 `gba;gb;gbc` 显示三种扩展名，隐藏存档和日志。
- 按 GB → GBC → GB 恢复 → GBC 恢复 → GBA 顺序运行，分别提交
  521、512、285、239、594 张有效画面，五次显示错误均为 0。
- GB 显示单色条纹，GBC 显示白/红/绿/蓝条纹及黑边；读取原生执行状态确认 GBC CPU 双速。
- 原生 A、右方向、按键松开可由卡带 RAM 观察到状态变化。
- GB 和 GBC 两个存档槽 CRC 均正确；重新加载恢复存档，ROM 身份不同，RTC trailer 可读。
- GB/GBC/GBA 各录制约 12 秒实际 AIC 输出：32,000 Hz、16 位 PCM，信号有音调变化。
- 五次 PCM 开关与窗口开关成对，切回 GBA 启用 JIT 并释放翻译缓存；Esc 返回桌面，
  日志最终为 `APP_END result=0`。音频无提交失败或前端丢弃，仍记录 4/3/2/2/2 次队列欠载。
- 停机读取私有 NAND，FTL 未发现未完成提交记录。原 E 盘 dump 和 F 盘应用未修改。

复核命令：`python tests/check_gb_native_evidence.py`。
证据：`build/h1-emulator-test/evidence/gb-native-verification.json`、`v07-native-run.log`、
`v07-native-interaction.json`、`v07-*.wav`、`v07-*.s0` / `.s1` 和 `build/h1-emulator-test/v07-*.png`。
实现和限制见 [GB/GBC 说明](../docs/h1-gb-gbc.md)。设备日志仍为 `A:\GBA\h1gba.log`。

GB/GBC 目前使用解释器；MBC3 时钟仅在游戏运行时推进。尚未验证商业 GB/GBC 游戏、实体 H1、
真机 FPS、长期稳定性或音质，不能据此保证所有游戏兼容或全速。
v0.6 历史记录见 `docs/verification-v06.md`，其旧 BDA 保存在本机 `build/v06-release/`。
