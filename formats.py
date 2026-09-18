"""支持的容器格式及其默认编码器配置。"""

from __future__ import annotations

from dataclasses import dataclass

AUDIO = "audio"
VIDEO = "video"


@dataclass(frozen=True)
class FormatSpec:
    ext: str
    kind: str
    video_codec: str | None = None
    audio_codec: str | None = None
    extra: tuple[str, ...] = ()
    """附加到输出文件之前的固定参数（如 mp4 的 faststart）。"""


FORMATS: dict[str, FormatSpec] = {
    # ---- 纯音频 ----
    "mp3": FormatSpec("mp3", AUDIO, audio_codec="libmp3lame"),
    "wav": FormatSpec("wav", AUDIO, audio_codec="pcm_s16le"),
    "flac": FormatSpec("flac", AUDIO, audio_codec="flac"),
    "aac": FormatSpec("aac", AUDIO, audio_codec="aac"),
    "m4a": FormatSpec("m4a", AUDIO, audio_codec="aac"),
    "ogg": FormatSpec("ogg", AUDIO, audio_codec="libvorbis"),
    "opus": FormatSpec("opus", AUDIO, audio_codec="libopus"),
    "wma": FormatSpec("wma", AUDIO, audio_codec="wmav2"),
    # ---- 视频（可含音轨）----
    "mp4": FormatSpec("mp4", VIDEO, "libx264", "aac", ("-movflags", "+faststart")),
    "mkv": FormatSpec("mkv", VIDEO, "libx264", "aac"),
    "mov": FormatSpec("mov", VIDEO, "libx264", "aac", ("-movflags", "+faststart")),
    "flv": FormatSpec("flv", VIDEO, "libx264", "aac"),
    "webm": FormatSpec("webm", VIDEO, "libvpx-vp9", "libopus"),
    "avi": FormatSpec("avi", VIDEO, "mpeg4", "libmp3lame"),
    "wmv": FormatSpec("wmv", VIDEO, "wmv2", "wmav2"),
    "gif": FormatSpec("gif", VIDEO, "gif"),
}

# 支持 CRF 质量模式的编码器；其余编码器只能用码率控制。
CRF_CODECS = {"libx264", "libx265", "libvpx", "libvpx-vp9"}

# 需要强制 yuv420p 像素格式才能在常见播放器中正常播放的容器。
YUV420P_CONTAINERS = {"mp4", "mov", "mkv", "flv", "avi"}


def get_format(ext: str) -> FormatSpec:
    """按扩展名取格式定义，未知格式直接报错。"""
    key = ext.lower().lstrip(".")
    if key not in FORMATS:
        raise ValueError(f"不支持的格式: {ext}，可选: {', '.join(sorted(FORMATS))}")
    return FORMATS[key]


def audio_formats() -> list[str]:
    return sorted(e for e, f in FORMATS.items() if f.kind == AUDIO)


def video_formats() -> list[str]:
    return sorted(e for e, f in FORMATS.items() if f.kind == VIDEO)
