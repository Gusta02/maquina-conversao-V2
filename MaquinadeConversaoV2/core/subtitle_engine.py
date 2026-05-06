"""
Subtitle Engine — Whisper word-level timestamps → dynamic Reels-style captions.

Styles:
  - VERTICAL:    centred, large font (72px), last word highlighted in yellow
  - HORIZONTAL:  semi-transparent bar at bottom, smaller font (52px)

Output: list of (t_start, t_end, RGBA ndarray) ready for video_engine overlay.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from config import settings
from models.project import SubtitleStyle

logger = logging.getLogger(__name__)


def _get_font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        # Windows
        r"C:\Windows\Fonts\arialbd.ttf",
        r"C:\Windows\Fonts\arial.ttf",
        # Linux
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        # macOS
        "/System/Library/Fonts/Helvetica.ttc",
        "arial.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


class SubtitleEngine:
    """Generate subtitle overlay frames from an audio file using Whisper."""

    def __init__(self) -> None:
        self._whisper_model = None  # lazy-loaded on first use

    # ── Public API ─────────────────────────────────────────────────────────────

    def generate_subtitle_frames(
        self,
        audio_path: str,
        video_w: int,
        video_h: int,
        style: SubtitleStyle = SubtitleStyle.VERTICAL,
    ) -> list[tuple[float, float, np.ndarray]]:
        """
        Transcribe audio with Whisper and return overlay frames.
        Each frame is (t_start, t_end, RGBA ndarray H×W×4).
        Returns [] on any failure — caller should use generate_frames_from_text as fallback.
        """
        try:
            words = self._transcribe(audio_path)
        except Exception as e:
            logger.error("Transcription raised uncaught exception: %s", e, exc_info=True)
            return []

        if not words:
            return []

        frames = []
        blocks = self._group_words(words, settings.subtitle_words_per_block)
        for block in blocks:
            try:
                t_start = block[0]["start"]
                t_end   = block[-1]["end"]
                texts   = [str(w.get("word") or "").strip() for w in block]
                texts   = [t for t in texts if t]
                if not texts:
                    continue
                frame = self._render_block(texts, video_w, video_h, style)
                frames.append((t_start, t_end, frame))
            except Exception as e:
                logger.warning("Block render failed (skipped): %s", e, exc_info=True)

        return frames

    def generate_frames_from_text(
        self,
        text: str,
        duration: float,
        video_w: int,
        video_h: int,
        style: SubtitleStyle = SubtitleStyle.VERTICAL,
    ) -> list[tuple[float, float, np.ndarray]]:
        """
        Generate subtitle frames from plain text without Whisper.
        Splits text into blocks and distributes them evenly across `duration`.
        Use this as a fallback when generate_subtitle_frames returns [].
        """
        tokens = text.split()
        if not tokens or duration <= 0:
            return []

        block_size = max(1, settings.subtitle_words_per_block)
        word_blocks = [tokens[i:i + block_size] for i in range(0, len(tokens), block_size)]
        if not word_blocks:
            return []

        frame_dur = duration / len(word_blocks)
        frames = []
        for i, block in enumerate(word_blocks):
            try:
                t_start = i * frame_dur
                t_end   = (i + 1) * frame_dur
                frame   = self._render_block(block, video_w, video_h, style)
                frames.append((t_start, t_end, frame))
            except Exception as e:
                logger.warning("Text block render failed (skipped): %s", e, exc_info=True)

        return frames

    # ── Transcription ─────────────────────────────────────────────────────────

    def _transcribe(self, audio_path: str) -> list[dict]:
        """
        Run Whisper and return list of word dicts with timestamps.
        All exceptions are caught and logged; returns [] on total failure.
        """
        try:
            import whisper
        except ImportError:
            logger.error("Whisper not installed — pip install openai-whisper")
            return []

        try:
            if self._whisper_model is None:
                logger.info("Loading Whisper model: %s", settings.whisper_model)
                self._whisper_model = whisper.load_model(settings.whisper_model)
        except Exception as e:
            logger.error("Failed to load Whisper model: %s", e, exc_info=True)
            return []

        logger.info("Transcribing: %s", audio_path)

        # Attempt 1: word-level timestamps (needs dtw-python)
        try:
            result = self._whisper_model.transcribe(
                audio_path,
                word_timestamps=True,
                verbose=False,
            )
            words = self._extract_word_timestamps(result)
            if words:
                logger.info("Word-level timestamps: %d words", len(words))
                return words
        except Exception as e:
            logger.warning("word_timestamps failed (%s) — falling back to segments", e)

        # Attempt 2: segment-level timestamps, words distributed evenly
        try:
            result = self._whisper_model.transcribe(
                audio_path,
                word_timestamps=False,
                verbose=False,
            )
            words = self._estimate_from_segments(result)
            logger.info("Segment-level timestamps: %d words estimated", len(words))
            return words
        except Exception as e:
            logger.error("Transcription failed completely: %s", e, exc_info=True)
            return []

    @staticmethod
    def _extract_word_timestamps(result: dict) -> list[dict]:
        words: list[dict] = []
        for segment in (result.get("segments") or []):
            for word in (segment.get("words") or []):
                text = str(word.get("word") or "").strip()
                if not text:
                    continue
                words.append({
                    "word":  text,
                    "start": float(word.get("start") or 0.0),
                    "end":   float(word.get("end") or 0.0),
                })
        return words

    @staticmethod
    def _estimate_from_segments(result: dict) -> list[dict]:
        words: list[dict] = []
        for segment in (result.get("segments") or []):
            text = str(segment.get("text") or "").strip()
            if not text:
                continue
            seg_start = float(segment.get("start") or 0.0)
            seg_end   = float(segment.get("end") or seg_start + len(text) / 15)
            tokens = text.split()
            if not tokens:
                continue
            word_dur = (seg_end - seg_start) / len(tokens)
            for i, tok in enumerate(tokens):
                words.append({
                    "word":  " " + tok,
                    "start": seg_start + i * word_dur,
                    "end":   seg_start + (i + 1) * word_dur,
                })
        return words

    # ── Frame rendering ───────────────────────────────────────────────────────

    @staticmethod
    def _group_words(words: list[dict], block_size: int) -> list[list[dict]]:
        block_size = max(1, block_size)
        return [words[i:i + block_size] for i in range(0, len(words), block_size)]

    def _render_block(
        self,
        texts: list[str],
        w: int,
        h: int,
        style: SubtitleStyle,
    ) -> np.ndarray:
        """Render one subtitle block as RGBA ndarray."""
        frame = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw  = ImageDraw.Draw(frame)

        if style == SubtitleStyle.VERTICAL:
            font_size = settings.subtitle_font_vertical_px
            y_pos = int(h * 0.78)
        else:
            font_size = settings.subtitle_font_horizontal_px
            y_pos = int(h * 0.88)

        font        = _get_font(font_size)
        font_normal = _get_font(int(font_size * 0.95))

        # Measure full block to centre horizontally
        full_text = " ".join(texts)
        try:
            bbox = draw.textbbox((0, 0), full_text, font=font)
            total_w = bbox[2] - bbox[0]
        except Exception:
            total_w = len(full_text) * (font_size // 2)

        x_cursor = (w - total_w) // 2

        if style == SubtitleStyle.HORIZONTAL:
            bar_h = font_size + 20
            bar_rect = [0, y_pos - 10, w, y_pos + bar_h]
            draw.rectangle(bar_rect, fill=(0, 0, 0, 160))

        for i, word in enumerate(texts):
            is_last = i == len(texts) - 1
            color   = (255, 220, 0, 255) if is_last else (255, 255, 255, 255)
            f       = font if is_last else font_normal

            for dx, dy in [(-2, -2), (2, -2), (-2, 2), (2, 2)]:
                draw.text((x_cursor + dx, y_pos + dy), word, font=f, fill=(0, 0, 0, 200))

            draw.text((x_cursor, y_pos), word, font=f, fill=color)

            try:
                bbox = draw.textbbox((0, 0), word + " ", font=f)
                x_cursor += bbox[2] - bbox[0]
            except Exception:
                x_cursor += len(word) * (font_size // 2) + 10

        return np.array(frame)
