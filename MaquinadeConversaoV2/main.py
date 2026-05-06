"""
Máquina de Conversões — FastAPI entry point.

Exposes:
  GET  /health           → API status of all services
  POST /projects         → create a new project
  GET  /projects         → list all projects
  GET  /projects/{uuid}  → get project detail
  POST /projects/{uuid}/generate-draft    → Phase 1 LLM
  POST /projects/{uuid}/structure-script  → Phase 2 LLM
  POST /projects/{uuid}/generate-voice    → TTS for all scenes
  POST /projects/{uuid}/resolve-media     → b-roll curation
  POST /projects/{uuid}/render            → full video render
  POST /projects/{uuid}/upload            → Drive upload + GC

The Streamlit UI (ui/app.py) calls these endpoints OR imports engines directly.
"""
import logging
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from config import settings, NICHES
from core.llm_engine import LLMEngine
from core.voice_engine import VoiceEngine
from core.media_miner import MediaMiner
from core.video_engine import VideoEngine
from core.music_engine import MusicEngine
from core.subtitle_engine import SubtitleEngine
from core.lower_thirds_engine import LowerThirdsEngine
from core.project_manager import ProjectManager
from core.drive_manager import DriveManager
from core.garbage_collector import GarbageCollector
from models.project import Project, ProjectStatus, VideoFormat, MoodType, LowerThirdStyle, SubtitleStyle
from models.script import HealthStatus

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Máquina de Conversões API",
    description="Automated video production pipeline",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Singleton engines ──────────────────────────────────────────────────────────
_llm     = LLMEngine()
_voice   = VoiceEngine()
_miner   = MediaMiner()
_video   = VideoEngine()
_music   = MusicEngine()
_subs    = SubtitleEngine()
_lt      = LowerThirdsEngine()
_pm      = ProjectManager()
_drive   = DriveManager()
_gc      = GarbageCollector()


# ── Request/Response schemas ───────────────────────────────────────────────────

class CreateProjectRequest(BaseModel):
    title: str
    niche: str = "generico"
    video_format: VideoFormat = VideoFormat.VERTICAL
    mood: MoodType = MoodType.CORPORATIVO
    lower_third_style: LowerThirdStyle = LowerThirdStyle.CORPORATE
    subtitle_style: SubtitleStyle = SubtitleStyle.VERTICAL
    person_name: str = ""
    person_title: str = ""

class GenerateDraftRequest(BaseModel):
    theme: str
    cta_index: int = 0

class StructureScriptRequest(BaseModel):
    approved_text: str

class RenderRequest(BaseModel):
    generate_subtitles: bool = True
    generate_lower_third: bool = True
    use_music: bool = True


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthStatus)
def health_check():
    """Ping all external APIs and return service availability."""
    status = HealthStatus()
    errors = {}

    # Groq
    try:
        _llm._complete(system="ping", user="responda apenas: ok", temperature=0.0)
        status.groq = True
    except Exception as e:
        errors["groq"] = str(e)

    # ElevenLabs
    try:
        from elevenlabs import ElevenLabs
        client = ElevenLabs(api_key=settings.elevenlabs_api_key)
        info = client.user.get_subscription()
        status.elevenlabs = True
        status.elevenlabs_chars_remaining = getattr(info, "character_limit", None)
    except Exception as e:
        errors["elevenlabs"] = str(e)

    # Pexels
    try:
        import requests as req
        r = req.get("https://api.pexels.com/v1/search",
                    headers={"Authorization": settings.pexels_api_key},
                    params={"query": "test", "per_page": 1}, timeout=5)
        r.raise_for_status()
        status.pexels = True
    except Exception as e:
        errors["pexels"] = str(e)

    # Google Drive
    try:
        status.google_drive = _drive.check_connection()
        if not status.google_drive:
            errors["google_drive"] = "Service account not configured or unreachable"
    except Exception as e:
        errors["google_drive"] = str(e)

    # Whisper model path
    import whisper
    status.whisper_model = settings.whisper_model
    status.errors = errors

    return status


@app.get("/niches")
def list_niches():
    return [{"key": k, "label": v.label_pt, "mood": v.mood.value}
            for k, v in NICHES.items()]


@app.post("/projects", response_model=Project)
def create_project(req: CreateProjectRequest):
    return _pm.create(**req.model_dump())


@app.get("/projects")
def list_projects():
    return _pm.list_all()


@app.get("/projects/{uuid}", response_model=Project)
def get_project(uuid: str):
    proj = _pm.load(uuid)
    if not proj:
        raise HTTPException(404, "Project not found")
    return proj


