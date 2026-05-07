"""
Voice Engine — ElevenLabs TTS with smart SHA-256 hash cache.

Flow:
  1. estimate_cost()   → CostEstimate (call before generating)
  2. generate_scene()  → Path to .mp3 file
  3. generate_all()    → list[Path] for a full project

Cache key = SHA-256(text + voice_id + model)
If cache hit → return cached path, no API call.
"""
from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path
from typing import Optional

from elevenlabs import ElevenLabs
from elevenlabs.core import ApiError

from config import settings, get_niche
from models.project import Project, Scene
from models.script import CostEstimate

logger = logging.getLogger(__name__)


class BaseTTSProvider:
    """Abstract interface — swap provider via settings.tts_provider."""

    def synthesize(self, text: str, voice_id: str) -> bytes:
        raise NotImplementedError


class ElevenLabsProvider(BaseTTSProvider):
    def __init__(self) -> None:
        self._client = ElevenLabs(api_key=settings.elevenlabs_api_key)

    def synthesize(self, text: str, voice_id: str) -> bytes:
        audio = self._client.text_to_speech.convert(
            voice_id=voice_id,
            text=text,
            model_id=settings.elevenlabs_model,
            output_format="mp3_44100_128",
        )
        # elevenlabs SDK returns a generator of bytes chunks
        if hasattr(audio, "__iter__"):
            return b"".join(audio)
        return audio  # type: ignore


class EdgeTTSProvider(BaseTTSProvider):
    """Microsoft edge-tts — gratuito, sem API key, alta qualidade pt-BR."""

    def synthesize(self, text: str, voice_id: str) -> bytes:
        import asyncio
        import edge_tts  # pip install edge-tts

        async def _run() -> bytes:
            communicate = edge_tts.Communicate(text, voice_id)
            chunks: list[bytes] = []
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    chunks.append(chunk["data"])
            return b"".join(chunks)

        # Cria sempre um loop novo para evitar conflito com o event loop do Streamlit
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_run())
        finally:
            loop.close()


class GoogleCloudTTSProvider(BaseTTSProvider):
    """Stub — implement with google-cloud-texttospeech in future sprint."""

    def synthesize(self, text: str, voice_id: str) -> bytes:
        raise NotImplementedError("Google Cloud TTS provider not yet implemented")


_PROVIDERS: dict[str, type[BaseTTSProvider]] = {
    "elevenlabs":  ElevenLabsProvider,
    "edge_tts":    EdgeTTSProvider,
    "google_cloud": GoogleCloudTTSProvider,
}


class VoiceEngine:
    """Handles TTS generation with intelligent caching."""

    def __init__(self) -> None:
        provider_cls = _PROVIDERS.get(settings.tts_provider, ElevenLabsProvider)
        self._provider: BaseTTSProvider = provider_cls()

    # ── Public API ─────────────────────────────────────────────────────────────

    def estimate_cost(self, project: Project) -> CostEstimate:
        """
        Calculate ElevenLabs cost before generating any audio.
        Deducts cached scenes from the billable total.
        """
        voice_id = self._voice_id(project)
        total_chars = 0
        cached_chars = 0
        cached_ids: list[int] = []

        for scene in project.scenes:
            text = scene.script_text
            chars = len(text)
            total_chars += chars
            cache_path = self._cache_path(project, scene.id, text, voice_id)
            if cache_path.exists():
                cached_chars += chars
                cached_ids.append(scene.id)

        billable = total_chars - cached_chars
        cost_usd = (billable / 1000) * settings.elevenlabs_price_per_1k
        cost_brl = cost_usd * settings.usd_brl_rate

        return CostEstimate(
            total_chars=total_chars,
            cached_chars=cached_chars,
            billable_chars=billable,
            cost_usd=round(cost_usd, 4),
            cost_brl=round(cost_brl, 2),
            cached_scene_ids=cached_ids,
            usd_brl_rate=settings.usd_brl_rate,
        )

    def _voice_id(self, project: Project) -> str:
        """
        Return the correct voice ID for the current TTS provider.
        Priority (ElevenLabs): ELEVENLABS_VOICE_ID_Adam → ELEVENLABS_VOICE_ID_DEFAULT → niche voice
        """
        niche = get_niche(project.niche)
        if isinstance(self._provider, EdgeTTSProvider):
            return niche.edge_tts_voice
        # ElevenLabs: override global via .env tem prioridade sobre o nicho
        override = settings.elevenlabs_voice_id_adam or settings.elevenlabs_voice_id_default
        return override if override else niche.voice_id

    def generate_scene(
        self,
        project: Project,
        scene: Scene,
        retries: int = 3,
    ) -> Path:
        """
        Generate TTS audio for a single scene.
        Returns Path to .mp3 file (cached or freshly generated).
        """
        voice_id = self._voice_id(project)
        text = scene.script_text
        cache_path = self._cache_path(project, scene.id, text, voice_id)

        if cache_path.exists():
            logger.info("TTS cache hit — scene %d", scene.id)
            scene.cache_hit = True
            return cache_path

        logger.info("Generating TTS — scene %d (%d chars)", scene.id, len(text))

        audio_bytes = self._synthesize_with_retry(text, voice_id, retries)

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(audio_bytes)
        logger.info("TTS saved → %s", cache_path)
        scene.cache_hit = False
        return cache_path

    def generate_all(
        self,
        project: Project,
        progress_callback=None,
    ) -> list[Path]:
        """
        Generate TTS for all scenes in a project.
        Updates scene.audio_path on each scene.
        progress_callback(scene_id, total) if provided.
        """
        paths: list[Path] = []
        total = len(project.scenes)

        for i, scene in enumerate(project.scenes):
            path = self.generate_scene(project, scene)
            scene.audio_path = str(path)
            # Update actual duration so subtitle/lower-third timing is accurate
            try:
                from moviepy.editor import AudioFileClip as _AC
                scene.audio_duration_sec = _AC(str(path)).duration
            except Exception:
                pass  # keep LLM estimate on failure
            paths.append(path)
            if progress_callback:
                progress_callback(i + 1, total)

        return paths

    # ── Internals ──────────────────────────────────────────────────────────────

    def _cache_key(self, text: str, voice_id: str) -> str:
        payload = f"{text}||{voice_id}||{settings.elevenlabs_model}"
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def _cache_path(self, project: Project, scene_id: int, text: str, voice_id: str) -> Path:
        key = self._cache_key(text, voice_id)
        audio_dir = Path(settings.projects_dir) / project.uuid / "audio"
        return audio_dir / f"scene_{scene_id:02d}_{key}.mp3"

    def _synthesize_with_retry(self, text: str, voice_id: str, retries: int) -> bytes:
        last_err: Optional[Exception] = None
        for attempt in range(retries):
            try:
                return self._provider.synthesize(text, voice_id)
            except ApiError as e:
                if getattr(e, "status_code", None) == 402:
                    raise RuntimeError(
                        "ElevenLabs requer plano pago para esta voz. "
                        "Mude TTS_PROVIDER=edge_tts no arquivo .env e reinicie o app."
                    ) from e
                if "quota" in str(e).lower() or "429" in str(e):
                    wait = 5 * (attempt + 1)
                    logger.warning("ElevenLabs quota/rate — waiting %ds", wait)
                    time.sleep(wait)
                    last_err = e
                else:
                    raise
            except Exception as e:
                logger.error("TTS error: %s", e)
                raise
        raise RuntimeError(f"TTS max retries exceeded: {last_err}") from last_err
