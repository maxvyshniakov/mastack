#!/usr/bin/env python3
"""Unit tests for the video feedback transcription wrapper."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).with_name("transcribe_video_feedback.py")
SPEC = importlib.util.spec_from_file_location("transcribe_video_feedback", SCRIPT_PATH)
assert SPEC and SPEC.loader
transcribe_video_feedback = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(transcribe_video_feedback)


class TranscribeVideoFeedbackTest(unittest.TestCase):
    def test_default_mlx_model_uses_large_v3_for_mixed_feedback(self) -> None:
        self.assertEqual(
            transcribe_video_feedback.default_model_for_engine("mlx"),
            "mlx-community/whisper-large-v3-mlx",
        )

    def test_default_language_uses_auto_detection(self) -> None:
        with patch.object(transcribe_video_feedback.sys, "argv", ["transcribe_video_feedback.py", "/tmp/video.mp4"]):
            args = transcribe_video_feedback.parse_args()

        self.assertEqual(args.language, "auto")

    def test_auto_engine_prefers_installed_mlx_whisper(self) -> None:
        def fake_which(command: str) -> str | None:
            return {
                "mlx_whisper": "/usr/local/bin/mlx_whisper",
                "whisper": "/usr/local/bin/whisper",
            }.get(command)

        with patch.object(transcribe_video_feedback.shutil, "which", side_effect=fake_which):
            self.assertEqual(
                transcribe_video_feedback.find_transcriber("auto"),
                ("mlx", "/usr/local/bin/mlx_whisper"),
            )

    def test_openai_whisper_command_uses_portable_cli_flags(self) -> None:
        command, output_stem = transcribe_video_feedback.build_whisper_command(
            engine="openai-whisper",
            executable="/usr/local/bin/whisper",
            audio_path=Path("/tmp/audio.wav"),
            out_dir=Path("/tmp/out"),
            model="small",
            language="ru",
            clip_timestamps="70,82",
            verbose="False",
            initial_prompt="Keep English UI terms in English.",
        )

        self.assertEqual(output_stem, "audio")
        self.assertIn("--output_dir", command)
        self.assertIn("--clip_timestamps", command)
        self.assertIn("--initial_prompt", command)
        self.assertNotIn("--output-name", command)

    def test_mlx_whisper_command_can_use_initial_prompt(self) -> None:
        command, output_stem = transcribe_video_feedback.build_whisper_command(
            engine="mlx",
            executable="/usr/local/bin/mlx_whisper",
            audio_path=Path("/tmp/audio.wav"),
            out_dir=Path("/tmp/out"),
            model="mlx-community/whisper-large-v3-mlx",
            language="auto",
            clip_timestamps=None,
            verbose="False",
            initial_prompt="Keep English UI terms in English.",
        )

        self.assertEqual(output_stem, "transcript")
        self.assertIn("--initial-prompt", command)
        self.assertIn("Keep English UI terms in English.", command)

    def test_default_artifacts_land_in_temp_dir_outside_the_repository(self) -> None:
        self.assertEqual(
            transcribe_video_feedback.DEFAULT_OUT_ROOT,
            Path(tempfile.gettempdir()) / "video-feedback",
        )

    def test_install_help_names_required_local_tools(self) -> None:
        help_text = transcribe_video_feedback.install_help()

        self.assertIn("ffmpeg", help_text)
        self.assertIn("mlx_whisper", help_text)
        self.assertIn("whisper", help_text)
        self.assertIn("uv tool install mlx-whisper", help_text)

    def test_normalize_output_names_replaces_stale_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir)
            (out_dir / "audio.json").write_text('{"segments": []}', encoding="utf-8")
            (out_dir / "transcript.json").write_text("stale", encoding="utf-8")

            transcribe_video_feedback.normalize_output_names(out_dir, "audio")

            self.assertEqual((out_dir / "transcript.json").read_text(encoding="utf-8"), '{"segments": []}')
            self.assertFalse((out_dir / "audio.json").exists())


if __name__ == "__main__":
    unittest.main()
