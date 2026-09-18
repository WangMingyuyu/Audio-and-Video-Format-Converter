"""打包脚本：python build.py [--gui-only | --cli-only]

产物：
    dist/MediaConverter-GUI/MediaConverter-GUI.exe   图形界面版（无控制台窗口）
    dist/MediaConverter-CLI/MediaConverter-CLI.exe   命令行版（保留控制台）

ffmpeg 由 imageio-ffmpeg 提供，会被复制到包内的 bin/ 目录，
运行时由 ffmpeg_locator 的 BIN_DIR 规则找到（冻结后 PROJECT_ROOT = _MEIPASS）。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg

ROOT = Path(__file__).resolve().parent
FFMPEG = Path(imageio_ffmpeg.get_ffmpeg_exe())

# Miniconda/Anaconda 环境里 tcl/tk 的 DLL 放在 <env>/Library/bin，
# PyInstaller 不会自动收集，缺了它们 GUI 无法启动。
TK_DLLS = ["tcl90.dll", "tcl9tk90.dll", "libtommath.dll"]
CONDA_LIB_BIN = Path(sys.prefix) / "Library" / "bin"


def stage_ffmpeg() -> Path:
    """把 ffmpeg 复制成 bin/ffmpeg.exe，名字要对上 ffmpeg_locator 的查找规则。"""
    staged_dir = ROOT / "build" / "ffmpeg-bin"
    staged_dir.mkdir(parents=True, exist_ok=True)
    staged = staged_dir / "ffmpeg.exe"
    if not staged.is_file() or staged.stat().st_size != FFMPEG.stat().st_size:
        shutil.copyfile(FFMPEG, staged)
    return staged


def binary_args() -> list[str]:
    args = ["--add-binary", f"{stage_ffmpeg()};bin"]
    for name in TK_DLLS:
        dll = CONDA_LIB_BIN / name
        if dll.is_file():
            args += ["--add-binary", f"{dll};."]
        else:
            print(f"警告: 未找到 {dll}", flush=True)
    return args


COMMON_ARGS = [
    "--noconfirm",
    "--clean",
    "--onedir",
    *binary_args(),
    # ffmpeg 已单独打包进 bin/，不需要再带一份 imageio-ffmpeg 自带的二进制
    "--exclude-module",
    "imageio_ffmpeg",
]


def build(name: str, extra: list[str]) -> None:
    cmd = [
        sys.executable, "-m", "PyInstaller",
        *COMMON_ARGS,
        *extra,
        "--name", name,
        str(ROOT / "main.py"),
    ]
    print("$", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)
    print(f"完成: {ROOT / 'dist' / name / (name + '.exe')}", flush=True)


def main() -> int:
    only = sys.argv[1] if len(sys.argv) > 1 else ""
    if only != "--cli-only":
        build("MediaConverter-GUI", ["--windowed"])
    if only != "--gui-only":
        build("MediaConverter-CLI", ["--console"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
