"""
Pydantic models for Project and Scene state.
These are the source of truth for project.json on disk.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class ProjectStatus(str, Enum):
    CREATED   = "created"
    SCRIPTED  = "scripted"
    VOICED    = "voiced"
    MEDIA     = "media_ready"
    RENDERED  = "rendered"
    UPLOADED  = "uploaded"
    DONE      = "done"
    ERROR     = "error"


class VideoFormat(str, Enum):
    HORIZONTAL = "16:9"   # 1920x1080 – YouTube long
    VERTICAL   = "9:16"   # 1080x1920 – Reels / Shorts


class MediaType(str, Enum):
    VIDEO  = "video"
    IMAGE  = "image"
    NONE   = "none"


class LowerThirdStyle(str, Enum):
    CORPORATE   = "corporate"
    MODERN      = "modern"
    MINIMALIST  = "minimalist"


class SubtitleStyle(str, Enum):
    VERTICAL    = "vertical"    # centred, 72px
    HORIZONTAL  = "horizontal"  # semi-transparent bar, 52px


class MoodType(str, Enum):
    CORPORATIVO = "corporativo"
    ENERGETICO  = "energetico"
    EMOCIONAL   = "emocional"
    EPICO       = "epico"


class MediaAsset(BaseModel):
    path: Optional[str]  = None
    media_type: MediaType = MediaType.NONE
    duration_sec: Optional[float] = None
    source: str = "none"            # "client" | "pexels" | "photo"


class Scene(BaseModel):
    id: int
    order: int
    script_text: str               = ""
    search_query: str              = ""
    audio_path: Optional[str]      = None
    audio_duration_sec: float      = 0.0
    media: MediaAsset              = Field(default_factory=MediaAsset)
    subtitle_path: Optional[str]   = None
    rendered_path: Optional[str]   = None
    dirty: bool                    = True   # needs re-render?
    cache_hit: bool                = False  # TTS was cached?


class Project(BaseModel):
    uuid: str               = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str              = "Sem título"
    niche: str              = "generico"
    video_format: VideoFormat = VideoFormat.VERTICAL
    status: ProjectStatus   = ProjectStatus.CREATED
    mood: MoodType          = MoodType.CORPORATIVO
    lower_third_style: LowerThirdStyle = LowerThirdStyle.CORPORATE
    subtitle_style: SubtitleStyle      = SubtitleStyle.VERTICAL
    person_name: str        = ""
    person_title: str       = ""
    scenes: list[Scene]     = Field(default_factory=list)
    final_video_path: Optional[str]  = None
    drive_link: Optional[str]        = None
    drive_file_id: Optional[str]     = None
    total_cost_usd: float   = 0.0
    total_cost_brl: float   = 0.0
    created_at: datetime    = Field(default_factory=datetime.utcnow)
    updated_at: datetime    = Field(default_factory=datetime.utcnow)

    def project_dir(self, base: str = "projects") -> Path:
        return Path(base) / self.uuid

    def touch(self) -> None:
        self.updated_at = datetime.utcnow()
