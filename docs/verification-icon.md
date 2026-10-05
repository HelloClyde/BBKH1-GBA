# H1 GBA v0.10 图标更新验证

本次使用内置 imagegen 生成透明背景的 GBA 掌机图标，参考本机 H1 原生应用的高光圆角风格。原图和提示词位于 `assets/`，构建使用固定版本 H1 SDK 转换资源。

## 当前包

| 文件 | 字节数 | SHA-256 |
| --- | ---: | --- |
| H1GBA.bda | 975800 | `f66534cafba4c9ec6974ebad75431b2efdd5e0fc4dd33fb62a4d2659bed7e4aa` |
| H1GBA-interpreter.bda | 564764 | `293bb137cba9e914e3b5107f92b10ba174cd5780d81764283fa329d0a155066b` |
| H1GBA-debug.bda | 975800 | `65069a70d0c61ff350e881213dfc0d58683fb1669fda72ee2d74f4c6a3b61cda` |

## 检查

- 四份图标资源：45×45、57×57 RGB565+alpha，以及两份 49×60 RGB565。
- BDA 格式、资源尺寸、透明边缘、RGB565 转换和填充通过；解包预览的小尺寸 GBA 标志可读。
- 三个包的头部、文件尺寸、载荷起点及可执行载荷与 `build/v10-release/` 完全一致，只有图标资源改变；程序功能沿用 v0.10。
- 新包 SHA-256、图标原图 SHA-256 和文件名已记入对应元数据／校验文件。
- 完整 H1 V1.41 模拟器桌面已实际显示新图标，视觉检查通过；点击新图标可进入系统文件选择器、运行 GBA 游戏、打开／关闭暂停菜单并正常退出，显示错误为 0，FTL 写入记录完整。

命令：`python tools/check_app_icon.py`。报告：`build/icon-design/verification.json`；实际解包预览：`build/icon-design/packed-icons-preview.png`。

完整固件停止后核验：`python tools/check_app_icon.py --native`。桌面截图为 `build/icon-design/h1-desktop-icon.png`，运行／暂停截图与日志也在该目录。

v0.10 菜单和三核心存读档的历史功能记录见 `docs/verification-v10.md`，该记录的 SHA-256 对应图标更新前归档包；本次图标包的 SHA-256 以上表为准。真机尚未测试。
