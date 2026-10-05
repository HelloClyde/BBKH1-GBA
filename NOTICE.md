# Source and license notices

The H1 platform, frontend, runtime, build scripts, homebrew tests and original
icon are released under GNU GPL version 3 or (at your option) any later version.
See LICENSE. Copyright (C) 2026 HelloClyde and contributors.

`src/libc/freestanding.c` and the initial freestanding declarations were adapted
from this author's HelloClyde/BBK9588-gba, commit
`57c2792ec374b394df24c0ee898bb8624cf95a85`. The H1 adaptation is distributed under
the H1 project's GPL-3.0-or-later terms. It replaces 9588 firmware dependencies
with H1 calls. This does not change the license of the separate 9588 repository.

Third-party components retain their upstream terms and copyright notices:

- `third_party/gpsp`: libretro/gpSP at
  `69e86ebe89f14c3f5f75b809c12c0a953b3d6ce4`, GPL-2.0-or-later as stated in
  the compiled source headers. Includes libretro-common components under their
  individual notices. The open GBA BIOS is by Normmatt and the VBA/VBA-M teams;
  its source headers also allow GPL-2.0-or-later. BIOS source is included in the
  pinned checkout and full release source bundle.
- `third_party/gnuboy`: rofl0r/gnuboy at
  `c367bb4ba96fb07cd62f72f5ecb43aeff7012564`, GPL-2.0-or-later as stated in
  `main.c`'s copyright text. Retain its COPYING and CREDITS.
- `vendor/h1-sdk`: MrDefinition1999/bbk-h1-bda-sdk at
  `067fe072477861dfc8949d7b1a55279fb92d2548`, Apache License 2.0, with its
  own LICENSE and NOTICE. A copy of each is in `assets/licenses/`.
- The combined application is distributed under GPL-3.0-or-later, selecting
  GPLv3 under the upstream cores' later-version option. The SDK remains
  Apache-2.0. Compatibility reference:
  https://www.apache.org/licenses/GPL-compatibility.html .
- `src/platform/menu_font.h`: a rendered glyph subset of Noto Sans CJK SC,
  Copyright (c) 2014-2021 Adobe (http://www.adobe.com/),
  SIL Open Font License 1.1. It is separately licensed; see
  `assets/licenses/NotoSansCJK-OFL.txt` and `assets/README.md` for the exact
  font source and regeneration command. No Microsoft font or glyphs are used
  in this release.
- GNU MIPS toolchain binaries are build dependencies, not bundled with the
  application. Their GPL and runtime-library exception terms remain upstream;
  GCC 15.2.0 sources: https://ftp.gnu.org/gnu/gcc/gcc-15.2.0/ .

H1 modifications to gpSP and gnuboy are reproduced in build copies by
`tools/prepare_gpsp.py` and `tools/prepare_gnuboy.py`, retaining upstream headers.
The fixed dependency checkouts are not modified.

`assets/gba-icon.png` was generated for this project using imagegen. The original
handheld composition follows the glossy visual style of H1 applications; no
existing application's icon pixels were reused. See `assets/README.md`.

The H1 file-selector ABI was researched from the user-supplied BB虚拟机.bda
(SHA-256 f6b8c3e6df8c74b6786f1018d37610b1d6afb205e0ad8cdd07b75409ad517dac).
The touch-coordinate ABI was researched against H1 V1.41. Only interface facts
and the project-local wrappers are included; the original app implementation,
firmware, device dump, NAND, commercial ROMs and Nintendo BIOS are not supplied.

`assets/screenshots/gba-emerald-title.png` and `gba-emerald-gameplay.png` were
provided by the user and depict Pokemon Emerald (GBA). The depicted game art,
characters and marks retain their respective owners' copyright and trademark
rights; the project code's GPL license does not relicense them.
Other project verification screenshots depict the application running original
homebrew test programs. Historical screenshots and traces in the separately
licensed upstream SDK remain covered by that SDK's NOTICE.
