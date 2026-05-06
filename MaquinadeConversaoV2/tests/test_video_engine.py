"""Tests for Video Engine — crop logic and encoder detection."""
import pytest
import numpy as np
from unittest.mock import patch, MagicMock
from PIL import Image

from core.video_engine import VideoEngine, detect_gpu_encoder


def test_detect_gpu_encoder_fallback():
    """When ffmpeg doesn't have h264_amf, should return libx264."""
    with patch("core.video_engine.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="libx264 encoder", returncode=0)
        enc = detect_gpu_encoder()
        assert enc == "libx264"


def test_detect_gpu_encoder_amd():
    """When h264_amf is available, should return it."""
    with patch("core.video_engine.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="h264_amf encoder", returncode=0)
        enc = detect_gpu_encoder()
        assert enc == "h264_amf"


def test_pil_smart_crop_landscape_to_portrait():
    """16:9 image cropped to 9:16 without distortion."""
    # Create a 1920x1080 RGB image
    img = Image.new("RGB", (1920, 1080), color=(100, 150, 200))
    result = VideoEngine._pil_smart_crop(img, 1080, 1920)
    assert result.size == (1080, 1920)


def test_pil_smart_crop_portrait_to_landscape():
    """Portrait image cropped to landscape."""
    img = Image.new("RGB", (1080, 1920), color=(200, 150, 100))
    result = VideoEngine._pil_smart_crop(img, 1920, 1080)
    assert result.size == (1920, 1080)


def test_pil_smart_crop_same_ratio():
    """Same ratio — just resize."""
    img = Image.new("RGB", (640, 360), color=(50, 50, 50))
    result = VideoEngine._pil_smart_crop(img, 1920, 1080)
    assert result.size == (1920, 1080)
