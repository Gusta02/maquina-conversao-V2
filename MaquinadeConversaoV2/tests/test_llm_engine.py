"""Tests for LLM Engine — all Groq calls are mocked."""
import json
import pytest
from unittest.mock import MagicMock, patch

from core.llm_engine import LLMEngine
from models.script import Script


@pytest.fixture
def engine():
    with patch("core.llm_engine.Groq"):
        return LLMEngine()


def test_generate_draft_returns_string(engine):
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "Roteiro de teste gerado pela IA."
    engine._client.chat.completions.create.return_value = mock_response

    result = engine.generate_draft("Direitos do inquilino", "advogado", "9:16")
    assert isinstance(result, str)
    assert len(result) > 0


def test_generate_draft_all_niches(engine):
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "Texto de roteiro."
    engine._client.chat.completions.create.return_value = mock_response

    niches = ["corretor", "advogado", "engenheiro_civil", "negocio_local",
              "clinica", "imobiliaria", "generico"]
    for niche in niches:
        result = engine.generate_draft("Tema qualquer", niche)
        assert isinstance(result, str), f"Failed for niche: {niche}"


def test_structure_script_parses_valid_json(engine):
    structured_json = json.dumps({
        "scenes": [
            {"scene_number": 1, "text": "Cena 1 do vídeo.", "word_count": 5,
             "duration_sec": 2.3, "search_query": "office business"},
            {"scene_number": 2, "text": "Cena 2 do vídeo de teste.", "word_count": 6,
             "duration_sec": 2.8, "search_query": "professional meeting"},
        ],
        "total_words": 11,
        "total_duration_sec": 5.1,
    })
    mock_response = MagicMock()
    mock_response.choices[0].message.content = structured_json
    engine._client.chat.completions.create.return_value = mock_response

    script = engine.structure_script("Texto aprovado de teste.", "generico")
    assert isinstance(script, Script)
    assert len(script.scenes) == 2
    assert script.scenes[0].scene_number == 1
    assert script.total_words == 11


def test_structure_script_strips_markdown_fences(engine):
    """LLM sometimes wraps JSON in ```json blocks — test that we strip them."""
    json_content = json.dumps({
        "scenes": [{"scene_number": 1, "text": "Teste.", "word_count": 1,
                    "duration_sec": 0.5, "search_query": "test"}],
        "total_words": 1,
        "total_duration_sec": 0.5,
    })
    wrapped = f"```json\n{json_content}\n```"
    mock_response = MagicMock()
    mock_response.choices[0].message.content = wrapped
    engine._client.chat.completions.create.return_value = mock_response

    script = engine.structure_script("Texto.", "generico")
    assert len(script.scenes) == 1


def test_count_metrics_accuracy(engine):
    text = "Uma frase de teste com dez palavras exatas aqui ok"
    metrics = engine.count_metrics(text)
    assert metrics["words"] == 10
    assert metrics["chars"] == len(text)
    assert metrics["duration_sec"] > 0


def test_structure_script_raises_on_invalid_json(engine):
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "isso não é json"
    engine._client.chat.completions.create.return_value = mock_response

    with pytest.raises(ValueError, match="invalid JSON"):
        engine.structure_script("Texto.", "generico")
