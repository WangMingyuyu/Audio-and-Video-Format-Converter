"Media Converter —— 音频 / 视频文件格式互转工具。"
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import converter
from formats import FORMATS, audio_formats, get_format, video_formats

SUPPORTED_INPUT_EXT = set(FORMATS) | {
    "3gp",
    "amr",
    "ape",
    "asf",
    "m4v",
    "mpg",
    "mpeg",
    "rm",
    "rmvb",
    "ts",
    "vob",
    "webm",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="音频、视频文件格式相互转换工具（基于 ffmpeg）",
    )
    parser.add_argument("--version", action="version", version="Media Converter 1.0")
    sub = parser.add_subparsers(dest="command", required=False)

    p_info = sub.add_parser("info", help="查看媒体文件信息")
    p_info.add_argument("input", help="输入文件")

    p_conv = sub.add_parser("convert", help="转换单个或多个文件")
    p_conv.add_argument("inputs", nargs="+", help="输入文件（可多个）")
    p_conv.add_argument("-o", "--output", required=True, help="输出文件或目录")
    p_conv.add_argument("-f", "--format", help="目标格式（默认按输出文件扩展名推断）")
    p_conv.add_argument("--video-codec")
    p_conv.add_argument("--audio-codec")
    p_conv.add_argument("--video-bitrate", help="视频码率，如 2M")
    p_conv.add_argument("--audio-bitrate", help="音频码率，如 192k")
    p_conv.add_argument("--crf", type=int, help="恒定质量因子 0-51（x264/x265/vp9，越小越好）")
    p_conv.add_argument("--resolution", help="输出分辨率，如 1280x720")
    p_conv.add_argument("--fps", type=float)
    p_conv.add_argument("--sample-rate", type=int, help="采样率，如 44100")
    p_conv.add_argument("--channels", type=int, choices=[1, 2], help="声道数")
    p_conv.add_argument("--background", help="音频转视频时使用的背景图片")
    p_conv.add_argument("--no-overwrite", action="store_true", help="不覆盖已存在文件")

    p_batch = sub.add_parser("batch", help="批量转换整个目录")
    p_batch.add_argument("input_dir")
    p_batch.add_argument("-o", "--output", required=True, help="输出目录")
    p_batch.add_argument("-f", "--format", required=True, help="目标格式")
    p_batch.add_argument("--recursive", action="store_true", help="递归子目录")
    p_batch.add_argument("--audio-bitrate")
    p_batch.add_argument("--video-bitrate")
    p_batch.add_argument("--crf", type=int)
    p_batch.add_argument("--resolution")
    p_batch.add_argument("--sample-rate", type=int)
    p_batch.add_argument("--channels", type=int, choices=[1, 2])
    p_batch.add_argument("--no-overwrite", action="store_true")

    sub.add_parser("gui", help="启动图形界面")
    return parser


def options_from_args(args: argparse.Namespace) -> converter.ConvertOptions:
    return converter.ConvertOptions(
        video_codec=getattr(args, "video_codec", None),
        audio_codec=getattr(args, "audio_codec", None),
        video_bitrate=getattr(args, "video_bitrate", None),
        audio_bitrate=getattr(args, "audio_bitrate", None),
        crf=getattr(args, "crf", None),
        resolution=getattr(args, "resolution", None),
        fps=getattr(args, "fps", None),
        sample_rate=getattr(args, "sample_rate", None),
        channels=getattr(args, "channels", None),
        background=getattr(args, "background", None),
        overwrite=not getattr(args, "no_overwrite", False),
    )


def _print_progress(percent: float) -> None:
    width = 30
    filled = int(width * percent / 100)
    bar = "#" * filled + "-" * (width - filled)
    print(f"\r[{bar}] {percent:5.1f}%", end="", flush=True)
    if percent >= 100:
        print()


def cmd_info(args: argparse.Namespace) -> int:
    info = converter.probe(args.input)
    kind = []
    if info.has_video:
        kind.append("视频")
    if info.has_audio:
        kind.append("音频")
    print(f"文件: {info.path}")
    print(f"包含: {' + '.join(kind) or '未知'}")
    if info.duration is not None:
        m, s = divmod(int(info.duration), 60)
        print(f"时长: {m:02d}:{s:02d} ({info.duration:.2f}s)")
    return 0


def cmd_convert(args: argparse.Namespace) -> int:
    options = options_from_args(args)
    output = Path(args.output)
    multi = len(args.inputs) > 1 or output.is_dir() or output.suffix == ""

    if multi and not args.format:
        print("多个文件转换时请用 -f/--format 指定目标格式", file=sys.stderr)
        return 1

    for src in args.inputs:
        source = Path(src)
        if multi:
            dst = output / f"{source.stem}.{args.format.lstrip('.')}"
        else:
            dst = output
        try:
            print(f"-> {source.name} => {dst}")
            result = converter.convert(
                source, dst, args.format, options, progress=_print_progress
            )
            print(f"完成: {result}")
        except (converter.ConversionError, ValueError) as exc:
            print(f"失败: {source.name}: {exc}", file=sys.stderr)
    return 0


def cmd_batch(args: argparse.Namespace) -> int:
    source_dir = Path(args.input_dir)
    if not source_dir.is_dir():
        print(f"目录不存在: {source_dir}", file=sys.stderr)
        return 1
    spec = get_format(args.format)
    options = options_from_args(args)
    output_dir = Path(args.output)

    pattern = "**/*" if args.recursive else "*"
    files = [
        p
        for p in source_dir.glob(pattern)
        if p.is_file() and p.suffix.lower().lstrip(".") in SUPPORTED_INPUT_EXT
    ]
    if not files:
        print("目录中没有可转换的媒体文件", file=sys.stderr)
        return 1

    print(f"共 {len(files)} 个文件 -> {spec.ext}")
    ok = fail = 0
    for index, src in enumerate(files, 1):
        relative = src.relative_to(source_dir).with_suffix(f".{spec.ext}")
        dst = output_dir / relative
        print(f"[{index}/{len(files)}] {src.name}")
        try:
            converter.convert(src, dst, spec.ext, options, progress=_print_progress)
            ok += 1
        except (converter.ConversionError, ValueError) as exc:
            fail += 1
            print(f"  失败: {exc}", file=sys.stderr)
    print(f"完成 {ok} 个，失败 {fail} 个，输出目录: {output_dir}")
    return 0 if fail == 0 else 1


def _format_help() -> str:
    return f"音频: {', '.join(audio_formats())}\n视频: {', '.join(video_formats())}"


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command in (None, "gui"):
        from gui import launch

        return launch()

    if args.command == "info":
        return cmd_info(args)
    if args.command == "convert":
        if args.format:
            get_format(args.format)
        return cmd_convert(args)
    if args.command == "batch":
        return cmd_batch(args)

    parser.print_help()
    print("\n支持的格式：\n" + _format_help())
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n已取消", file=sys.stderr)
        sys.exit(130)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)
