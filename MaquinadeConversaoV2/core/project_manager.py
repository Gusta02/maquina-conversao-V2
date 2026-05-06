"""
Project Manager — create, load, save and list projects.

All project state lives in projects/{uuid}/project.json.
This module is the single source of truth for project lifecycle.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from config import settings
from models.project import Project, ProjectStatus, VideoFormat, MoodType, LowerThirdStyle, SubtitleStyle

logger = logging.getLogger(__name__)


class ProjectManager:
    """CRUD operations for Project state on disk."""

    def __init__(self, base_dir: Optional[str] = None) -> None:
        self.base = Path(base_dir or settings.projects_dir)
        self.base.mkdir(parents=True, exist_ok=True)

    # ── Create ─────────────────────────────────────────────────────────────────

    def create(
        self,
        title: str,
        niche: str,
        video_format: VideoFormat = VideoFormat.VERTICAL,
        mood: MoodType = MoodType.CORPORATIVO,
        lower_third_style: LowerThirdStyle = LowerThirdStyle.CORPORATE,
        subtitle_style: SubtitleStyle = SubtitleStyle.VERTICAL,
        person_name: str = "",
        person_title: str = "",
    ) -> Project:
        project = Project(
            title=title,
            niche=niche,
            video_format=video_format,
            mood=mood,
            lower_third_style=lower_third_style,
            subtitle_style=subtitle_style,
            person_name=person_name,
            person_title=person_title,
        )
        self._make_dirs(project)
        self.save(project)
        logger.info("Project created: %s (%s)", project.title, project.uuid)
        return project

    # ── Save / Load ────────────────────────────────────────────────────────────

    def save(self, project: Project) -> None:
        project.touch()
        project_file = self._project_file(project.uuid)
        project_file.parent.mkdir(parents=True, exist_ok=True)
        project_file.write_text(project.model_dump_json(indent=2), encoding="utf-8")

    def load(self, project_uuid: str) -> Optional[Project]:
        path = self._project_file(project_uuid)
        if not path.exists():
            logger.warning("Project not found: %s", project_uuid)
            return None
        try:
            return Project.model_validate_json(path.read_text(encoding="utf-8"))
        except (ValidationError, json.JSONDecodeError) as e:
            logger.error("Failed to load project %s: %s", project_uuid, e)
            return None

    # ── Update helpers ─────────────────────────────────────────────────────────

    def set_status(self, project: Project, status: ProjectStatus) -> None:
        project.status = status
        self.save(project)
        logger.info("Project %s → %s", project.uuid[:8], status.value)

    def mark_scene_dirty(self, project: Project, scene_id: int) -> None:
        for scene in project.scenes:
            if scene.id == scene_id:
                scene.dirty = True
        self.save(project)

    # ── List ───────────────────────────────────────────────────────────────────

    def list_all(self) -> list[dict]:
        """Return summary dicts for all projects, sorted by updated_at desc."""
        summaries = []
        for p in self.base.iterdir():
            if not p.is_dir():
                continue
            project_file = p / "project.json"
            if not project_file.exists():
                continue
            try:
                proj = Project.model_validate_json(project_file.read_text(encoding="utf-8"))
                summaries.append({
                    "uuid":       proj.uuid,
                    "title":      proj.title,
                    "niche":      proj.niche,
                    "status":     proj.status.value,
                    "format":     proj.video_format.value,
                    "scenes":     len(proj.scenes),
                    "updated_at": proj.updated_at.isoformat(),
                    "drive_link": proj.drive_link,
                })
            except Exception:
                continue

        return sorted(summaries, key=lambda x: x["updated_at"], reverse=True)

    def list_by_status(self, status: ProjectStatus) -> list[dict]:
        return [p for p in self.list_all() if p["status"] == status.value]

    # ── Delete ─────────────────────────────────────────────────────────────────

    def delete(self, project_uuid: str) -> bool:
        import shutil
        project_dir = self.base / project_uuid
        if project_dir.exists():
            shutil.rmtree(project_dir)
            logger.info("Project deleted: %s", project_uuid)
            return True
        return False

    # ── Internals ──────────────────────────────────────────────────────────────

    def _project_file(self, uuid: str) -> Path:
        return self.base / uuid / "project.json"

    def _make_dirs(self, project: Project) -> None:
        base = self.base / project.uuid
        for sub in ("audio", "media", "output", "subtitles"):
            (base / sub).mkdir(parents=True, exist_ok=True)
