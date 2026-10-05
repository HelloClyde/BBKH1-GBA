"""Build native H1 BDA with the H1 SDK packer and a GNU MIPS toolchain."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT / "vendor/h1-sdk"
CORE = ROOT / "third_party/gpsp"
GB_CORE = ROOT / "third_party/gnuboy"
GB_COMMIT = "c367bb4ba96fb07cd62f72f5ecb43aeff7012564"
GB_SOURCES = ["cpu.c", "mem.c", "hw.c", "lcd.c", "lcdc.c", "sound.c", "palette.c", "refresh.c"]
CORE_COMMIT = "69e86ebe89f14c3f5f75b809c12c0a953b3d6ce4"
SDK_COMMIT = "067fe072477861dfc8949d7b1a55279fb92d2548"
CORE_SOURCES = ["bios_data.S", "video.cc", "cpu.cc", "main.c", "gba_memory.c",
                "savestate.c", "input.c", "sound.c", "cheats.c", "memmap.c",
                "serial.c", "gbp.c", "rfu.c", "serial_proto.c", "libretro/libretro.c",
                "gba_cc_lut.c", "libretro/libretro-common/compat/compat_strl.c"]
APP_SOURCES = ["src/runtime/entry.S", "src/runtime/startup.c", "src/libc/freestanding.c",
               "src/platform/file_stream.c", "src/platform/frontend.c", "src/platform/linear_mxu.S", "src/platform/save.c",
               "src/platform/file_selector.c", "src/platform/diagnostics.c", "src/platform/audio.c", "src/platform/gba_rtc.c", "src/platform/loading.c", "src/platform/menu.c", "src/platform/state.c", "src/platform/profile.c", "src/app.c"]

def run(args, **kw):
    return subprocess.run(list(map(str, args)), check=True, **kw)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--toolchain", type=Path, default=os.environ.get("H1_GNU_BIN"))
    p.add_argument("--test-frames", type=int, default=0, help="Exit after selected ROM runs N frames (test build only)")
    p.add_argument("--core", choices=["jit", "interpreter"], default="jit")
    p.add_argument("--benchmark", action="store_true", help="Disable audio and pacing in a bounded test build")
    p.add_argument("--verbose-log", action="store_true", help="Build detailed diagnostic logging (slower)")
    p.add_argument("--profile", action="store_true", help="Collect exclusive TCU timing in RAM; dump on pause/exit")
    args = p.parse_args()
    if not args.toolchain:
        p.error("Set H1_GNU_BIN or supply --toolchain with mipsel-none-elf-gcc/g++/objcopy")
    if args.test_frames < 0 or args.test_frames > 600:
        p.error("--test-frames must be 0..600")
    if args.benchmark and not args.test_frames:
        p.error("--benchmark requires --test-frames")
    def tool(name):
        prefix = args.toolchain / ("mipsel-none-elf-" + name)
        path = prefix.with_suffix(".exe") if prefix.with_suffix(".exe").is_file() else prefix
        if not path.is_file(): p.error(f"Missing tool: {prefix}")
        return path.resolve()
    gcc, gxx, objcopy, nm = tool("gcc"), tool("g++"), tool("objcopy"), tool("nm")
    source_manifest = ROOT / 'SOURCE-REVISION.json'
    source_revisions = json.loads(source_manifest.read_text()) if source_manifest.is_file() and not (ROOT/'.git').exists() else None
    for repo, expected in [(SDK, SDK_COMMIT), (CORE, CORE_COMMIT), (GB_CORE, GB_COMMIT)]:
        if source_revisions is not None:
            if source_revisions.get(repo.relative_to(ROOT).as_posix()) != expected:
                p.error(f'Source bundle revision mismatch: {repo}')
            continue
        actual = run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        if actual != expected:
            p.error(f"Dependency revision mismatch: {repo}: {actual}")
        if run(["git", "-C", repo, "status", "--porcelain"], capture_output=True, text=True).stdout:
            p.error(f"Dependency checkout is modified: {repo}")
    build_name = f"test-{args.test_frames}" if args.test_frames else "release"
    if args.core == "interpreter": build_name += "-interpreter"
    if args.benchmark: build_name += "-benchmark"
    if args.verbose_log: build_name += "-debug"
    if args.profile: build_name += "-profile"
    build = ROOT / "build" / build_name
    build.mkdir(parents=True, exist_ok=True)
    from prepare_gpsp import prepare
    core = prepare(CORE, ROOT / ("build/gpsp-h1" if args.core == "jit" else "build/gpsp-h1-interpreter"), jit=args.core == "jit")
    core_sources = list(CORE_SOURCES)
    app_sources = list(APP_SOURCES)
    if args.core == "jit":
        core_sources.remove("memmap.c")
        core_sources += ["cpu_threaded.c", "mips/mips_stub.S"]
        app_sources += ["src/platform/jit.c", "src/platform/jit_patch.S"]
    includes = [ROOT / "src", ROOT / "src/libc/include", SDK / "sdk/include", core,
                core / "libretro", core / "libretro/libretro-common/include"]
    flags = ["-EL", "-march=mips32", "-mabi=32", "-msoft-float", "-mno-abicalls", "-G0", "-fno-pic",
             "-O2", "-ffreestanding", "-fno-builtin", "-fno-stack-protector", "-ffunction-sections",
             "-fdata-sections", "-fno-strict-aliasing", "-g0", "-Wall", "-Wextra",
             "-DROM_BUFFER_SIZE=2", "-DHAVE_NO_LANGEXTRA", f"-DH1_TEST_FRAMES={args.test_frames}",
             f"-ffile-prefix-map={ROOT}=h1-gba"]
    flags += [f"-DH1_BENCHMARK={int(args.benchmark)}"]
    flags += [f"-DH1_TRACE={int(args.verbose_log)}", f"-DH1_PROFILE={int(args.profile)}"]
    if args.core == "jit":
        flags += ["-DH1_JIT", "-DHAVE_DYNAREC", "-DMIPS_ARCH", "-DMMAP_JIT_CACHE", "-DSMALL_TRANSLATION_CACHE"]
    flags += [v for folder in includes for v in ["-I", str(folder)]]
    headers = hashlib.sha256()
    for header in sorted([*(ROOT / 'src').rglob('*.h'), *(SDK / 'sdk/include').rglob('*.h'), *core.rglob('*.h'), *GB_CORE.rglob('*.h')]):
        headers.update(header.read_bytes())
    compiler_version = run([gcc, '--version'], capture_output=True, text=True).stdout.splitlines()[0]
    objects = []
    gb_objects = []
    from prepare_gnuboy import prepare as prepare_gb
    gb_memory = prepare_gb(GB_CORE, ROOT / "build/gnuboy-h1")
    for i, source in enumerate([*(ROOT / s for s in app_sources), *(core / s for s in core_sources), *(gb_memory if s == "mem.c" else GB_CORE / s for s in GB_SOURCES), ROOT / "src/platform/gb_core.c"]):
        obj = build / f"{i:02d}-{source.stem}.o"
        if source.suffix == ".cc":
            compiler = gxx
            language = ["-std=c++17", "-fno-exceptions", "-fno-rtti", "-fno-threadsafe-statics", "-fno-use-cxa-atexit"]
        elif source.suffix == ".S":
            compiler, language = gcc, ["-x", "assembler-with-cpp"]
        else:
            compiler, language = gcc, ["-std=c11"]
        print(f"Compile {source.relative_to(ROOT)}", flush=True)
        warnings = ["-Werror"] if source.is_relative_to(ROOT / "src") else []
        compile_flags = list(flags)
        # These macros only affect the frontend. Core objects are shared by
        # test/release builds, so cache their expensive translator compilation.
        is_core = source.is_relative_to(core)
        is_gb = source.is_relative_to(GB_CORE) or source == gb_memory or source.name == "gb_core.c"
        if is_gb:
            compile_flags = ["-I", str(GB_CORE), "-I", str(ROOT / "tools/gb-include"), "-DIS_LITTLE_ENDIAN", *compile_flags]
        if is_core or is_gb:
            compile_flags = [f for f in compile_flags if not f.startswith(("-DH1_TEST_FRAMES=", "-DH1_BENCHMARK=", "-DH1_TRACE="))]
        command = [compiler, *compile_flags, *warnings, *language, "-c", source, "-o", obj]
        signature = hashlib.sha256()
        signature.update((str(compiler) + compiler_version).encode())
        signature.update(json.dumps([str(x).replace(str(core), "GPSP") for x in command[1:-2]]).encode())
        signature.update(source.read_bytes())
        signature.update(headers.digest())
        if is_gb:
            for header in sorted((ROOT / "tools/gb-include").rglob("*.h")):
                signature.update(header.read_bytes())
        cache = ROOT / 'build/object-cache' / (signature.hexdigest() + '.o')
        if cache.is_file():
            shutil.copyfile(cache, obj)
        else:
            run(command, cwd=core if source.name == "bios_data.S" else ROOT)
            cache.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(obj, cache)
        objects.append(obj)
        if is_gb: gb_objects.append(obj)
    # Prefix every GB-defined external, including its adapter helpers. libc and
    # H1 imports keep their names; gpSP globals cannot collide with gnuboy.
    symbols = set()
    for obj in gb_objects:
        output = run([nm, "--defined-only", "--extern-only", obj], capture_output=True, text=True).stdout
        for line in output.splitlines():
            name = line.split()[-1]
            if not name.startswith("h1_"): symbols.add(name)
    renames = build / "gb-symbols.txt"
    renames.write_text("".join(f"{s} h1gb_{s}\n" for s in sorted(symbols)), encoding="ascii")
    for obj in gb_objects: run([objcopy, "--redefine-syms", renames, obj])
    elf, raw = build / "H1GBA.elf", build / "H1GBA.bin"
    run([gcc, *flags, "-nostdlib", "-Wl,--build-id=none", "-Wl,--gc-sections",
         f"-Wl,-T,{ROOT / 'src/runtime/h1.ld'}", f"-Wl,-Map,{build / 'H1GBA.map'}",
         "-o", elf, *objects, "-lgcc"])
    run([objcopy, "-O", "binary", elf, raw])
    sys.path.insert(0, str(SDK))
    from h1_bda.header import HeaderFields, encode_header
    from h1_bda.resources import PAYLOAD_OFFSET, RESOURCE_OFFSET, RESOURCE_SIZES, build_icon_resources
    from h1_bda.validate import validate_bda
    payload = raw.read_bytes()
    icon = ROOT / "assets/gba-icon.png"
    resources = build_icon_resources(icon)
    size = PAYLOAD_OFFSET + len(payload)
    padding = (-size) & 3
    fields = HeaderFields(category=0x48, file_size_minus_4=size + padding - 4,
                          payload_offset=PAYLOAD_OFFSET, resource_offset=RESOURCE_OFFSET, resource_sizes=RESOURCE_SIZES)
    data = encode_header(fields, title="GameBoy", build_time="2026-10-05 00:00:00") + resources + payload + bytes(padding)
    dest = build / "H1GBA.bda"
    dest.write_bytes(data)
    report = validate_bda(dest)
    if not report["ok"]: raise RuntimeError(report)
    digest = hashlib.sha256(data).hexdigest()
    metadata = {"title": "GameBoy", "profile": args.profile, "sha256": digest, "size": len(data), "sdk_commit": SDK_COMMIT, "gpsp_commit": CORE_COMMIT,
                "entry_va": "0x83c00020", "core": args.core, "audio": "H1 native PCM 32000 Hz mono",
                "gnuboy_commit": GB_COMMIT, "formats": ["gba", "gb", "gbc"], "version": "0.12.3-linear-mxu-profile" if args.profile else "0.12.3-linear-mxu", "gba_rtc": "autodetect; H1 RTC; .rtc.s0/.rtc.s1", "benchmark": args.benchmark, "verbose_log":args.verbose_log, "log_path": "A:\\GBA\\h1gba.log",
                "rom_selector": "H1 GUI+0x9EC; native game window GUI+0x84C/+0x850",
                "pause_menu": "touch or P; calibrated coordinates GUI+0x6C0",
                "instant_state_slots": 3, "config": "per-ROM .cfg.s0/.s1",
                "display_modes": ["native", "aspect", "stretch", "aspect_linear"],
                "linear_scaler": "source intervals; packed RGB888 rows; MXU1 Q8 vertical; exact selftest; guarded state; solid runs",
                "game_input": "GUI+0x9D8; native scancode; once per core frame",
                "icon": "assets/gba-icon.png", "icon_sha256": hashlib.sha256(icon.read_bytes()).hexdigest(),
                "test_frames": args.test_frames, "compiler": run([gcc, "--version"], capture_output=True, text=True).stdout.splitlines()[0]}
    dest.with_suffix(".bda.sha256").write_text(f"{digest}  H1GBA.bda\n", encoding="ascii")
    dest.with_suffix(".build.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    if not args.test_frames:
        (ROOT / "dist").mkdir(exist_ok=True)
        for suffix in [".bda", ".bda.sha256", ".build.json"]:
            target = "H1GBA" if args.core == "jit" else "H1GBA-interpreter"
            if args.verbose_log: target += "-debug"
            if args.profile: target += "-profile"
            output = ROOT / "dist" / (target + suffix)
            if suffix == ".bda.sha256":
                output.write_text(f"{digest}  {target}.bda\n", encoding="ascii")
            else:
                shutil.copyfile(build / ("H1GBA" + suffix), output)
    print(f"PASS: {dest} ({len(data)} bytes)\nSHA256 {digest}")

if __name__ == "__main__": main()
