"""
Media Miner — Hybrid b-roll curation.

Priority order per scene:
  1. Client upload (photo or video)    — prioridade absoluta
  2. Pexels video search (3 attempts)  — fallback automático
  3. Pexels photo search               — se sem vídeo disponível
  4. MediaType.NONE                    — sinaliza ausência (video_engine cria black frame)
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Optional

import requests

from config import settings, get_niche
from models.project import Project, Scene, MediaAsset, MediaType

logger = logging.getLogger(__name__)

PEXELS_VIDEO_URL = "https://api.pexels.com/videos/search"
PEXELS_PHOTO_URL = "https://api.pexels.com/v1/search"

_HEADERS = lambda: {"Authorization": settings.pexels_api_key}  # noqa: E731


class MediaMiner:
    """Resolve b-roll media for every scene in a project."""

    # ── Public API ─────────────────────────────────────────────────────────────

    def resolve_scene(
        self,
        project: Project,
        scene: Scene,
        client_file_path: Optional[str] = None,
    ) -> MediaAsset:
        """
        Resolve media for a single scene.
        client_file_path: absolute or relative path already uploaded by operator.
        """
        media_dir = Path(settings.projects_dir) / project.uuid / "media"
        media_dir.mkdir(parents=True, exist_ok=True)

        # ── Priority 1: client upload ──────────────────────────────────────────
        if client_file_path:
            asset = self._ingest_client_file(client_file_path, scene, media_dir)
            if asset:
                logger.info("Scene %d → client media: %s", scene.id, asset.path)
                return asset

        # ── Priority 2 & 3: Pexels ────────────────────────────────────────────
        niche = get_niche(project.niche)
        queries = self._build_queries(scene.search_query, niche.pexels_search_style)

        for query in queries:
            video_asset = self._pexels_video(query, scene, media_dir)
            if video_asset:
                logger.info("Scene %d → Pexels video: %s", scene.id, video_asset.path)
                return video_asset

        # ── Priority 3: photo fallback ────────────────────────────────────────
        for query in queries:
            photo_asset = self._pexels_photo(query, scene, media_dir)
            if photo_asset:
                logger.info("Scene %d → Pexels photo: %s", scene.id, photo_asset.path)
                return photo_asset

        logger.warning("Scene %d → no media found", scene.id)
        return MediaAsset(media_type=MediaType.NONE, source="none")

    def resolve_all(
        self,
        project: Project,
        client_files: Optional[dict[int, str]] = None,
        progress_callback=None,
    ) -> list[MediaAsset]:
        """
        Resolve media for all scenes.
        client_files: {scene_id: file_path}
        Updates scene.media in place.
        """
        cf = client_files or {}
        assets: list[MediaAsset] = []
        total = len(project.scenes)

        for i, scene in enumerate(project.scenes):
            asset = self.resolve_scene(project, scene, cf.get(scene.id))
            scene.media = asset
            assets.append(asset)
            if progress_callback:
                progress_callback(i + 1, total)

        return assets

    def coverage_report(self, project: Project) -> dict:
        """Return dict with coverage statistics after resolve_all."""
        counts = {"client": 0, "pexels_video": 0, "pexels_photo": 0, "none": 0}
        for s in project.scenes:
            src = s.media.source if s.media else "none"
            counts[src] = counts.get(src, 0) + 1
        counts["total"] = len(project.scenes)
        return counts

    def search_pexels(self, query: str, n: int = 5) -> list[dict]:
        """
        Search Pexels and return up to n results (videos first, then photos).
        Each result dict: {type, thumb, download_url, duration, id}
        """
        results: list[dict] = []

        resp = self._pexels_get(
            PEXELS_VIDEO_URL,
            params={"query": query, "per_page": n, "min_width": settings.pexels_min_width},
        )
        if resp:
            for video in resp.json().get("videos", [])[:n]:
                thumbs = video.get("video_pictures", [])
                thumb = thumbs[0]["picture"] if thumbs else None
                files = sorted(
                    video.get("video_files", []),
                    key=lambda f: f.get("width", 0),
                    reverse=True,
                )
                hd = next(
                    (f for f in files if f.get("width", 0) >= settings.pexels_min_width),
                    files[0] if files else None,
                )
                if hd:
                    results.append({
                        "type": "video",
                        "thumb": thumb,
                        "download_url": hd["link"],
                        "duration": float(video.get("duration", 0)),
                        "id": video["id"],
                    })

        remaining = n - len(results)
        if remaining > 0:
            resp = self._pexels_get(
                PEXELS_PHOTO_URL,
                params={"query": query, "per_page": remaining},
            )
            if resp:
                for photo in resp.json().get("photos", [])[:remaining]:
                    results.append({
                        "type": "photo",
                        "thumb": photo["src"].get("medium"),
                        "download_url": photo["src"].get("large2x") or photo["src"]["original"],
                        "duration": None,
                        "id": photo["id"],
                    })

        return results

    def download_pexels_result(
        self, result: dict, scene: "Scene", media_dir: Path
    ) -> MediaAsset:
        """Download a user-selected Pexels result and return a MediaAsset."""
        media_id = result["id"]
        if result["type"] == "video":
            dest = media_dir / f"scene_{scene.id:02d}_pexels_{media_id}.mp4"
        else:
            dest = media_dir / f"scene_{scene.id:02d}_pexels_{media_id}.jpg"

        if not dest.exists():
            self._download_file(result["download_url"], dest)

        return MediaAsset(
            path=str(dest),
            media_type=MediaType.VIDEO if result["type"] == "video" else MediaType.IMAGE,
            duration_sec=result.get("duration"),
            source="pexels_video" if result["type"] == "video" else "pexels_photo",
        )

    # ── Internals ──────────────────────────────────────────────────────────────

    def _ingest_client_file(
        self, path_str: str, scene: Scene, media_dir: Path
    ) -> Optional[MediaAsset]:
        src = Path(path_str)
        if not src.exists():
            logger.warning("Client file not found: %s", src)
            return None

        suffix = src.suffix.lower()
        is_video = suffix in {".mp4", ".mov", ".avi", ".mkv", ".webm"}
        is_image = suffix in {".jpg", ".jpeg", ".png", ".webp"}

        if not (is_video or is_image):
            logger.warning("Unsupported file type: %s", suffix)
            return None

        dest = media_dir / f"scene_{scene.id:02d}_client{suffix}"
        if not dest.exists():
            import shutil
            shutil.copy2(src, dest)

        media_type = MediaType.VIDEO if is_video else MediaType.IMAGE
        duration = self._probe_duration(dest) if is_video else None

        return MediaAsset(
            path=str(dest),
            media_type=media_type,
            duration_sec=duration,
            source="client",
        )

    def _build_queries(self, scene_query: str, style_hint: str) -> list[str]:
        """Return up to 3 queries to try in sequence."""
        queries = []
        if scene_query:
            queries.append(scene_query)
        if style_hint:
            queries.append(style_hint)
        queries.append("business professional")  # generic fallback
        return queries[:3]

    def _pexels_video(
        self, query: str, scene: Scene, media_dir: Path
    ) -> Optional[MediaAsset]:
        try:
            resp = self._pexels_get(
                PEXELS_VIDEO_URL,
                params={
                    "query": query,
                    "per_page": settings.pexels_per_page,
                    "min_width": settings.pexels_min_width,
                    "orientation": "landscape",
                },
            )
            if resp is None:
                return None
            videos = resp.json().get("videos", [])
            if not videos:
                return None

            video = videos[0]
            # Prefer HD file
            files = sorted(
                video.get("video_files", []),
                key=lambda f: f.get("width", 0),
                reverse=True,
            )
            hd_file = next(
                (f for f in files if f.get("width", 0) >= settings.pexels_min_width),
                files[0] if files else None,
            )
            if not hd_file:
                return None

            url = hd_file["link"]
            dest = media_dir / f"scene_{scene.id:02d}_pexels_{self._short_hash(query)}.mp4"
            if not dest.exists():
                self._download_file(url, dest)

            return MediaAsset(
                path=str(dest),
                media_type=MediaType.VIDEO,
                duration_sec=float(video.get("duration", 0)),
                source="pexels_video",
            )
        except Exception as e:
            logger.warning("Pexels video search failed for '%s': %s", query, e)
            return None

    def _pexels_photo(
        self, query: str, scene: Scene, media_dir: Path
    ) -> Optional[MediaAsset]:
        try:
            resp = self._pexels_get(
                PEXELS_PHOTO_URL,
                params={"query": query, "per_page": 3, "orientation": "landscape"},
            )
            if resp is None:
                return None
            photos = resp.json().get("photos", [])
            if not photos:
                return None

            photo = photos[0]
            url = photo["src"].get("large2x") or photo["src"]["original"]
            ext = ".jpg"
            dest = media_dir / f"scene_{scene.id:02d}_pexels_{self._short_hash(query)}{ext}"
            if not dest.exists():
                self._download_file(url, dest)

            return MediaAsset(
                path=str(dest),
                media_type=MediaType.IMAGE,
                duration_sec=None,
                source="pexels_photo",
            )
        except Exception as e:
            logger.warning("Pexels photo search failed for '%s': %s", query, e)
            return None

    @staticmethod
    def _pexels_get(url: str, params: dict, max_retries: int = 3) -> Optional[requests.Response]:
        """GET request to Pexels with exponential backoff on 429."""
        import time
        for attempt in range(max_retries):
            try:
                resp = requests.get(
                    url,
                    headers=_HEADERS(),
                    params=params,
                    timeout=10,
                )
                if resp.status_code == 429:
                    wait = 2 ** attempt
                    logger.warning("Pexels rate limit (429) — retrying in %ds", wait)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp
            except requests.exceptions.HTTPError:
                return None
            except Exception as e:
                logger.warning("Pexels request error: %s", e)
                return None
        logger.warning("Pexels: max retries reached for %s", url)
        return None

    @staticmethod
    def _download_file(url: str, dest: Path) -> None:
        with requests.get(url, stream=True, timeout=30) as r:
            r.raise_for_status()
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

    @staticmethod
    def _probe_duration(path: Path) -> Optional[float]:
        try:
            import subprocess
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_format", str(path)],
                capture_output=True, text=True, timeout=10
            )
            import json
            data = json.loads(result.stdout)
            return float(data["format"].get("duration", 0))
        except Exception:
            return None

    @staticmethod
    def _short_hash(text: str) -> str:
        return hashlib.md5(text.encode()).hexdigest()[:8]
