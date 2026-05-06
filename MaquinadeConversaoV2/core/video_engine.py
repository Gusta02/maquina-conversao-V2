"""
Video Engine — MoviePy + FFmpeg

Responsibilities:
  - Audio-driven editing: video/image duration = narration duration
  - Smart crop without distortion (center crop)
  - Multi-scene composition + final concatenation
  - Subtitle and lower-third overlay (delegated to their engines)
  - GPU AMD encoder detection (h264_amf) with CPU fallback
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Optional

import numpy as np

# ── Compatibilidade Pillow 10+ com MoviePy 1.0.3 ──────────────────────────────
# MoviePy usa PIL.Image.ANTIALIAS que foi removido no Pillow 10.0.0 (renomeado
# para LANCZOS). O patch abaixo corrige isso sem precisar alterar o MoviePy.
import PIL.Image as _pil_compat
if not hasattr(_pil_compat, "ANTIALIAS"):
    _pil_compat.ANTIALIAS = _pil_compat.LANCZOS  # type: ignore[attr-defined]

from moviepy.editor import (
    AudioFileClip,
    ColorClip,
    CompositeVideoClip,
    ImageClip,
    VideoFileClip,
    concatenate_videoclips,
)
from PIL import Image

from config import settings
from models.project import MediaType, Project, Scene, VideoFormat

logger = logging.getLogger(__name__)


def detect_gpu_encoder() -> str:
    """
    Probe FFmpeg for AMD AMF encoder availability.
    Returns 'h264_amf' if found, else falls back to 'libx264'.
    """
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=10,
        )
        if "h264_amf" in result.stdout:
            logger.info("GPU encoder detected: h264_amf (AMD AMF)")
            return "h264_amf"
    except Exception:
        pass
    logger.info("GPU encoder not found — using libx264 (CPU)")
    return "libx264"


class VideoEngine:
    """Assemble per-scene clips and concatenate into a final video."""

    def __init__(self) -> None:
        self._encoder = detect_gpu_encoder()
        logger.info("VideoEngine initialised | encoder=%s", self._encoder)

    # ── Public API ─────────────────────────────────────────────────────────────

    def render_scene(
        self,
        project: Project,
        scene: Scene,
        subtitle_frames: Optional[list] = None,   # list of (time, np.ndarray RGBA)
        lower_third_frames: Optional[list] = None,
    ) -> Path:
        """
        Render a single scene to a temporary .mp4 file.
        Returns path to the rendered scene file.
        """
        w, h = settings.resolution(project.video_format)
        audio_clip = self._load_audio(scene)
        duration = audio_clip.duration

        bg_clip = self._build_background(scene, w, h, duration)

        layers = [bg_clip]

        if subtitle_frames:
            sub_clip = self._frames_to_clip(subtitle_frames, w, h, duration)
            if sub_clip:
                layers.append(sub_clip)

        if lower_third_frames:
            lt_clip = self._frames_to_clip(lower_third_frames, w, h, duration)
            if lt_clip:
                layers.append(lt_clip)

        composite = CompositeVideoClip(layers, size=(w, h)).set_audio(audio_clip)
        composite = composite.set_duration(duration)

        out_dir = Path(settings.projects_dir) / project.uuid / "output"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"scene_{scene.id:02d}_raw.mp4"

        self._write_clip(composite, out_path)
        scene.rendered_path = str(out_path)
        scene.dirty = False

        composite.close()
        audio_clip.close()
        return out_path

    def concatenate_scenes(
        self,
        project: Project,
        scene_paths: list[Path],
        music_clip=None,
    ) -> Path:
        """
        Concatenate rendered scene clips and optionally mix in background music.
        Returns path to final video.
        """
        clips = []
        for p in scene_paths:
            if p.exists():
                clips.append(VideoFileClip(str(p)))
            else:
                logger.warning("Scene file missing: %s", p)

        if not clips:
            raise ValueError("No scene clips to concatenate")

        final = concatenate_videoclips(clips, method="chain")

        if music_clip is not None:
            final = self._mix_music(final, music_clip)

        out_dir = Path(settings.projects_dir) / project.uuid / "output"
        out_path = out_dir / f"final_{project.uuid[:8]}.mp4"

        self._write_clip(final, out_path)
        project.final_video_path = str(out_path)

        for c in clips:
            c.close()
        final.close()

        return out_path

    # ── Background builder ────────────────────────────────────────────────────

    def _build_background(
        self, scene: Scene, w: int, h: int, duration: float
    ):
        media = scene.media

        if media.media_type == MediaType.VIDEO and media.path:
            return self._video_bg(media.path, w, h, duration)

        if media.media_type == MediaType.IMAGE and media.path:
            return self._image_bg(media.path, w, h, duration)

        # No media — solid black fallback
        return ColorClip(size=(w, h), color=(0, 0, 0)).set_duration(duration)

    def _video_bg(self, path: str, w: int, h: int, duration: float):
        try:
            clip = VideoFileClip(path, audio=False)
            clip = self._smart_crop(clip, w, h)

            if clip.duration < duration:
                # Loop until we have enough footage
                repeats = int(duration / clip.duration) + 2
                from moviepy.editor import concatenate_videoclips
                clip = concatenate_videoclips([clip] * repeats)

            clip = clip.subclip(0, duration)
            return clip
        except Exception as e:
            logger.warning("Failed to load video bg %s: %s", path, e)
            return ColorClip(size=(w, h), color=(10, 10, 10)).set_duration(duration)

    def _image_bg(self, path: str, w: int, h: int, duration: float):
        try:
            # Resize/crop image to target resolution
            img = Image.open(path).convert("RGB")
            img = self._pil_smart_crop(img, w, h)
            arr = np.array(img)
            return ImageClip(arr).set_duration(duration)
        except Exception as e:
            logger.warning("Failed to load image bg %s: %s", path, e)
            return ColorClip(size=(w, h), color=(10, 10, 10)).set_duration(duration)

    # ── Crop helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _smart_crop(clip, target_w: int, target_h: int):
        """Centre-crop a MoviePy clip to target resolution without distortion."""
        from moviepy.editor import vfx
        clip_ratio = clip.w / clip.h
        target_ratio = target_w / target_h

        if clip_ratio > target_ratio:
            # Clip is wider — scale by height, then crop width
            new_h = target_h
            new_w = int(clip.w * (target_h / clip.h))
        else:
            # Clip is taller — scale by width, then crop height
            new_w = target_w
            new_h = int(clip.h * (target_w / clip.w))

        clip = clip.resize((new_w, new_h))
        x_start = (new_w - target_w) // 2
        y_start = (new_h - target_h) // 2
        return clip.crop(x1=x_start, y1=y_start, x2=x_start + target_w, y2=y_start + target_h)

    @staticmethod
    def _pil_smart_crop(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
        """Centre-crop a PIL image to target resolution."""
        img_ratio = img.width / img.height
        target_ratio = target_w / target_h

        if img_ratio > target_ratio:
            new_h = target_h
            new_w = int(img.width * (target_h / img.height))
        else:
            new_w = target_w
            new_h = int(img.height * (target_w / img.width))

        img = img.resize((new_w, new_h), Image.LANCZOS)
        left = (new_w - target_w) // 2
        top = (new_h - target_h) // 2
        return img.crop((left, top, left + target_w, top + target_h))

    # ── Overlays ──────────────────────────────────────────────────────────────

    @staticmethod
    def _frames_to_clip(frames: list, w: int, h: int, duration: float):
        """
        Convert list of (t_start, t_end, RGBA ndarray) into a transparent VideoClip.
        Alpha channel is preserved as a mask so transparent areas composite correctly.
        """
        if not frames:
            return None
        try:
            from moviepy.video.VideoClip import VideoClip

            _empty_rgb  = np.zeros((h, w, 3), dtype=np.uint8)
            _empty_mask = np.zeros((h, w), dtype=np.float64)

            def make_frame(t):
                for (t_start, t_end, arr) in frames:
                    if t_start <= t < t_end:
                        return arr[:, :, :3]
                return _empty_rgb

            def make_mask(t):
                for (t_start, t_end, arr) in frames:
                    if t_start <= t < t_end:
                        return arr[:, :, 3].astype(np.float64) / 255.0
                return _empty_mask

            clip = VideoClip(make_frame, duration=duration)
            mask = VideoClip(make_mask, duration=duration, ismask=True)
            return clip.set_mask(mask)
        except Exception as e:
            logger.warning("Could not build overlay clip: %s", e)
            return None

    # ── Audio ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _load_audio(scene: Scene):
        if not scene.audio_path or not Path(scene.audio_path).exists():
            raise FileNotFoundError(f"Audio file not found for scene {scene.id}: {scene.audio_path}")
        return AudioFileClip(scene.audio_path)

    @staticmethod
    def _mix_music(video_clip, music_clip):
        """Overlay music at configured volume, looping if necessary."""
        from moviepy.editor import CompositeAudioClip, afx
        try:
            duration = video_clip.duration
            music = music_clip.volumex(settings.music_volume)

            if music.duration < duration:
                loops = int(duration / music.duration) + 2
                from moviepy.editor import concatenate_audioclips
                music = concatenate_audioclips([music] * loops)

            music = music.subclip(0, duration)
            music = music.audio_fadein(settings.music_fade_in_sec)
            music = music.audio_fadeout(settings.music_fade_out_sec)

            if video_clip.audio:
                combined = CompositeAudioClip([video_clip.audio, music])
            else:
                combined = music

            return video_clip.set_audio(combined)
        except Exception as e:
            logger.warning("Music mix failed: %s", e)
            return video_clip

    # ── FFmpeg writer ─────────────────────────────────────────────────────────

    def _write_clip(self, clip, out_path: Path) -> None:
        ffmpeg_params = ["-crf", str(settings.video_crf)]
        if self._encoder == "libx264":
            ffmpeg_params += ["-preset", settings.video_preset]

        clip.write_videofile(
            str(out_path),
            codec=self._encoder,
            audio_codec="aac",
            fps=settings.video_fps,
            ffmpeg_params=ffmpeg_params,
            verbose=False,
            logger=None,
        )
        logger.info("Written: %s (%.1f MB)", out_path, out_path.stat().st_size / 1e6)