@app.post("/projects/{uuid}/generate-draft")
def generate_draft(uuid: str, req: GenerateDraftRequest):
    proj = _load_or_404(uuid)
    draft = _llm.generate_draft(
        theme=req.theme,
        niche_key=proj.niche,
        video_format=proj.video_format.value,
        cta_index=req.cta_index,
    )
    metrics = _llm.count_metrics(draft)
    return {"draft": draft, "metrics": metrics}


@app.post("/projects/{uuid}/structure-script", response_model=Project)
def structure_script(uuid: str, req: StructureScriptRequest):
    proj = _load_or_404(uuid)
    script = _llm.structure_script(req.approved_text, proj.niche)

    from models.project import Scene, MediaAsset
    proj.scenes = [
        Scene(
            id=s.scene_number,
            order=s.scene_number,
            script_text=s.text,
            search_query=s.search_query,
            audio_duration_sec=s.duration_sec,
        )
        for s in script.scenes
    ]
    _pm.set_status(proj, ProjectStatus.SCRIPTED)
    _pm.save(proj)
    return proj


@app.get("/projects/{uuid}/cost-estimate")
def cost_estimate(uuid: str):
    proj = _load_or_404(uuid)
    return _voice.estimate_cost(proj)


@app.post("/projects/{uuid}/generate-voice", response_model=Project)
def generate_voice(uuid: str):
    proj = _load_or_404(uuid)
    _voice.generate_all(proj)
    _pm.set_status(proj, ProjectStatus.VOICED)
    _pm.save(proj)
    return proj


@app.post("/projects/{uuid}/resolve-media", response_model=Project)
def resolve_media(uuid: str):
    proj = _load_or_404(uuid)
    _miner.resolve_all(proj)
    _pm.set_status(proj, ProjectStatus.MEDIA)
    _pm.save(proj)
    return proj


@app.post("/projects/{uuid}/upload-scene-media/{scene_id}")
async def upload_scene_media(uuid: str, scene_id: int, file: UploadFile = File(...)):
    """Receive a file upload for a specific scene and save to project media dir."""
    proj = _load_or_404(uuid)
    scene = next((s for s in proj.scenes if s.id == scene_id), None)
    if not scene:
        raise HTTPException(404, f"Scene {scene_id} not found")

    media_dir = Path(settings.projects_dir) / proj.uuid / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "upload").suffix or ".mp4"
    dest = media_dir / f"scene_{scene_id:02d}_client{suffix}"

    content = await file.read()
    dest.write_bytes(content)

    asset = _miner._ingest_client_file(str(dest), scene, media_dir)
    if asset:
        scene.media = asset
        _pm.save(proj)

    return {"path": str(dest), "media_type": scene.media.media_type.value}


@app.post("/projects/{uuid}/render", response_model=Project)
def render_project(uuid: str, req: RenderRequest):
    proj = _load_or_404(uuid)
    w, h = settings.resolution(proj.video_format)

    music_clip = None
    if req.use_music:
        music_clip = _music.get_track(proj.mood)

    scene_paths = []
    for scene in proj.scenes:
        sub_frames  = None
        lt_frames   = None

        if req.generate_subtitles and scene.audio_path:
            try:
                sub_frames = _subs.generate_subtitle_frames(
                    scene.audio_path, w, h, proj.subtitle_style
                )
            except Exception as e:
                logger.warning("Subtitle generation failed for scene %d: %s", scene.id, e)

        if req.generate_lower_third and proj.person_name:
            try:
                total_dur = scene.audio_duration_sec or 30
                lt_frames = _lt.generate_frames(proj, w, h, total_dur)
            except Exception as e:
                logger.warning("Lower third failed for scene %d: %s", scene.id, e)

        scene_path = _video.render_scene(proj, scene, sub_frames, lt_frames)
        scene_paths.append(scene_path)

    _video.concatenate_scenes(proj, scene_paths, music_clip)
    if music_clip:
        music_clip.close()

    _pm.set_status(proj, ProjectStatus.RENDERED)
    _pm.save(proj)
    return proj


@app.post("/projects/{uuid}/upload", response_model=Project)
def upload_to_drive(uuid: str):
    proj = _load_or_404(uuid)
    link = _drive.upload_video(proj)

    if not link:
        raise HTTPException(500, "Drive upload failed — check logs")

    _pm.set_status(proj, ProjectStatus.UPLOADED)
    _pm.save(proj)

    # Auto-trigger garbage collection
    gc_result = _gc.collect(proj)
    logger.info("GC result: %s", gc_result)

    _pm.set_status(proj, ProjectStatus.DONE)
    _pm.save(proj)
    return proj


# ── Helpers ────────────────────────────────────────────────────────────────────

def _load_or_404(uuid: str) -> Project:
    proj = _pm.load(uuid)
    if not proj:
        raise HTTPException(404, "Project not found")
    return proj


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
