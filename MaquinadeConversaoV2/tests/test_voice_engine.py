"""Tests for Voice Engine — ElevenLabs and cache logic."""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

from core.voice_engine import VoiceEngine
from models.project import Project, Scene, VideoFormat


@pytest.fixture
def engine(tmp_path):
    with patch("core.voice_engine.ElevenLabsProvider") as mock_provider_cls:
        mock_provider = MagicMock()
        mock_provider.synthesize.return_value = b"fake_mp3_bytes"
        mock_provider_cls.return_value = mock_provider
        eng = VoiceEngine()
        eng._provider = mock_provider
        # patch projects_dir
        import config.settings as cfg
        cfg.settings.projects_dir = str(tmp_path)
        return eng


@pytest.fixture
def project_with_scenes(tmp_path):
    import config.settings as cfg
    cfg.settings.projects_dir = str(tmp_path)

    proj = Project(title="Test", niche="generico", video_format=VideoFormat.VERTICAL)
    proj.scenes = [
        Scene(id=1, order=1, script_text="Texto da cena um para teste."),
        Scene(id=2, order=2, script_text="Texto da cena dois para teste."),
    ]
    return proj


def test_generate_scene_creates_file(engine, project_with_scenes, tmp_path):
    scene = project_with_scenes.scenes[0]
    path  = engine.generate_scene(project_with_scenes, scene)
    assert path.exists()
    assert path.suffix == ".mp3"
    assert path.read_bytes() == b"fake_mp3_bytes"


def test_cache_hit_avoids_api_call(engine, project_with_scenes, tmp_path):
    scene = project_with_scenes.scenes[0]
    # First call — creates file
    path1 = engine.generate_scene(project_with_scenes, scene)
    call_count = engine._provider.synthesize.call_count

    # Second call — should use cache
    path2 = engine.generate_scene(project_with_scenes, scene)
    assert engine._provider.synthesize.call_count == call_count  # no new call
    assert scene.cache_hit is True
    assert path1 == path2


def test_estimate_cost_no_cache(engine, project_with_scenes):
    estimate = engine.estimate_cost(project_with_scenes)
    assert estimate.total_chars > 0
    assert estimate.cached_chars == 0
    assert estimate.billable_chars == estimate.total_chars
    assert estimate.cost_usd >= 0
    assert estimate.cost_brl >= 0


def test_estimate_cost_with_cache(engine, project_with_scenes):
    # Generate scene 1 to cache it
    engine.generate_scene(project_with_scenes, project_with_scenes.scenes[0])
    estimate = engine.estimate_cost(project_with_scenes)
    assert estimate.cached_chars > 0
    assert 1 in estimate.cached_scene_ids
    assert estimate.billable_chars < estimate.total_chars


def test_generate_all_updates_scene_audio_path(engine, project_with_scenes):
    paths = engine.generate_all(project_with_scenes)
    assert len(paths) == 2
    for scene in project_with_scenes.scenes:
        assert scene.audio_path is not None
        assert Path(scene.audio_path).exists()
