"""
LLM Engine — Groq / LLaMA 3.3 70B

Responsibilities:
  1. Generate raw draft script (Phase 1 — human editable text)
  2. Structure approved text into JSON scenes (Phase 2 — machine-ready)
  3. Return word count, duration estimates and per-scene Pexels search queries
"""
from __future__ import annotations

import json
import logging
import time
from typing import Optional

from groq import Groq
from groq import RateLimitError, APIConnectionError, APIStatusError

from config import settings, get_niche
from models.script import Script, ScriptScene

logger = logging.getLogger(__name__)

# ── Prompts ────────────────────────────────────────────────────────────────────

_PHASE1_USER_TEMPLATE = """
Crie um roteiro para um vídeo sobre o tema: "{theme}"
Nicho: {niche_label}
Formato: {video_format} ({duration_hint})
Dores do público: {pain_points}

Instruções:
- Escreva como texto corrido sem numeração de cenas
- Inclua um gancho forte nos primeiros 5 segundos
- Termine com este CTA: {cta}
- Tom: {tone}
- Aproximadamente {target_words} palavras no total
"""

_PHASE2_USER_TEMPLATE = """
Transforme o roteiro abaixo em cenas estruturadas para produção de vídeo.

ROTEIRO APROVADO:
{approved_text}

REGRAS:
- Divida em 3 a 6 cenas balanceadas
- Cada cena deve ter entre 30 e 80 palavras
- Para cada cena gere uma search_query em INGLÊS para buscar b-roll no Pexels
  (use o estilo visual: "{search_style}")
- Calcule duration_sec estimando {wpm} palavras por minuto
- Responda SOMENTE com JSON válido, sem markdown, sem comentários

SCHEMA JSON OBRIGATÓRIO:
{{
  "scenes": [
    {{
      "scene_number": 1,
      "text": "texto da cena",
      "word_count": 45,
      "duration_sec": 20.8,
      "search_query": "modern apartment living room luxury"
    }}
  ],
  "total_words": 180,
  "total_duration_sec": 83.1
}}
"""

_TONE_MAP: dict[str, str] = {
    "corretor":        "confiante, aspiracional, direto",
    "advogado":        "sério, empático, acessível",
    "engenheiro_civil":"técnico porém acessível, inspiracional",
    "negocio_local":   "animado, próximo, descontraído",
    "clinica":         "acolhedor, confiável, educativo",
    "imobiliaria":     "aspiracional, premium",
    "generico":        "engajador, versátil",
}

_DURATION_HINT_MAP: dict[str, str] = {
    "9:16": "vídeo curto até 60 segundos para Reels / Shorts",
    "16:9": "vídeo longo de 8 a 10 minutos para YouTube",
}

_TARGET_WORDS_MAP: dict[str, int] = {
    "9:16": 120,
    "16:9": 1300,
}


class LLMEngine:
    """Wrapper around Groq API for two-phase script generation."""

    MODEL = "llama-3.3-70b-versatile"

    def __init__(self) -> None:
        self._client = Groq(api_key=settings.groq_api_key)

    # ── Public API ─────────────────────────────────────────────────────────────

    def generate_draft(
        self,
        theme: str,
        niche_key: str,
        video_format: str = "9:16",
        cta_index: int = 0,
    ) -> str:
        """
        Phase 1: Return a raw editable script as a plain string.
        No JSON, no scene splits — just human-readable copy.
        """
        niche = get_niche(niche_key)
        pain_str = "; ".join(niche.pain_points[:3])
        cta = niche.ctas[cta_index % len(niche.ctas)]

        user_msg = _PHASE1_USER_TEMPLATE.format(
            theme=theme,
            niche_label=niche.label_pt,
            video_format=video_format,
            duration_hint=_DURATION_HINT_MAP.get(video_format, "vídeo curto"),
            pain_points=pain_str,
            cta=cta,
            tone=_TONE_MAP.get(niche_key, "engajador"),
            target_words=_TARGET_WORDS_MAP.get(video_format, 120),
        )

        logger.info("Phase 1 — generating draft for niche=%s theme=%s", niche_key, theme)
        raw = self._complete(system=niche.system_prompt, user=user_msg, temperature=0.85)
        return raw.strip()

    def structure_script(
        self,
        approved_text: str,
        niche_key: str,
    ) -> Script:
        """
        Phase 2: Receive human-approved text, return a structured Script.
        The LLM is forced to respond with valid JSON only.
        """
        niche = get_niche(niche_key)

        user_msg = _PHASE2_USER_TEMPLATE.format(
            approved_text=approved_text,
            search_style=niche.pexels_search_style,
            wpm=settings.narration_words_per_min,
        )

        logger.info("Phase 2 — structuring script for niche=%s", niche_key)
        raw_json = self._complete(
            system=(
                "You are a JSON generator. Respond ONLY with valid JSON. "
                "No markdown fences, no explanations, no extra text."
            ),
            user=user_msg,
            temperature=0.2,
        )

        return self._parse_structured(raw_json, approved_text, niche_key)

    def count_metrics(self, text: str) -> dict:
        """Return word count, char count and duration estimate for a text block."""
        words = len(text.split())
        chars = len(text)
        duration_sec = round((words / settings.narration_words_per_min) * 60, 1)
        return {"words": words, "chars": chars, "duration_sec": duration_sec}

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _complete(
        self,
        system: str,
        user: str,
        temperature: float = 0.7,
        max_retries: int = 3,
    ) -> str:
        last_err: Optional[Exception] = None
        for attempt in range(max_retries):
            try:
                resp = self._client.chat.completions.create(
                    model=self.MODEL,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user",   "content": user},
                    ],
                    temperature=temperature,
                    max_tokens=4096,
                )
                return resp.choices[0].message.content or ""

            except RateLimitError as e:
                wait = 2 ** attempt
                logger.warning("Groq rate limit — waiting %ds (attempt %d)", wait, attempt + 1)
                time.sleep(wait)
                last_err = e

            except (APIConnectionError, APIStatusError) as e:
                logger.error("Groq API error: %s", e)
                raise

        raise RuntimeError(f"Groq max retries exceeded: {last_err}") from last_err

    def _parse_structured(self, raw_json: str, original_text: str, niche_key: str) -> Script:
        """Parse Phase 2 JSON output into a Script model."""
        # Strip accidental markdown fences
        clean = raw_json.strip()
        if clean.startswith("```"):
            clean = "\n".join(clean.split("\n")[1:])
        if clean.endswith("```"):
            clean = "\n".join(clean.split("\n")[:-1])
        clean = clean.strip()

        try:
            data = json.loads(clean)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse LLM JSON: %s\nRaw: %s", e, clean[:500])
            raise ValueError(f"LLM returned invalid JSON: {e}") from e

        scenes = [
            ScriptScene(
                scene_number=s["scene_number"],
                text=s["text"],
                word_count=s.get("word_count", len(s["text"].split())),
                duration_sec=s.get("duration_sec", 0.0),
                search_query=s.get("search_query", ""),
            )
            for s in data.get("scenes", [])
        ]

        return Script(
            raw_text=original_text,
            scenes=scenes,
            total_words=data.get("total_words", sum(s.word_count for s in scenes)),
            total_duration_sec=data.get("total_duration_sec", sum(s.duration_sec for s in scenes)),
            niche=niche_key,
        )
