# v0.10 触摸暂停菜单验证

更新包为 `dist/H1GBA.bda`，正常 JIT 包，无自动退出帧数限制。解释器和详细日志包同步更新。

| 包 | 字节数 | SHA-256 |
| --- | ---: | --- |
| H1GBA.bda | 975800 | `1ce75cc0c3bdeee7f427cbec76dc4d30437cdbd86454f76c4b7efe7a3b24124e` |
| H1GBA-interpreter.bda | 564764 | `4ba19ce7dad91f843da8e1ad67f820d5a94b105df00695895703578db56ac0f8` |
| H1GBA-debug.bda | 975800 | `84dc865719a477478a2e4d63008d0bd81536e892cd53c024e20fff27f1dd686f` |

## 功能

- 游戏中点击触摸屏暂停，显示中文菜单；P 可用作实体键入口。
- 菜单支持触摸和实体方向键／确认／返回。打开菜单的首次松开不触发按钮，滑出按钮取消点击，已按住的实体键必须先松开。
- 暂停时停止核心运行、计时器和 PCM，恢复时释放游戏按键、重建音频缓冲和计时基准。
- 十字键、A/B/L/R/START/SELECT 重映射，恢复默认映射，保留前端快捷键。
- 三个即时存档槽，保存 CPU、内存、视频、声音、卡带 RAM 和 RTC；保留独立的自动电池存档。
- 原始／等比／全屏拉伸，跳帧 0/1/2，声音开关；设置按 ROM 保存。
- 更换游戏和退出仍执行电池存档及核心资源清理。

使用说明见 `docs/h1-pause-menu.md`。即时存档和配置文件均放在 ROM 旁，A/B 双份、CRC 和写后读取校验；这与原来的电池存档文件不同。

## 自动测试

`tests/pause_menu_smoke.py` 执行实际编译后的 MIPS BDA，固件服务用测试替身提供。JIT 和解释器包各自测试 GBA、GB、GBC：

- 触摸入口、初次松开防误触、滑动取消和 P 的按键保持过滤；实体键导航和恢复。
- 菜单空闲时 CPU 和内存不变，PCM 不处于播放状态。
- 保存后主动改变 CPU、工作内存和卡带 RAM，读档恢复原数据，再执行游戏并正常退出。
- A 改成 Q，移除 Z／确认别名；显示和声音设置跨调用恢复。
- 空槽和 CRC 损坏槽不改变核心、不覆盖损坏文件，显示相应消息。
- 宿主寄存器／栈恢复，没有文件句柄、堆块、窗口或 PCM 描述符泄漏。

报告为 `build/verification/pause-menu-jit-smoke.json` 和 `pause-menu-interpreter-smoke.json`，记录被测包 SHA-256。

平台回归、加载进度、原选择器／中文路径／换 ROM、GB/GBC 卡带、RTC GPIO、JIT 生成代码和自修改、音频缓冲及诊断落盘测试均通过。新全屏模式与 RGB565 参考缩放逐像素对比；原暂停菜单以外的快键仍保留。

## 完整 H1 固件

使用用户提供的 V1.41 `project.bin`（SHA-256 `d05786e442f9aad62a8d0a0cb4f6d786bdc7c2fa353a7a2b152c9ed9f01b40ef`）、本机 H1 dump 的私有测试副本和项目配置的 QEMU bbkh1。原 dump 未改动。

固件实测覆盖原创 GBA 音调 ROM、原创 GB/GBC ROM 和用户本机中文版《绿宝石》：

- 触摸可以准确打开、选择中文菜单及子菜单。坐标由导出的 `GUI+0x6C0` 实时读取系统校准结果；只读缓存坐标的早期探针已排除。
- 暂停前后读取前端帧计数，暂停期间计数不变。
- 运行后帧计数已推进，GB/GBC 和《绿宝石》的 CPU 状态已改变；即时读档后，GBA 的 ARM 寄存器和 GB/GBC 的 CPU 状态与保存位置逐字相同。小型音调 ROM 的周期循环可在不同帧停止于相同寄存器值，报告保留该实际观察值。
- 继续后帧计数增加；《绿宝石》读档后 JIT 正常执行。
- GB/GBC 的 Z→Q 重映射真实传入卡带，按下 A 的 SRAM 标志为 `a5`，松开恢复 `11`；不同 ROM 的映射独立。
- 暂停和静音时没有新 AIC PCM 包，恢复后的音调 WAV 为 32000 Hz、16 位双通道采集且含非零采样。播放器使用本项目的原生单声道输出，QEMU 的采集流以双通道承载。
- 四个游戏的显示错误均为 0，换 ROM、正常退出和窗口关闭成功，日志以 `APP_END result=0` 结束。
- 停止 QEMU 后，从 NAND 读出即时存档及配置文件，校验文件头、数据 CRC、代数和核心格式，FTL `torn_records=0`。

原始交互报告：`build/h1-emulator-test/evidence/v10-native-interaction.json`。日志、WAV、保存状态和校验报告位于同目录；菜单截图位于 `build/h1-emulator-test/v10-*-native.png`。

核验命令：

```powershell
python tests/check_pause_native_evidence.py
```

这验证的是本机完整固件模拟器的功能与恢复过程，尚未在 H1 真机测试，不代表所有商业游戏兼容或真机速度。即时存档只承诺本项目当前固定核心及格式；GB/GBC 离线 RTC 的原限制保留。v0.9 加载／音频性能对照的历史记录已保留在 `docs/verification-v09.md`，没有用菜单测试代替性能基准。
