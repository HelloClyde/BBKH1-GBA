# 完整 H1 固件测试

本次确切发布包的验证见 [v0.12.3 发布记录](release-v0.12.3.md)。
下面保留早期测试环境与历史记录，旧版证据不代表本次构建的实测。

2026-10-04，使用用户本机 `E:\bbk\H1` 文件 dump 和 V1.41 SD 恢复包中的
`project.bin`。原目录和设备 F: 均未修改。测试镜像仅保留必要系统数据、应用程序和宠物
游戏数据；省略词典等约 787,850,236 字节，复制约 153,914,266 字节。
省略发生在测试镜像中，没有删除原 dump。私有 NAND 文件为 1,107,296,256 字节。

## 环境

- H1 模拟器：`MrDefinition1999/bbk-h1-emulator`，提交 `2416cfc4bb5295a1dad44c1129159620416b3862`。
- 上游 QEMU：`98b060da3a4f92b2a994ead5b16a87e783baf77c`，安装上述仓库 H1 overlay。
- 本机 UCRT64 构建，QEMU `bbkh1`、64 MiB、单线程 TCG、普通时钟、可写 NAND。
- 内核 SHA-256：`d05786e442f9aad62a8d0a0cb4f6d786bdc7c2fa353a7a2b152c9ed9f01b40ef`。
- 使用模拟器已有的桌面壁纸回退补丁；没有为 GBA 修改固件指令或注入宿主服务替身。
- NAND 中 `应用/程序/黑白子.bda` 替换为 H1GBA，复用原生游戏菜单槽位。

## 打包和启动

先把 H1 模拟器放在 `.tools/h1-emulator`，根据它的文档编译包含 H1 overlay 的 QEMU。
启动脚本通过 `-Qemu`、`-DllDir` 接受本机路径，无需改写源码。镜像生成使用本机
`gcc`，可通过 `HOST_CC` 指定。以下路径为需替换的示例。

```powershell
python tools/build.py --toolchain .tools/toolchain/bin
python tools/build_h1_test_image.py --dump "你的H1文件dump" --kernel "你的恢复包/project.bin" --rom "你的游戏.gba"
& tools/start_h1_test.ps1 -Qemu "你的QEMU/qemu-system-mipsel.exe" -DllDir "你的MSYS2/ucrt64/bin"
```

镜像和暂存文件在 `build/h1-emulator-test/`。已经存在暂存目录时必须明确加
`--reuse-stage` 才会重新打包；重新打包创建新的测试 NAND，不保留上一份 NAND 中的运行存档。
镜像脚本不会改写 dump。固件、镜像和用户商业 ROM 均不纳入源码或发布包。

浏览器打开 `http://127.0.0.1:8793/`。首次启动由前端完成触摸校准。
恢复到桌面后选择游戏分类并向左滑到末页，H1GBA 图标位于 `(42,51)`。
SDK 导航脚本可辅助到达该页，但其默认槽位坐标 `(305,51)` 不适用于本镜像；
启动和选择之前必须查看当前画面，避免额外确认键直接选中默认 ROM。

SDK 导航辅助：

```powershell
python vendor/h1-sdk/scripts/navigate_emulator_game_slot.py --no-reset --capture build/h1-emulator-test/menu.png
```

## 镜像格式修正

H1 V1.41 的 FTL 从 NAND 容量推导 FAT 簇数量，不能直接沿用 9588 的小容量镜像布局。
本镜像为 4096 个物理单元，每单元 128 页，每页 2048 数据字节加 64 OOB 字节，
前 64 单元保留、64 号单元存 BBT；OOB 使用固件认可的提交标记、代号与 RS ECC。

H1 禁止写入 LBA 512 以下区域。FAT 的保留扇区采用 480，分区前缀采用 32，
确保 FAT 从 LBA 512 开始。原先的 1 个保留扇区会让 FAT 写失败并阻塞后续文件访问。
这属于测试镜像构造问题，不是 ROM 解释器缺陷。

原 dump 的 `SysTp.cfg` 是实机触摸参数，本镜像省略它，让模拟器重新校准自身 ADC。

## 实际结果

正式包 SHA-256：`07ab1ec5c02c74243a16a7e05c6ec73f69a4f95f1d16318752dc7559811dceee`。

- 原生文件选择器正常显示 `.gba` 列表，中文路径原样加载。
- 原创 H1TEST：A 键改变首像素蓝/绿色，正常显示红色画面和黑边；M 返回选择器。
- 本机 16 MiB《口袋妖怪 - 绿宝石》：显示版权和标题画面，Start 进入后续界面，
  共 1973 次有效画面提交，日志显示错误数为 0，M 返回选择器。
- H1TEST 原生文件系统写出 131,100 字节存档，头部和数据 CRC 正确，SRAM 首字节为 0x5A。
  再次选择 H1TEST 后固件日志确认恢复第 0 槽、第 1 代存档。
- Escape 正常退出，游戏窗口关闭，桌面恢复，日志以 `APP_END result=0` 结束。
- 点击文件选择器右上角关闭按钮取消，日志为 `ROM_SELECT_END status=0`，正常返回桌面，未加载 ROM。

关键修复：选择器返回后进入原生游戏模式，普通 GUI RGB565 刷新被跳过。
v0.4 使用 GUI+0x84C/+0x850 管理游戏窗口，GUI+0x8F4 查询 480×272、步长 1920、
32 位 LCD 帧缓冲，将 gpSP RGB565 转为 0x00RRGGBB。按键继续使用经实际验证的
H1 GUI+0x750 矩阵事件。

截图、日志、存档和自动复核 JSON 在 `build/h1-emulator-test/`，其中
`v04-emerald-title.png`、`v04-native-a.png`、`v04-h1test-restored.png`、
`v04-exit-desktop.png` 是实际完整固件画面。

停机后只读提取 NAND 文件并检查证据：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8793/api/stop
python tools/read_h1_test_file.py --output build/h1-emulator-test/evidence/v04-native-run.log
python tools/read_h1_test_file.py --file GBA/H1TEST.gba.s0 --output build/h1-emulator-test/evidence/H1TEST.gba.s0
python tests/check_native_evidence.py
```

证据检查使用已经保存的上述测试截图及包含三次 ROM 运行的日志，不负责自动导航。
NAND 读取器支持 VFAT 长文件名，按提交标记和代号选择最新的完整 FTL 单元。

本页记录 v0.4 的历史测试，彼时为无声音解释器版本。v0.5 已增加原生 PCM 输出，
完整固件的音频验证见 `h1-audio.md`。尚未验证真机速度、全部 ROM、长时间稳定性或 RTC；
RTC 关闭时《绿宝石》会显示电池提示，但可以继续游戏。
