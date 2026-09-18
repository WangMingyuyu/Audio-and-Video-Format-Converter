"""定位可用的 ffmpeg / ffprobe 可执行文件。

查找顺序：
1. 环境变量 FFMPEG_BINARY / FFPROBE_BINARY
2. 项目目录下的 bin/ffmpeg[.exe]
3. 系统 PATH
4. imageio-ffmpeg 自带的静态构建（需 pip install imageio-ffmpeg）
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
BIN_DIR = PROJECT_ROOT / "bin"

_cached: dict[str, str] = {}


def find_ffmpeg() -> str:
    return _find("ffmpeg")


def find_ffprobe() -> str | None:
    try:
        return _find("ffprobe")
    except FileNotFoundError:
        return None


def _find(tool: str) -> str:
    if tool in _cached:
        return _cached[tool]

    env_key = "FFMPEG_BINARY" if tool == "ffmpeg" else "FFPROBE_BINARY"
    candidates: list[str] = []

    env_val = os.environ.get(env_key)
    if env_val:
        candidates.append(env_val)

    suffix = ".exe" if sys.platform == "win32" else ""
    candidates.append(str(BIN_DIR / f"{tool}{suffix}"))

    which = shutil.which(tool)
    if which:
        candidates.append(which)

    if tool == "ffmpeg":
        try:
            import imageio_ffmpeg  # type: ignore

            candidates.append(imageio_ffmpeg.get_ffmpeg_exe())
        except Exception:
            pass

    for path in candidates:
        if path and Path(path).is_file():
            _cached[tool] = str(Path(path).resolve())
            return _cached[tool]

    raise FileNotFoundError(_help_message(tool))


def _help_message(tool: str) -> str:
    return (
        f"未找到 {tool}。请选择以下任一方式后重试：\n"
        f"  1) pip install imageio-ffmpeg（自动带一份静态 ffmpeg）\n"
        f"  2) 下载 https://ffmpeg.org/download.html 的可执行文件，放到 {BIN_DIR}\n"
        f"  3) 把 ffmpeg 所在目录加入 PATH，或设置环境变量 FFMPEG_BINARY 指向可执行文件"
    )
