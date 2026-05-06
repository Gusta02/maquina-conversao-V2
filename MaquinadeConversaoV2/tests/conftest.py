"""
Shared pytest fixtures for Máquina de Conversões tests.
All tests mock external APIs — no real API calls in CI.
"""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from models.project import Project, Scene, MediaAsset, MediaType, VideoFormat, MoodType
from models.script import Script, ScriptScene


@pytest.fixture
def sample_project(tmp_path) -> Project:
    proj = Project(
        title="Test Project",
        niche="generico",
        video_format=VideoFormat.VERTICAL,
        mood=MoodType.CORPORATIVO,
        person_name="Dr. Teste",
        person_title="CRO-SP 99999",
    )
    # Override projects dir to tmp_path
    import config.settings as cfg_mod
    cfg_mod.settings.projects_dir = str(tmp_path)
    return proj


@pytest.fixture
def sample_scene() -> Scene:
    return Scene(
        id=1,
        order=1,
        script_text="Este é um texto de teste com algumas palavras para o roteiro.",
        search_query="business professional office",
        audio_duration_sec=15.0,
        audio_path=None,
        media=MediaAsset(media_type=MediaType.NONE),
    )


@pytest.fixture
def sample_script() -> Script:
    return Script(
        raw_text="Roteiro de teste completo.",
        scenes=[
            ScriptScene(
                scene_number=1,
                text="Cena um do roteiro de teste.",
                word_count=6,
                duration_sec=2.8,
                search_query="office professional",
            ),
            ScriptScene(
                scene_number=2,
                text="Cena dois com mais texto para testar a estruturação.",
                word_count=9,
                duration_sec=4.2,
                search_query="business meeting",
            ),
        ],
        total_words=15,
        total_duration_sec=7.0,
        niche="generico",
    )
