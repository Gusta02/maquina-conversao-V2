"""
Script de teste de renderização — usa projeto existente sem chamadas de API.

Projeto: 25303c96-ff64-418c-930c-731d291be569 (João - Corretor)
Testa  : legenda Whisper, lower third animado, trilha, corte, composição final.
Saída  : projects/<uuid>/output/test_output.mp4

Uso:
    python test_render.py              # cena 1 apenas (rápido)
    python test_render.py --cenas 1 2  # cenas específicas
    python test_render.py --todas      # todas as 6 cenas
"""
import sys
import argparse
import logging
from pathlib import Path

# Garante que a raiz do projeto está no path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("test_render")

# ── Imports do projeto ────────────────────────────────────────────────────────
from core.project_manager import ProjectManager
from core.subtitle_engine import SubtitleEngine
from core.lower_thirds_engine import LowerThirdsEngine
from core.music_engine import MusicEngine
from core.video_engine import VideoEngine
from config import settings
from models.project import SubtitleStyle, LowerThirdStyle, MoodType

PROJECT_UUID = "25303c96-ff64-418c-930c-731d291be569"


def parse_args():
    p = argparse.ArgumentParser(description="Teste de renderização")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--cenas", nargs="+", type=int, metavar="N",
                       help="IDs das cenas a renderizar (ex: 1 2)")
    group.add_argument("--todas", action="store_true",
                       help="Renderiza todas as cenas do projeto")
    return p.parse_args()


def check_files(scene) -> bool:
    """Verifica se os arquivos necessários existem."""
    ok = True
    if not scene.audio_path or not Path(scene.audio_path).exists():
        logger.error("  Audio ausente: %s", scene.audio_path)
        ok = False
    if not scene.media or not scene.media.path or not Path(scene.media.path).exists():
        logger.warning("  Vídeo/imagem ausente para cena %d — usará tela preta", scene.id)
    return ok


def main():
    args = parse_args()

    # ── Carrega projeto ───────────────────────────────────────────────────────
    pm = ProjectManager()
    proj = pm.load(PROJECT_UUID)
    if not proj:
        logger.error("Projeto %s não encontrado.", PROJECT_UUID)
        sys.exit(1)

    logger.info("Projeto: %s | Status: %s", proj.title, proj.status.value)
    logger.info("Formato: %s | Nicho: %s", proj.video_format.value, proj.niche)

    # ── Seleciona cenas ───────────────────────────────────────────────────────
    if args.todas:
        cenas = proj.scenes
    elif args.cenas:
        ids = set(args.cenas)
        cenas = [s for s in proj.scenes if s.id in ids]
    else:
        cenas = proj.scenes[:1]  # padrão: só cena 1

    if not cenas:
        logger.error("Nenhuma cena selecionada.")
        sys.exit(1)

    logger.info("Cenas selecionadas: %s", [s.id for s in cenas])

    # ── Engines ───────────────────────────────────────────────────────────────
    sub_engine = SubtitleEngine()
    lt_engine  = LowerThirdsEngine()
    music_eng  = MusicEngine()
    video_eng  = VideoEngine()

    w, h = settings.resolution(proj.video_format)
    logger.info("Resolução: %dx%d | Encoder: %s", w, h, video_eng._encoder)

    # Trilha sonora
    music_clip = music_eng.get_track(proj.mood or MoodType.CORPORATIVO)
    if music_clip:
        logger.info("Trilha carregada: %s", proj.mood.value)
    else:
        logger.warning("Nenhuma trilha encontrada em assets/music/%s/", proj.mood.value)

    # ── Renderiza cenas ───────────────────────────────────────────────────────
    scene_paths = []
    for scene in cenas:
        logger.info("─── Cena %d: %s", scene.id, scene.script_text[:50])

        if not check_files(scene):
            logger.error("Pulando cena %d por arquivo ausente.", scene.id)
            continue

        # Legendas Whisper → fallback texto puro
        sub_frames = None
        logger.info("  Gerando legendas (Whisper %s)...", settings.whisper_model)
        try:
            sub_frames = sub_engine.generate_subtitle_frames(
                scene.audio_path, w, h, SubtitleStyle.VERTICAL
            )
            logger.info("  Legendas Whisper: %d blocos", len(sub_frames))
        except Exception as e:
            logger.warning("  Falha nas legendas Whisper: %s", e)
            sub_frames = []

        if not sub_frames and scene.script_text:
            logger.info("  Usando fallback de legenda por texto...")
            try:
                audio_dur = scene.audio_duration_sec or 20.0
                sub_frames = sub_engine.generate_frames_from_text(
                    scene.script_text, audio_dur, w, h, SubtitleStyle.VERTICAL
                )
                logger.info("  Legendas texto: %d blocos", len(sub_frames))
            except Exception as e:
                logger.warning("  Falha no fallback de legenda: %s", e)
                sub_frames = []

        # Lower third
        lt_frames = None
        if proj.person_name:
            logger.info("  Gerando lower third para '%s'...", proj.person_name)
            try:
                audio_dur = scene.audio_duration_sec or 20.0
                lt_frames = lt_engine.generate_frames(
                    proj, w, h, audio_dur
                )
                logger.info("  Lower third: %d frames gerados", len(lt_frames))
            except Exception as e:
                logger.warning("  Falha no lower third: %s", e)

        # Renderiza cena
        logger.info("  Renderizando cena %d...", scene.id)
        try:
            path = video_eng.render_scene(proj, scene, sub_frames, lt_frames)
            scene_paths.append(path)
            size_mb = path.stat().st_size / 1e6
            logger.info("  Cena %d → %s (%.1f MB)", scene.id, path.name, size_mb)
        except Exception as e:
            logger.error("  Erro ao renderizar cena %d: %s", scene.id, e)
            raise

    if not scene_paths:
        logger.error("Nenhuma cena renderizada.")
        sys.exit(1)

    # ── Concatena e salva como test_output.mp4 ────────────────────────────────
    logger.info("─── Concatenando %d cena(s)...", len(scene_paths))
    out_dir = Path(settings.projects_dir) / PROJECT_UUID / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Redireciona o path de saída para test_output.mp4
    _original_save = proj.final_video_path
    proj.final_video_path = None  # evita sobrescrever o final original

    final_path = out_dir / "test_output.mp4"

    # Usa o engine diretamente apontando para test_output
    from moviepy.editor import VideoFileClip, concatenate_videoclips
    clips = [VideoFileClip(str(p)) for p in scene_paths]
    combined = concatenate_videoclips(clips, method="chain")

    if music_clip and len(cenas) > 1:
        combined = video_eng._mix_music(combined, music_clip)

    video_eng._write_clip(combined, final_path)

    for c in clips:
        c.close()
    combined.close()
    if music_clip:
        music_clip.close()

    # Restaura path original
    proj.final_video_path = _original_save

    size_mb = final_path.stat().st_size / 1e6
    logger.info("══ PRONTO ══")
    logger.info("Saída : %s", final_path)
    logger.info("Tamanho: %.1f MB", size_mb)
    logger.info("Duração cenas: %s",
                [f"{s.audio_duration_sec:.1f}s" for s in cenas if s.id in {s2.id for s2 in cenas}])


if __name__ == "__main__":
    main()
