"""
Pydantic models for LLM script generation output.
"""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class ScriptScene(BaseModel):
    """One scene as returned by the LLM (Fase 2 structured output)."""
    scene_number: int
    text: str
    word_count: int             = 0
    duration_sec: float         = 0.0    # estimated at ~130 wpm
    search_query: str           = ""     # Pexels search suggestion


class Script(BaseModel):
    """Full structured script ready for pipeline processing."""
    raw_text: str               = ""
    scenes: list[ScriptScene]   = Field(default_factory=list)
    total_words: int            = 0
    total_duration_sec: float   = 0.0
    niche: str                  = ""


class CostEstimate(BaseModel):
    """ElevenLabs cost estimate before TTS generation."""
    total_chars: int            = 0
    cached_chars: int           = 0
    billable_chars: int         = 0
    cost_usd: float             = 0.0
    cost_brl: float             = 0.0
    cached_scene_ids: list[int] = Field(default_factory=list)
    usd_brl_rate: float         = 5.10   # updated at runtime if available


class HealthStatus(BaseModel):
    groq: bool          = False
    elevenlabs: bool    = False
    pexels: bool        = False
    google_drive: bool  = False
    whisper_model: Optional[str] = None
    elevenlabs_chars_remaining: Optional[int] = None
    errors: dict[str, str] = Field(default_factory=dict)

    @property
    def all_ok(self) -> bool:
        return self.groq and self.elevenlabs and self.pexels and self.google_drive
