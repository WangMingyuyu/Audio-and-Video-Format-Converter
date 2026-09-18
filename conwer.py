"""基于 ffmpeg 的媒体格式转换核心逻辑。"""

from __future__ import annotations

import re
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path

from ffmpeg_locator import find_ffmpeg
from formats import CRF_CODECS, VIDEO, YUV420P_CONTAINERS, FormatSpec, get_format

DurationRe = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")


class ConversionError(RuntimeError):
    """转换失败（输入无效、ffmpeg 返回非零、文件无法写入等）。"""


@dataclass
class MediaInfo:
    path: str
    duration: float | None
    has_video: bool
    has_audio: bool


@dataclass
class ConvertOptions:
    """转换参数；None 表示沿用格式默认值。"""

    video_codec: str | None = None
    audio_codec: str | None = None
    video_bitrate: str | None = None  # 例: "2M"
    audio_bitrate: str | None = None  # 例: "192k"
    crf: int | None = None  # 0-51，越小质量越高
    resolution: str | None = None  # 例: "1280x720"
    fps: float | None = None
    sample_rate: int | None = None  # 例: 44100
    channels: int | None = None  # 1 / 2
    background: str | None = None  # 音频转视频时的背景图
    overwrite: bool = True
    extra_args: list[str] = field(default_factory=list)


def probe(path: str | Path) -> MediaInfo:
    """读取媒体文件的时长与流信息（不依赖 ffprobe）。"""
    src = str(path)
    if not Path(src).is_file():
        raise ConversionError(f"输入文件不存在: {src}")

    proc = subprocess.run(
        [find_ffmpeg(), "-hide_banner", "-i", src],
        capture_output=True,
        text=True,
        errors="replace",
    )
    log = proc.stderr or ""

    duration = None
    match = DurationRe.search(log)
    if match:
        h, m, s = match.groups()
        duration = int(h) * 3600 + int(m) * 60 + float(s)

    return MediaInfo(
        path=src,
        duration=duration,
        has_video="Stream #" in log and "Video:" in log,
        has_audio="Stream #" in log and "Audio:" in log,
    )


def build_ffmpeg_args(
    src: str | Path,
    dst: str | Path,
    spec: FormatSpec,
    info: MediaInfo,
    options: ConvertOptions | None = None,
) -> list[str]:
    """根据输入/输出类型拼装 ffmpeg 命令行参数。"""
    options = options or ConvertOptions()
    cmd: list[str] = [find_ffmpeg(), "-hide_banner"]

    if options.overwrite:
        cmd.append("-y")
    else:
        cmd.append("-n")

    if spec.kind == VIDEO and not info.has_video:
        # 音频 -> 视频：补一路画面（纯色或静态背景图）
        cmd += _video_source_args(options, spec)
        cmd += ["-i", str(src)]
        cmd += ["-map", "0:v", "-map", "1:a", "-shortest"]
    else:
        cmd += ["-i", str(src)]

    if spec.kind == VIDEO:
        if not info.has_video and not info.has_audio:
            raise ConversionError(f"输入没有可编码的音频或视频流: {info.path}")
        cmd += _video_args(spec, options)
        if info.has_audio:
            cmd += _audio_args(spec, options)
        else:
            cmd += ["-an"]
    else:
        if not info.has_audio:
            raise ConversionError(f"输入不含音频流，无法转为 {spec.ext}: {info.path}")
        cmd += ["-vn"]
        cmd += _audio_args(spec, options)

    cmd += list(spec.extra)
    cmd += list(options.extra_args)
    cmd.append(str(dst))
    return cmd


def _video_source_args(options: ConvertOptions, spec: FormatSpec) -> list[str]:
    resolution = options.resolution or "1280x720"
    fps = options.fps or 25
    if options.background:
        return ["-loop", "1", "-i", str(options.background)]
    return ["-f", "lavfi", "-i", f"color=c=black:s={resolution}:r={fps}"]


def _video_args(spec: FormatSpec, options: ConvertOptions) -> list[str]:
    codec = options.video_codec or spec.video_codec
    if not codec:
        return []
    args = ["-c:v", codec]

    if options.crf is not None and codec in CRF_CODECS:
        args += ["-crf", str(options.crf)]
    elif options.video_bitrate:
        args += ["-b:v", options.video_bitrate]

    if options.resolution:
        args += ["-vf", f"scale={options.resolution.replace('x', ':')}"]
    if options.fps:
        args += ["-r", str(options.fps)]
    if spec.ext in YUV420P_CONTAINERS and codec != "gif":
        args += ["-pix_fmt", "yuv420p"]
    return args


def _audio_args(spec: FormatSpec, options: ConvertOptions) -> list[str]:
    codec = options.audio_codec or spec.audio_codec
    if not codec:
        return []
    args = ["-c:a", codec]
    if options.audio_bitrate:
        args += ["-b:a", options.audio_bitrate]
    if options.sample_rate:
        args += ["-ar", str(options.sample_rate)]
    if options.channels:
        args += ["-ac", str(options.channels)]
    return args


def run(
    args: list[str],
    duration: float | None = None,
    progress=None,
    log=None,
) -> None:
    """执行 ffmpeg；通过 -progress 输出回调 0~100 的进度。"""
    full_args = args[:-1] + ["-nostats", "-progress", "pipe:1", args[-1]]

    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NO_WINDOW  # 避免弹出控制台窗口

    proc = subprocess.Popen(
        full_args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        errors="replace",
        bufsize=1,
        creationflags=creationflags,
    )

    stderr_lines: list[str] = []

    def drain_stderr():
        assert proc.stderr is not None
        for line in proc.stderr:
            stderr_lines.append(line.rstrip())
            if log:
                log(line.rstrip())

    reader = threading.Thread(target=drain_stderr, daemon=True)
    reader.start()

    last_percent = [0.0]
    assert proc.stdout is not None
    for line in proc.stdout:
        if line.startswith("out_time_ms=") and progress and duration:
            try:
                micros = float(line.split("=", 1)[1])
            except ValueError:
                continue
            percent = min(micros / 1_000_000 / duration * 100, 100.0)
            if percent >= last_percent[0]:
                last_percent[0] = percent
                progress(percent)

    reader.join(timeout=5)
    returncode = proc.wait()
    if returncode != 0:
        tail = "\n".join(stderr_lines[-20:])
        raise ConversionError(f"ffmpeg 退出码 {returncode}:\n{tail}")
    if progress and last_percent[0] < 100:
        progress(100.0)


def convert(
    src: str | Path,
    dst: str | Path,
    target_format: str | None = None,
    options: ConvertOptions | None = None,
    progress=None,
    log=None,
) -> Path:
    """把 src 转成 dst。target_format 省略时按 dst 扩展名推断。"""
    source = Path(src)
    target = Path(dst)

    ext = target_format or target.suffix.lstrip(".")
    if not ext:
        raise ConversionError("无法确定输出格式，请指定扩展名或 -f/--format")
    spec = get_format(ext)
    if target.suffix.lower().lstrip(".") != spec.ext:
        target = target.with_suffix(f".{spec.ext}")

    info = probe(source)
    target.parent.mkdir(parents=True, exist_ok=True)

    args = build_ffmpeg_args(source, target, spec, info, options)
    if log:
        log(" ".join(args))
    run(args, duration=info.duration, progress=progress, log=log)
    return target
