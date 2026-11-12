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


def pick_loudest_audio_stream(mean_volumes: list[float]) -> int | None:
    """Index of the audio stream with the highest mean volume (screen recorders often add a silent track)."""
    if not mean_volumes:
        return None
    return max(range(len(mean_volumes)), key=lambda i: mean_volumes[i])


def audio_extract_command(ffmpeg: str, video_path: Path, audio_path: Path, stream_index: int | None) -> list[str]:
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(video_path)]
    if stream_index is not None:
        command.extend(["-map", f"0:a:{stream_index}"])
    # Quiet voice-over recordings make Whisper loop on a hallucinated sentence; normalize first.
    command.extend(["-vn", "-af", "highpass=f=80,loudnorm", "-ac", "1", "-ar", "16000", str(audio_path)])
    return command


def audio_stream_mean_volumes(ffmpeg: str, video_path: Path) -> list[float]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return []
    probe = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", str(video_path)],
        capture_output=True, text=True,
    )
    count = len([line for line in probe.stdout.splitlines() if line.strip()])
    if count < 2:
        return []
    volumes: list[float] = []
    for i in range(count):
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-i", str(video_path), "-map", f"0:a:{i}", "-af", "volumedetect", "-f", "null", "-"],
            capture_output=True, text=True,
        )
        match = re.search(r"mean_volume:\s*(-?[0-9.]+|-inf) dB", result.stderr)
        volumes.append(float(match.group(1)) if match and match.group(1) != "-inf" else float("-inf"))
    return volumes


def looks_like_repeated_hallucination(segments: list[dict[str, object]]) -> bool:
    """True when one sentence fills most segments, Whisper's typical failure on quiet or silent audio."""
    texts = [str(segment.get("text", "")).strip().lower() for segment in segments]
    texts = [text for text in texts if text]
    if len(texts) < 3:
        return False
    most = max(texts.count(text) for text in set(texts))
    return most >= 3 and most / len(texts) >= 0.5


def has_suspect_gap(segments: list[dict[str, object]], max_gap: float = 15.0) -> bool:
    """A long hole between transcribed segments often means Whisper skipped speech it could not align."""
    previous_end = 0.0
    for segment in segments:
        start = float(segment.get("start") or 0)
        if start - previous_end > max_gap:
            return True
        previous_end = max(previous_end, float(segment.get("end") or start))
    return False


def distinct_text_length(segments: list[dict[str, object]]) -> int:
    seen: set[str] = set()
    total = 0
    for segment in segments:
        text = str(segment.get("text", "")).strip()
        if text and text not in seen:
            seen.add(text)
            total += len(text)
    return total


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
            "--condition-on-previous-text",
            "False",
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
        "--condition_on_previous_text",
        "False",
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
    volumes = audio_stream_mean_volumes(ffmpeg, video_path)
    stream_index = pick_loudest_audio_stream(volumes)
    if volumes:
        print(f"Audio streams mean volume (dB): {volumes}; using stream {stream_index}", flush=True)
    run(audio_extract_command(ffmpeg, video_path, audio_path, stream_index))

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
    first = load_segments(json_path)
    if initial_prompt and (looks_like_repeated_hallucination(first) or has_suspect_gap(first)):
        # An initial prompt can make Whisper skip or loop on quiet speech; compare with a plain run.
        print("Transcript has repeats or long gaps; comparing with a run without the initial prompt.", flush=True)
        kept = {path.name: path.read_bytes() for path in out_dir.glob(f"{OUTPUT_STEM}.*")}
        whisper_cmd, output_stem = build_whisper_command(
            engine=engine,
            executable=transcriber_path,
            audio_path=audio_path,
            out_dir=out_dir,
            model=model,
            language=args.language,
            clip_timestamps=args.clip_timestamps,
            verbose=args.verbose,
            initial_prompt=None,
        )
        run(whisper_cmd)
        normalize_output_names(out_dir, output_stem)
        second = load_segments(json_path)
        if distinct_text_length(second) < distinct_text_length(first):
            for name, data in kept.items():
                (out_dir / name).write_bytes(data)
            print("Kept the prompted transcript (more distinct text).", flush=True)
        else:
            print("Kept the transcript without the initial prompt (more distinct text).", flush=True)
    if looks_like_repeated_hallucination(load_segments(json_path)):
        print(
            "WARNING: the transcript repeats one sentence, which is how Whisper hallucinates on silent or "
            "unusable audio. Do not treat it as speech: check the audio streams and listen before concluding "
            "there is no narration.",
            file=sys.stderr,
        )
    write_timeline(json_path, timeline_path, video_path, model)

    print()
    print(f"Timeline: {timeline_path}")
    print(f"Raw JSON: {json_path}")
    print(f"SRT: {out_dir / 'transcript.srt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
