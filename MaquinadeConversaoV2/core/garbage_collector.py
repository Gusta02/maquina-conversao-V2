"""
Garbage Collector — clean up temporary files after a successful Drive upload.

What gets deleted:
  - projects/{uuid}/audio/        → narration .mp3 files (minus cache entries)
  - projects/{uuid}/media/        → downloaded b-roll files
  - projects/{uuid}/output/scene_*_raw.mp4  → per-scene renders

What is KEPT:
  - projects/{uuid}/project.json
  - projects/{uuid}/output/final_*.mp4
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from config import settings
from models.project import Project

logger = logging.getLogger(__name__)


class GarbageCollector:
    """Post-upload cleanup to prevent SSD strangulation."""

    def collect(self, project: Project, dry_run: bool = False) -> dict:
        """
        Remove temporary files for a project.
        Returns stats: {'deleted_files': int, 'freed_bytes': int}
        """
        if not project.drive_link:
            logger.warning(
                "GC skipped for %s — no confirmed Drive upload", project.uuid[:8]
            )
            return {"deleted_files": 0, "freed_bytes": 0, "skipped": True}

        base = Path(settings.projects_dir) / project.uuid
        if not base.exists():
            return {"deleted_files": 0, "freed_bytes": 0, "skipped": True}

        deleted_files = 0
        freed_bytes   = 0

        targets: list[Path] = []

        # Audio directory — all files
        audio_dir = base / "audio"
        if audio_dir.exists():
            targets.extend(audio_dir.iterdir())

        # Media directory — all files
        media_dir = base / "media"
        if media_dir.exists():
            targets.extend(media_dir.iterdir())

        # Output — only per-scene raw renders, NOT final
        output_dir = base / "output"
        if output_dir.exists():
            for f in output_dir.iterdir():
                if f.name.startswith("scene_") and f.name.endswith("_raw.mp4"):
                    targets.append(f)

        for path in targets:
            if not path.is_file():
                continue
            try:
                size = path.stat().st_size
                if not dry_run:
                    path.unlink()
                    logger.debug("Deleted: %s (%.1f KB)", path.name, size / 1024)
                freed_bytes   += size
                deleted_files += 1
            except OSError as e:
                logger.warning("Could not delete %s: %s", path, e)

        label = "[DRY RUN] " if dry_run else ""
        logger.info(
            "%sGC for %s: %d files removed, %.2f MB freed",
            label, project.uuid[:8], deleted_files, freed_bytes / 1e6,
        )
        return {"deleted_files": deleted_files, "freed_bytes": freed_bytes, "dry_run": dry_run}

    def collect_all_done(self, dry_run: bool = False) -> list[dict]:
        """Run GC on all projects with status=done that still have temp files."""
        from core.project_manager import ProjectManager
        from models.project import ProjectStatus

        pm   = ProjectManager()
        done = pm.list_by_status(ProjectStatus.DONE)
        results = []

        for summary in done:
            proj = pm.load(summary["uuid"])
            if proj:
                result = self.collect(proj, dry_run=dry_run)
                result["uuid"] = proj.uuid
                results.append(result)

        return results
