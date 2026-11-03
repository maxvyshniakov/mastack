#!/usr/bin/env python3
"""Transcribe screen-recorded feedback and write a timestamped timeline."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


DEFAULT_MLX_MODEL = "mlx-community/whisper-large-v3-mlx"
DEFAULT_OPENAI_WHISPER_MODEL = "small"
DEFAULT_OUT_ROOT = Path(tempfile.gettempdir()) / "video-feedback"
OUTPUT_STEM = "transcript"
DEFAULT_MIXED_UI_INITIAL_PROMPT = (
    "This is multilingual UI feedback. Keep English UI and developer terms in English. "
    "Expected terms include: button, page, layout, sidebar, toolbar, dialog, viewport, route, query, commit."
)


def run(cmd: list[str]) -> None:
    print("+ " + " ".join(shell_quote(part) for part in cmd), flush=True)
    subprocess.run(cmd, check=True)


def shell_quote(value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_./:=,@+-]+", value):
        return value
    return "'" + value.replace("'", "'\"'\"'") + "'"


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")
    return slug or "video-feedback"


def format_timestamp(seconds: float | int | None) -> str:
    if seconds is None:
        seconds = 0
    millis = int(round(float(seconds) * 1000))
    minutes, ms = divmod(millis, 60_000)
    whole_seconds, ms = divmod(ms, 1000)
    return f"{minutes:02d}:{whole_seconds:02d}.{ms:03d}"


def load_segments(json_path: Path) -> list[dict[str, object]]:
    with json_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    segments = data.get("segments", [])
    if not isinstance(segments, list):
        raise ValueError(f"Unexpected transcript JSON shape in {json_path}")
    return [segment for segment in segments if isinstance(segment, dict)]


def write_timeline(json_path: Path, timeline_path: Path, video_path: Path, model: str) -> None:
    segments = load_segments(json_path)
    lines = [
        f"# Video Feedback Transcript",
        "",
        f"Video: `{video_path}`",
        f"Model: `{model}`",
        "",
    ]

    if not segments:
        lines.append("_No speech segments detected._")
    else:
        for segment in segments:
            start = format_timestamp(segment.get("start"))
            end = format_timestamp(segment.get("end"))
            text = str(segment.get("text", "")).strip()
            if text:
                lines.append(f"- `{start} - {end}` {text}")

    timeline_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def install_help() -> str:
    return "\n".join([
        "Video feedback requires a local transcription CLI before any visual analysis.",
        "",
        "Install ffmpeg and one local transcriber:",
        "- macOS Apple Silicon: brew install ffmpeg uv && uv tool install mlx-whisper",
        "- macOS Intel: brew install ffmpeg openai-whisper",
        "- Linux: install ffmpeg with your package manager, then python3 -m pip install --user openai-whisper",
        "- Windows: winget install Gyan.FFmpeg, then py -m pip install --user openai-whisper",
        "",
        "Expected commands after install: ffmpeg plus either mlx_whisper or whisper.",
    ])


def find_transcriber(engine: str) -> tuple[str, str] | None:
    if engine in {"auto", "mlx"}:
        mlx_whisper = shutil.which("mlx_whisper")
        if mlx_whisper:
            return "mlx", mlx_whisper
    if engine in {"auto", "openai-whisper"}:
        whisper = shutil.which("whisper")
        if whisper:
            return "openai-whisper", whisper
    return None


def default_model_for_engine(engine: str) -> str:
    if engine == "mlx":
        return DEFAULT_MLX_MODEL
    return DEFAULT_OPENAI_WHISPER_MODEL


def build_whisper_command(
    *,
    engine: str,
    executable: str,
    audio_path: Path,
    out_dir: Path,
    model: str,
    language: str,
    clip_timestamps: str | None,
    verbose: str,
    initial_prompt: str | None,
) -> tuple[list[str], str]:
    if engine == "mlx":
        command = [
            executable,
            str(audio_path),
            "--model",
            model,
            "--output-dir",
            str(out_dir),
            "--output-name",
            OUTPUT_STEM,
            "--output-format",
            "all",
            "--verbose",
            verbose,
        ]
        if language != "auto":
            command.extend(["--language", language])
        if clip_timestamps:
            command.extend(["--clip-timestamps", clip_timestamps])
        if initial_prompt:
            command.extend(["--initial-prompt", initial_prompt])
        return command, OUTPUT_STEM

    command = [
        executable,
        str(audio_path),
        "--model",
        model,
        "--output_dir",
        str(out_dir),
        "--output_format",
        "all",
        "--verbose",
        verbose,
    ]
    if language != "auto":
        command.extend(["--language", language])
    if clip_timestamps:
        command.extend(["--clip_timestamps", clip_timestamps])
    if initial_prompt:
        command.extend(["--initial_prompt", initial_prompt])
    return command, audio_path.stem


def normalize_output_names(out_dir: Path, source_stem: str) -> None:
    if source_stem == OUTPUT_STEM:
        return
    for suffix in ["json", "srt", "tsv", "txt", "vtt"]:
        source = out_dir / f"{source_stem}.{suffix}"
        target = out_dir / f"{OUTPUT_STEM}.{suffix}"
        if source.exists():
            source.replace(target)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", help="Absolute or relative path to a screen recording")
    parser.add_argument(
        "--out-dir",
        type=Path,
        help="Directory for artifacts. Defaults to <temp dir>/video-feedback/<video-name>",
    )
    parser.add_argument(
        "--engine",
        choices=["auto", "mlx", "openai-whisper"],
        default="auto",
        help="Local transcription engine. Default: auto",
    )
    parser.add_argument(
        "--model",
        help=(
            "Transcription model. Defaults to mlx-community/whisper-large-v3-mlx for mlx_whisper "
            "or small for openai-whisper."
        ),
    )
    parser.add_argument(
        "--language",
        default="auto",
        help="Whisper language code such as ru, uk, or en. Default: auto",
    )
    parser.add_argument(
        "--clip-timestamps",
        help="Optional Whisper clip timestamps, e.g. 70,82 or 5.5,12.0",
    )
    parser.add_argument(
        "--mixed-ui-prompt",
        action="store_true",
        help=(
            "Use a built-in prompt for multilingual UI feedback so common "
            "developer terms are kept in English."
        ),
    )
    parser.add_argument(
        "--initial-prompt",
        help="Optional prompt passed through to Whisper for vocabulary and style hints.",
    )
    parser.add_argument(
        "--verbose",
        default="False",
        choices=["True", "False"],
        help="Pass through to mlx_whisper --verbose. Default: False",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    video_path = Path(args.video).expanduser().resolve()
    if not video_path.exists():
        print(f"Video not found: {video_path}", file=sys.stderr)
        return 2

    ffmpeg = shutil.which("ffmpeg")
    transcriber = find_transcriber(args.engine)
    if not ffmpeg or not transcriber:
        missing = []
        if not ffmpeg:
            missing.append("ffmpeg")
        if not transcriber:
            missing.append("mlx_whisper or whisper")
        print(f"Missing required local tool(s): {', '.join(missing)}", file=sys.stderr)
        print("", file=sys.stderr)
        print(install_help(), file=sys.stderr)
        return 2

    engine, transcriber_path = transcriber
    model = args.model or default_model_for_engine(engine)
    initial_prompt = args.initial_prompt
    if args.mixed_ui_prompt and not initial_prompt:
        initial_prompt = DEFAULT_MIXED_UI_INITIAL_PROMPT

    out_dir = args.out_dir or DEFAULT_OUT_ROOT / slugify(video_path.stem)
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    audio_path = out_dir / "audio.wav"
    run([
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        str(audio_path),
    ])

    whisper_cmd, output_stem = build_whisper_command(
        engine=engine,
        executable=transcriber_path,
        audio_path=audio_path,
        out_dir=out_dir,
        model=model,
        language=args.language,
        clip_timestamps=args.clip_timestamps,
        verbose=args.verbose,
        initial_prompt=initial_prompt,
    )
    run(whisper_cmd)
    normalize_output_names(out_dir, output_stem)

    json_path = out_dir / f"{OUTPUT_STEM}.json"
    timeline_path = out_dir / "timeline.md"
    if not json_path.exists():
        print(f"Expected transcript JSON was not written: {json_path}", file=sys.stderr)
        return 1
    write_timeline(json_path, timeline_path, video_path, model)

    print()
    print(f"Timeline: {timeline_path}")
    print(f"Raw JSON: {json_path}")
    print(f"SRT: {out_dir / 'transcript.srt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
