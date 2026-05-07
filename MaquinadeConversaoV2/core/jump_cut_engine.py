"""
Jump Cut Engine — remove silences from audio/video to tighten pacing.

Pipeline:
  1. detect_keep_segments(audio_path) → [(t_start, t_end), ...]
     Uses pydub to find non-silent windows (threshold -30 dBFS by default).
  2. apply_to_audio(audio_path, segments, output_path) → Path
     Exports a cut audio with all silence removed.
  3. VideoEngine calls apply_to_clip() to trim the background video in sync.

Settings (all configurable via kwargs):
  silence_thresh_db  : int   = -30   dBFS below which a frame is "silent"
  min_silence_ms     : int   = 300   ms — silence shorter than this is kept
  padding_ms         : int   = 80    ms padding kept around each kept segment
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class JumpCutEngine:
    """Detect and remove silence segments from narration audio."""

    def __init__(
        self,
        silence_thresh_db: int = -30,
        min_silence_ms: int = 300,
        padding_ms: int = 80,
    ) -> None:
        self.silence_thresh_db = silence_thresh_db
        self.min_silence_ms    = min_silence_ms
        self.padding_ms        = padding_ms

    # ── Public API ─────────────────────────────────────────────────────────────

    def detect_keep_segments(
        self, audio_path: str
    ) -> list[tuple[float, float]]:
        """
        Return list of (start_sec, end_sec) for non-silent audio windows.
        Returns a single full-duration segment on any failure (safe no-op).
        """
        try:
            from pydub import AudioSegment
            from pydub.silence import detect_nonsilent

            audio = AudioSegment.from_file(audio_path)
            duration_ms = len(audio)

            nonsilent = detect_nonsilent(
                audio,
                min_silence_len=self.min_silence_ms,
                silence_thresh=self.silence_thresh_db,
                seek_step=10,
            )

            if not nonsilent:
                logger.warning("No non-silent segments found — returning full clip")
                return [(0.0, duration_ms / 1000.0)]

            # Apply padding so cuts don't feel abrupt
            padded: list[tuple[float, float]] = []
            for start_ms, end_ms in nonsilent:
                s = max(0, start_ms - self.padding_ms) / 1000.0
                e = min(duration_ms, end_ms + self.padding_ms) / 1000.0
                padded.append((s, e))

            # Merge overlapping padded segments
            merged = self._merge_segments(padded)
            removed_ms = duration_ms - sum((e - s) * 1000 for s, e in merged)
            logger.info(
                "Jump cuts: keeping %d segments, removing %.1fs of silence",
                len(merged), removed_ms / 1000.0,
            )
            return merged

        except ImportError:
            logger.warning("pydub not installed — jump cuts disabled")
            return self._full_segment(audio_path)
        except Exception as e:
            logger.error("Jump cut detection failed: %s — skipping", e)
            return self._full_segment(audio_path)

    def apply_to_audio(
        self,
        audio_path: str,
        segments: list[tuple[float, float]],
        output_path: str,
    ) -> Path:
        """
        Export a new audio file containing only the kept segments concatenated.
        Returns output_path as Path. Falls back to the original on any error.
        """
        try:
            from pydub import AudioSegment

            audio = AudioSegment.from_file(audio_path)
            result = AudioSegment.empty()
            for start_sec, end_sec in segments:
                result += audio[int(start_sec * 1000): int(end_sec * 1000)]

            out = Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            fmt = out.suffix.lstrip(".") or "mp3"
            result.export(str(out), format=fmt)
            logger.info(
                "Jump-cut audio saved → %s (%.1fs → %.1fs)",
                out.name,
                len(audio) / 1000.0,
                len(result) / 1000.0,
            )
            return out

        except Exception as e:
            logger.error("apply_to_audio failed: %s — returning original", e)
            return Path(audio_path)

    def total_duration(self, segments: list[tuple[float, float]]) -> float:
        """Return total kept duration in seconds."""
        return sum(e - s for s, e in segments)

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _merge_segments(
        segments: list[tuple[float, float]],
    ) -> list[tuple[float, float]]:
        """Merge overlapping or adjacent segments."""
        if not segments:
            return []
        sorted_segs = sorted(segments)
        merged = [sorted_segs[0]]
        for start, end in sorted_segs[1:]:
            if start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        return merged

    @staticmethod
    def _full_segment(audio_path: str) -> list[tuple[float, float]]:
        try:
            from pydub import AudioSegment
            dur = len(AudioSegment.from_file(audio_path)) / 1000.0
        except Exception:
            dur = 999.0
        return [(0.0, dur)]
