"""
Global application settings loaded from environment / .env file.
All paths and tunable parameters live here — never hard-coded elsewhere.
"""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── API Keys ───────────────────────────────────────────────────────────────
    groq_api_key: str               = ""
    elevenlabs_api_key: str         = ""
    pexels_api_key: str             = ""
    google_service_account_file: str = "service_account.json"
    google_drive_folder_id: str     = ""

    # ── TTS ────────────────────────────────────────────────────────────────────
    tts_provider: str               = "elevenlabs"  # elevenlabs | edge_tts | google_cloud
    elevenlabs_model: str           = "eleven_multilingual_v2"
    elevenlabs_price_per_1k: float  = 0.18          # USD per 1 000 chars
    usd_brl_rate: float             = 5.10
    # Vozes ElevenLabs configuráveis via .env (quando preenchido, substitui a voz do nicho)
    elevenlabs_voice_id_default: str = ""   # ELEVENLABS_VOICE_ID_DEFAULT
    elevenlabs_voice_id_adam: str    = ""   # ELEVENLABS_VOICE_ID_Adam
    elevenlabs_voice_id_juliano: str = ""   # ELEVENLABS_VOICE_ID_juliano

    # ── Whisper ────────────────────────────────────────────────────────────────
    whisper_model: str              = "base"        # tiny|base|small|medium

    # ── Video ──────────────────────────────────────────────────────────────────
    resolution_horizontal: tuple[int, int] = (1920, 1080)
    resolution_vertical: tuple[int, int]   = (1080, 1920)
    video_fps: int                  = 30
    video_crf: int                  = 23
    video_preset: str               = "medium"      # ffmpeg preset
    video_codec_cpu: str            = "libx264"
    video_codec_gpu: str            = "h264_amf"    # AMD GPU codec

    # ── Audio ──────────────────────────────────────────────────────────────────
    music_volume: float             = 0.13          # 13 % relative to narration
    music_fade_in_sec: float        = 2.0
    music_fade_out_sec: float       = 5.0
    narration_words_per_min: int    = 130

    # ── Subtitles ──────────────────────────────────────────────────────────────
    subtitle_font_vertical_px: int  = 72
    subtitle_font_horizontal_px: int = 52
    subtitle_words_per_block: int   = 3

    # ── Lower Thirds ───────────────────────────────────────────────────────────
    lower_third_fade_sec: float     = 0.4
    lower_third_start_sec: float    = 0.5  # appears at 0.5 s
    lower_third_end_sec: float      = 4.0  # disappears at 4 s

    # ── Paths ──────────────────────────────────────────────────────────────────
    projects_dir: str               = "projects"
    assets_dir: str                 = "assets"
    music_dir: str                  = "assets/music"

    # ── Pexels ─────────────────────────────────────────────────────────────────
    pexels_per_page: int            = 5
    pexels_min_width: int           = 1280

    # ── Logging ────────────────────────────────────────────────────────────────
    log_level: str                  = "INFO"

    def resolution(self, fmt: str) -> tuple[int, int]:
        """Return (width, height) for given format string '16:9' or '9:16'."""
        return self.resolution_horizontal if fmt == "16:9" else self.resolution_vertical


settings = Settings()
