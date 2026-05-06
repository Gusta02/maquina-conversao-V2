"""
Music Engine — automatic background music selection and mixing.

Selects a random .mp3 from assets/music/{mood}/ and returns an
AudioFileClip ready to be mixed by video_engine.
"""
from __future__ import annotations

import logging
import random
from pathlib import Path
from typing import Optional

from moviepy.editor import AudioFileClip

from config import settings
from models.project import MoodType

logger = logging.getLogger(__name__)


class MusicEngine:
    """Load and prepare background music tracks."""

    def get_track(self, mood: MoodType) -> Optional[AudioFileClip]:
        """
        Return an AudioFileClip for the given mood.
        Returns None if no tracks are available (warns but doesn't crash).
        """
        mood_dir = Path(settings.music_dir) / mood.value
        tracks = list(mood_dir.glob("*.mp3")) + list(mood_dir.glob("*.wav"))

        if not tracks:
            logger.warning(
                "No music tracks found in %s — proceeding without background music",
                mood_dir,
            )
            return None

        chosen = random.choice(tracks)
        logger.info("Music track selected: %s", chosen.name)

        try:
            return AudioFileClip(str(chosen))
        except Exception as e:
            logger.error("Failed to load music track %s: %s", chosen, e)
            return None

    def available_moods(self) -> dict[str, int]:
        """Return dict of mood_name → track count for UI display."""
        result = {}
        for mood in MoodType:
            d = Path(settings.music_dir) / mood.value
            count = len(list(d.glob("*.mp3"))) + len(list(d.glob("*.wav")))
            result[mood.value] = count
        return result
