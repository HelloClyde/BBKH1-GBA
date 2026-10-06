# GBA 应用图标

`gba-icon.png` 是用于 H1 GBA 模拟器的 RGBA 原图，使用内置 imagegen 生成。设计参考本机 H1 应用“电子图书”“宠物单词”“三步互动”“飞天影音”“黑白子”“电学实验”的图标：高光圆角底板、鲜明渐变色、立体且清楚的主体。参考图仅用于观察风格，没有复制其他应用的图标资源。

设计：紫色横版掌机、黑色十字键、两颗洋红色按钮、深色屏幕上的白色 GBA，以及蓝色玻璃质感底板。透明边缘让图标融入 H1 桌面。

生成提示词：

```text
Use case: stylized-concept. Create ONE finished raster app icon for the BBK H1 handheld's GBA emulator, as a single square icon on a genuinely transparent background. Match the aesthetic of early-2000s BBK H1 application icons: a compact glossy rounded-square tile, softly beveled edges, bright cyan-to-deep-blue glass gradient, small white sheen at the upper left, subtle tight shadow, chunky clean pictogram. The central pictogram is a recognizable purple horizontal handheld game console inspired by the Game Boy Advance silhouette, with a black D-pad on its left, two magenta round action buttons on its right, a generous dark screen in the center, and two small pill buttons beneath. Very slight three-quarter tilt, front face clearly visible, console fills most of the tile. Put large crisp white uppercase text 'GBA' (exact spelling) centered inside the dark screen. Do not add any other text. The console must remain recognizable and 'GBA' readable when the final image is reduced to 45x45 pixels. Strong silhouette and broad surfaces; prioritize clear simple shapes over fine detail. Keep the console entirely inside the rounded tile, balanced composition. Tile fills about 92% of square canvas with transparent margin outside its rounded perimeter. Retro glossy embedded-device icon, polished dimensional illustration, precise outlines, high contrast, NOT a flat modern corporate logo. No photographs, no real game characters, no Nintendo text, no extra controllers, no checkerboard background, no labels outside icon, no mockup or multiple icons. Output a single square RGBA PNG.
```

`tools/build.py` 用固定版本 SDK 的 `build_icon_resources()` 转换四份资源：45×45、57×57 的 RGB565+alpha，以及两份 49×60 的 RGB565。无需在构建时重新生成图像。`python tools/check_app_icon.py` 校验 BDA 格式、资源、透明度、SHA-256 和可执行载荷不变，并解包生成小尺寸预览。

## 菜单字体

发布使用 Noto Sans CJK SC Regular（OFL 1.1），不依赖 Windows 系统字体。
源码中 `src/platform/menu_font.h` 是 18×21 位图的字形子集，许可文本见
`licenses/NotoSansCJK-OFL.txt`。不分发原始 OTF 文件，普通构建直接使用生成头文件。
中文和英文使用 18 像素字形；统一基线，并记录每个字形的
实际前进宽度，避免大小写错位和宽字母重叠。

来源：[notofonts/noto-cjk](https://github.com/notofonts/noto-cjk)，固定提交
`f8d157532fbfaeda587e826d4cd5b21a49186f7c`，文件
`Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf`，SHA-256：
`2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b`。
字体版权与许可沿用上游，不适用项目代码的 GPL。

再生（安装 requirements.txt 中的固定 Pillow）：

```powershell
New-Item -ItemType Directory -Force .tools | Out-Null
Invoke-WebRequest 'https://raw.githubusercontent.com/notofonts/noto-cjk/f8d157532fbfaeda587e826d4cd5b21a49186f7c/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf' -OutFile .tools/NotoSansCJKsc-Regular.otf
Get-FileHash .tools/NotoSansCJKsc-Regular.otf -Algorithm SHA256
python tools/generate_menu_font.py --font .tools/NotoSansCJKsc-Regular.otf
```

`screenshots/gba-emerald-title.png` 和 `gba-emerald-gameplay.png` 为用户提供的
GBA《精灵宝可梦 绿宝石》截图，原图直接收录，没有修改。用户未附构建哈希或运行环境，
不能据此认定是特定版本的测试结果。游戏画面版权归各自权利人，不适用项目代码的 GPL。

其余截图为发布构建实测帧缓冲，来源与确切 BDA 哈希见 `docs/release-v0.12.3.md`。
各截图的 SHA-256 和来源记录在 `docs/evidence/screenshots.json`；第三方 SDK 中的截图仍遵循该 SDK 的 NOTICE。
