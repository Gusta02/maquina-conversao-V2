"""
Lower Thirds Engine — animated name/title overlay.

Three styles:
  CORPORATE   : dark bg panel + coloured side bar (accent colour)
  MODERN      : no background, text in accent colour
  MINIMALIST  : white text with drop shadow only

Output: list of (t_start, t_end, RGBA ndarray) — same format as subtitle_engine.
Appears in the first [lower_third_start_sec .. lower_third_end_sec] of the video.
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from config import settings, get_niche
from models.project import LowerThirdStyle, Project

logger = logging.getLogger(__name__)


def _get_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    candidates_bold = [
        # Windows
        r"C:\Windows\Fonts\arialbd.ttf",
        r"C:\Windows\Fonts\arial.ttf",
        # Linux
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        # macOS
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    candidates_normal = [
        # Windows
        r"C:\Windows\Fonts\arial.ttf",
        # Linux
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        # macOS
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for path in (candidates_bold if bold else candidates_normal):
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


class LowerThirdsEngine:
    """Generate lower-third overlay frames for a project."""

    # ── Public API ─────────────────────────────────────────────────────────────

    def generate_frames(
        self,
        project: Project,
        video_w: int,
        video_h: int,
        total_duration: float,
    ) -> list[tuple[float, float, np.ndarray]]:
        """
        Return frames list: [(t_start, t_end, RGBA ndarray), ...]
        Uses fade-in and fade-out by returning multiple near-duplicate frames
        at the boundaries with varying alpha — simplified approach for MVP.
        """
        if not project.person_name:
            return []

        niche = get_niche(project.niche)
        accent = niche.accent_color

        t_start = settings.lower_third_start_sec
        t_end   = min(settings.lower_third_end_sec, total_duration - 0.2)
        fade    = settings.lower_third_fade_sec

        # Safety: not enough duration for a meaningful lower third
        if t_end <= t_start + fade * 2:
            logger.debug("Video too short (%.2fs) for lower third — skipping", total_duration)
            return []

        frames: list[tuple[float, float, np.ndarray]] = []

        # Fade-in frames
        steps = max(int(fade * 10), 3)
        for i in range(steps):
            alpha_factor = (i + 1) / steps
            t0 = t_start + i * (fade / steps)
            t1 = t_start + (i + 1) * (fade / steps)
            arr = self._render(project, video_w, video_h, accent,
                               project.lower_third_style, alpha_factor)
            frames.append((t0, t1, arr))

        # Steady frame
        arr_full = self._render(project, video_w, video_h, accent,
                                project.lower_third_style, 1.0)
        frames.append((t_start + fade, t_end - fade, arr_full))

        # Fade-out frames
        for i in range(steps):
            alpha_factor = 1.0 - (i + 1) / steps
            t0 = t_end - fade + i * (fade / steps)
            t1 = t_end - fade + (i + 1) * (fade / steps)
            arr = self._render(project, video_w, video_h, accent,
                               project.lower_third_style, alpha_factor)
            frames.append((t0, t1, arr))

        return frames

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _render(
        self,
        project: Project,
        w: int,
        h: int,
        accent: tuple[int, int, int],
        style: LowerThirdStyle,
        alpha_factor: float,
    ) -> np.ndarray:
        frame = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw  = ImageDraw.Draw(frame)

        name_font  = _get_font(max(28, h // 40), bold=True)
        title_font = _get_font(max(20, h // 56), bold=False)

        name  = project.person_name
        title = project.person_title

        pad   = int(w * 0.04)
        y_bot = int(h * 0.82)
        bar_h = int(h * 0.09)
        y_top = y_bot - bar_h

        a = int(255 * alpha_factor)
        ar, ag, ab = accent

        if style == LowerThirdStyle.CORPORATE:
            # Dark semi-transparent background panel
            draw.rectangle([pad, y_top, pad + int(w * 0.55), y_bot],
                           fill=(10, 10, 20, int(200 * alpha_factor)))
            # Coloured left bar
            draw.rectangle([pad, y_top, pad + 6, y_bot],
                           fill=(ar, ag, ab, a))
            text_x = pad + 18
            self._draw_text(draw, name,  text_x, y_top + 8,  name_font,  (255, 255, 255, a), shadow=True)
            self._draw_text(draw, title, text_x, y_top + 8 + bar_h // 2, title_font, (200, 200, 200, a), shadow=True)

        elif style == LowerThirdStyle.MODERN:
            text_x = pad
            self._draw_text(draw, name,  text_x, y_top + 6,            name_font,  (ar, ag, ab, a), shadow=True)
            self._draw_text(draw, title, text_x, y_top + 6 + bar_h // 2, title_font, (255, 255, 255, a), shadow=True)

        else:  # MINIMALIST
            text_x = pad
            self._draw_text(draw, name,  text_x, y_top + 8,            name_font,  (255, 255, 255, a), shadow=True, shadow_strength=4)
            self._draw_text(draw, title, text_x, y_top + 8 + bar_h // 2, title_font, (200, 200, 200, a), shadow=True, shadow_strength=3)

        return np.array(frame)

    @staticmethod
    def _draw_text(
        draw: ImageDraw.ImageDraw,
        text: str,
        x: int,
        y: int,
        font: ImageFont.FreeTypeFont,
        fill: tuple,
        shadow: bool = False,
        shadow_strength: int = 2,
    ) -> None:
        if shadow:
            for dx, dy in [(-shadow_strength, -shadow_strength),
                           (shadow_strength, -shadow_strength),
                           (-shadow_strength, shadow_strength),
                           (shadow_strength, shadow_strength)]:
                draw.text((x + dx, y + dy), text, font=font,
                          fill=(0, 0, 0, min(fill[3], 180)))
        draw.text((x, y), text, font=font, fill=fill)
