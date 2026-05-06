"""Tests for Subtitle Engine — grouping and frame rendering."""
import pytest
import numpy as np
from unittest.mock import patch, MagicMock

from core.subtitle_engine import SubtitleEngine
from models.project import SubtitleStyle


@pytest.fixture
def engine():
    return SubtitleEngine()


def test_group_words_basic(engine):
    words = [{"word": f"word{i}", "start": i * 0.5, "end": (i + 1) * 0.5}
             for i in range(9)]
    groups = engine._group_words(words, 3)
    assert len(groups) == 3
    assert all(len(g) == 3 for g in groups)


def test_group_words_uneven(engine):
    words = [{"word": f"w{i}", "start": i * 0.3, "end": (i + 1) * 0.3}
             for i in range(7)]
    groups = engine._group_words(words, 3)
    assert len(groups) == 3              # 3 + 3 + 1
    assert len(groups[-1]) == 1


def test_render_block_vertical_returns_rgba(engine):
    frame = engine._render_block(["Olá", "mundo", "teste"], 1080, 1920, SubtitleStyle.VERTICAL)
    assert isinstance(frame, np.ndarray)
    assert frame.shape == (1920, 1080, 4)  # H × W × RGBA
    assert frame.dtype == np.uint8


def test_render_block_horizontal_returns_rgba(engine):
    frame = engine._render_block(["teste", "horizontal", "legenda"], 1080, 1920, SubtitleStyle.HORIZONTAL)
    assert isinstance(frame, np.ndarray)
    assert frame.shape[2] == 4  # RGBA


def test_render_block_has_yellow_last_word(engine):
    """Last word should have yellow pixels (R=255, G=220, B=0) somewhere."""
    frame = engine._render_block(["palavra", "final"], 1080, 400, SubtitleStyle.VERTICAL)
    # Yellow pixels: R > 200, G > 180, B < 50
    yellow_mask = (frame[:, :, 0] > 200) & (frame[:, :, 1] > 180) & (frame[:, :, 2] < 50)
    assert yellow_mask.any(), "No yellow pixels found for last word highlight"
