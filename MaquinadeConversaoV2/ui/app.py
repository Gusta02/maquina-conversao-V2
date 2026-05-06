"""
Máquina de Conversões — Streamlit Dashboard

4 main tabs:
  📝 Roteiro     — LLM Phase 1 + Phase 2 checkpoint
  🎙️ Locução     — TTS generation + scene media upload
  🎬 Renderização — render with subtitles, lower thirds, music
  📤 Exportar    — Drive upload + GC + download

Session state drives the active project across reruns.
"""
import sys
import logging
from pathlib import Path
from typing import Optional

# Garante que a raiz do projeto está no path independente de onde o Streamlit é invocado
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Máquina de Conversões",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Imports (lazy to avoid startup crash if deps missing) ─────────────────────
IMPORTS_OK = False
IMPORT_ERROR = ""
try:
    from config import settings, NICHES, get_niche
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
    from models.project import (
        Project, Scene, MediaAsset, MediaType,
        ProjectStatus, VideoFormat, MoodType,
        LowerThirdStyle, SubtitleStyle,
    )
    IMPORTS_OK = True
except Exception as e:
    IMPORTS_OK = False
    IMPORT_ERROR = str(e)

logger = logging.getLogger(__name__)

# ── CSS ────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] {
        height: 44px;
        padding: 0 20px;
        border-radius: 8px 8px 0 0;
        font-weight: 600;
    }
    .metric-card {
        background: #1e293b;
        border-radius: 10px;
        padding: 16px;
        margin: 4px 0;
    }
    .status-badge {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: 600;
    }
    div[data-testid="stExpander"] details summary p {
        font-weight: 600;
        font-size: 15px;
    }
</style>
""", unsafe_allow_html=True)


# ── Session state init ────────────────────────────────────────────────────────
def _init_state():
    defaults = {
        "project":     None,
        "draft_text":  "",
        "structured":  False,
        "voiced":      False,
        "rendered":    False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()


# ── Guard imports ─────────────────────────────────────────────────────────────
if not IMPORTS_OK:
    st.error(f"❌ Import error: {IMPORT_ERROR}")
    st.info("Run `pip install -r requirements.txt` then restart.")
    st.stop()


# ── Singleton engines (cached by Streamlit) ──────────────────────────────────
@st.cache_resource
def _engines():
    return {
        "llm":   LLMEngine(),
        "voice": VoiceEngine(),
        "miner": MediaMiner(),
        "video": VideoEngine(),
        "music": MusicEngine(),
        "subs":  SubtitleEngine(),
        "lt":    LowerThirdsEngine(),
        "pm":    ProjectManager(),
        "drive": DriveManager(),
        "gc":    GarbageCollector(),
    }

E = _engines()


# ── Sidebar ───────────────────────────────────────────────────────────────────
def _sidebar():
    st.sidebar.image("https://via.placeholder.com/200x60/1e293b/38bdf8?text=MC+v2.0",
                     width="stretch")
    st.sidebar.title("Máquina de Conversões")
    st.sidebar.caption("v2.0 — MVP da Agência")
    st.sidebar.divider()

    mode = st.sidebar.radio(
        "Modo",
        ["🆕 Novo Projeto", "📂 Abrir Existente"],
        key="sidebar_mode",
    )

    if mode == "🆕 Novo Projeto":
        _sidebar_new_project()
    else:
        _sidebar_open_project()

    st.sidebar.divider()
    _sidebar_cache()
    _sidebar_health()


def _sidebar_new_project():
    with st.sidebar.form("new_project_form"):
        st.subheader("Novo Projeto")
        title  = st.text_input("Título do projeto", placeholder="Ex: Dr. João — Dentista")
        niche  = st.selectbox("Nicho", list(NICHES.keys()),
                              format_func=lambda k: NICHES[k].label_pt)
        fmt    = st.radio("Formato", ["9:16 (Vertical)", "16:9 (Horizontal)"])
        p_name = st.text_input("Nome (lower third)", placeholder="Dr. João Silva")
        p_titl = st.text_input("Título/CRM/CRO etc.", placeholder="CRO-SP 12345")

        submitted = st.form_submit_button("✨ Criar Projeto", use_container_width=False)
        if submitted and title:
            video_fmt = VideoFormat.VERTICAL if "9:16" in fmt else VideoFormat.HORIZONTAL
            niche_cfg = get_niche(niche)
            proj = E["pm"].create(
                title=title,
                niche=niche,
                video_format=video_fmt,
                mood=niche_cfg.mood,
                person_name=p_name,
                person_title=p_titl,
            )
            st.session_state.project    = proj
            st.session_state.draft_text = ""
            st.session_state.structured = False
            st.session_state.voiced     = False
            st.session_state.rendered   = False
            st.success(f"Projeto criado: {proj.uuid[:8]}")
            st.rerun()


def _sidebar_open_project():
    projects = E["pm"].list_all()
    if not projects:
        st.sidebar.info("Nenhum projeto encontrado.")
        return
    options = {f"{p['title']} [{p['uuid'][:8]}]": p["uuid"] for p in projects}
    choice  = st.sidebar.selectbox("Selecionar projeto", list(options.keys()))
    if st.sidebar.button("📂 Abrir"):
        proj = E["pm"].load(options[choice])
        if proj:
            st.session_state.project    = proj
            st.session_state.structured = bool(proj.scenes)
            st.session_state.voiced     = proj.status.value in ("voiced", "media_ready", "rendered", "uploaded", "done")
            st.session_state.rendered   = proj.status.value in ("rendered", "uploaded", "done")
            st.rerun()


def _sidebar_cache():
    """Botão para forçar reload dos engines (limpa @st.cache_resource)."""
    if st.sidebar.button("🔄 Reiniciar Engines", help="Limpa cache e recarrega todos os módulos"):
        _engines.clear()
        st.sidebar.success("Cache limpo — recarregando...")
        st.rerun()


def _sidebar_health():
    st.sidebar.subheader("🔌 Status das APIs")
    apis = {
        "Groq": bool(settings.groq_api_key),
        "ElevenLabs": bool(settings.elevenlabs_api_key),
        "Pexels": bool(settings.pexels_api_key),
        "Google Drive": E["drive"].is_configured(),
    }
    for name, ok in apis.items():
        icon = "🟢" if ok else "🔴"
        st.sidebar.caption(f"{icon} {name}")


# ── Tab 1: Roteiro ────────────────────────────────────────────────────────────
def _tab_roteiro():
    proj: Optional[Project] = st.session_state.project
    if not proj:
        st.info("👈 Crie ou abra um projeto na barra lateral.")
        return

    st.header(f"📝 Roteiro — {proj.title}")
    col1, col2, col3 = st.columns(3)
    col1.metric("Nicho", NICHES[proj.niche].label_pt)
    col2.metric("Formato", proj.video_format.value)
    col3.metric("Cenas estruturadas", len(proj.scenes) if proj.scenes else 0)

    st.divider()

    # ── Phase 1: Generate Draft ────────────────────────────────────────────────
    st.subheader("Fase 1 — Gerar Rascunho")
    theme = st.text_input("Tema / assunto do vídeo",
                          placeholder="Ex: 5 direitos do inquilino que todo mundo ignora")

    niche_cfg = get_niche(proj.niche)
    cta_idx   = st.selectbox("CTA final",
                             range(len(niche_cfg.ctas)),
                             format_func=lambda i: niche_cfg.ctas[i])

    if st.button("🤖 Gerar Rascunho com IA", disabled=not theme):
        with st.spinner("Gerando roteiro..."):
            try:
                draft = E["llm"].generate_draft(
                    theme, proj.niche, proj.video_format.value, cta_idx
                )
                st.session_state.draft_text = draft
                # Sincroniza o estado interno do widget (key="draft_editor")
                # Sem isso o st.text_area ignora o value= em reruns
                st.session_state["draft_editor"] = draft
            except Exception as e:
                st.error(f"❌ Erro ao gerar roteiro: {e}")
                logger.exception("generate_draft failed")

    # ── Editable draft ─────────────────────────────────────────────────────────
    draft = st.text_area(
        "✏️ Revise e edite o roteiro livremente:",
        value=st.session_state.draft_text,
        height=300,
        key="draft_editor",
    )
    st.session_state.draft_text = draft

    # Real-time metrics
    if draft:
        metrics = E["llm"].count_metrics(draft)
        m1, m2, m3 = st.columns(3)
        m1.metric("Palavras", metrics["words"])
        m2.metric("Caracteres", metrics["chars"])
        m3.metric("Duração estimada", f"{metrics['duration_sec']:.0f}s")

    st.divider()

    # ── Phase 2: Structure ─────────────────────────────────────────────────────
    st.subheader("Fase 2 — Estruturar em Cenas")
    if st.button("⚙️ Estruturar Roteiro Aprovado em Cenas",
                 disabled=len(draft) < 50):
        with st.spinner("Estruturando cenas..."):
            try:
                script = E["llm"].structure_script(draft, proj.niche)

                from models.project import Scene
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
                E["pm"].set_status(proj, ProjectStatus.SCRIPTED)
                E["pm"].save(proj)
                st.session_state.project    = proj
                st.session_state.structured = True
                st.success(f"✅ {len(proj.scenes)} cenas estruturadas!")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Erro ao estruturar cenas: {e}")
                logger.exception("structure_script failed")

    # ── Show scenes ────────────────────────────────────────────────────────────
    if st.session_state.structured and proj.scenes:
        st.subheader(f"📋 {len(proj.scenes)} Cenas Geradas")
        for scene in proj.scenes:
            with st.expander(f"Cena {scene.id} — {scene.audio_duration_sec:.0f}s estimado"):
                new_text = st.text_area("Texto", scene.script_text,
                                        key=f"scene_text_{scene.id}", height=100)
                st.caption(f"🔍 Busca Pexels: `{scene.search_query}`")
                if new_text != scene.script_text:
                    scene.script_text = new_text
                    scene.dirty = True
                    E["pm"].save(proj)


# ── Helpers: mídia por cena ────────────────────────────────────────────────────

def _scene_media_status(scene) -> str:
    """Retorna ícone + nome do arquivo da mídia atual da cena."""
    if scene.media and scene.media.media_type != MediaType.NONE and scene.media.path:
        tipo = "🎬" if scene.media.media_type == MediaType.VIDEO else "🖼️"
        return f"{tipo} {Path(scene.media.path).name}"
    return "⏳ Sem mídia"


def _scene_pexels_tab(proj, scene) -> None:
    """UI de busca Pexels com grid de thumbnails para uma cena."""
    key_q   = f"pexels_q_{scene.id}"
    key_res = f"pexels_res_{scene.id}"

    if key_q not in st.session_state:
        st.session_state[key_q] = scene.search_query

    col_q, col_btn = st.columns([5, 1])
    with col_q:
        st.text_input("Busca em inglês", key=key_q, label_visibility="collapsed",
                      placeholder="modern office business meeting")
    with col_btn:
        buscar = st.button("🔍", key=f"btn_pex_{scene.id}", help="Buscar no Pexels")

    if buscar:
        query = st.session_state[key_q]
        if query:
            with st.spinner("Buscando..."):
                try:
                    st.session_state[key_res] = E["miner"].search_pexels(query, n=5)
                except Exception as e:
                    st.error(f"❌ Erro Pexels: {e}")
                    logger.exception("search_pexels failed")

    results = st.session_state.get(key_res, [])
    if not results:
        st.caption("Digite um termo e clique em 🔍 para buscar.")
        return

    cols = st.columns(len(results))
    for i, (col, r) in enumerate(zip(cols, results)):
        with col:
            if r["thumb"]:
                st.image(r["thumb"])
            tipo = "🎬" if r["type"] == "video" else "🖼️"
            dur  = f" {r['duration']:.0f}s" if r.get("duration") else ""
            st.caption(f"{tipo}{dur}")
            if st.button("Selecionar", key=f"pex_sel_{scene.id}_{i}"):
                media_dir = Path(settings.projects_dir) / proj.uuid / "media"
                media_dir.mkdir(parents=True, exist_ok=True)
                with st.spinner("Baixando mídia..."):
                    asset = E["miner"].download_pexels_result(r, scene, media_dir)
                scene.media = asset
                E["pm"].save(proj)
                st.session_state.project = proj
                st.success(f"✅ {Path(asset.path).name}")
                st.rerun()


def _scene_upload_tab(proj, scene) -> None:
    """UI de upload de arquivo local para uma cena."""
    uploaded = st.file_uploader(
        "Foto ou vídeo (prioridade máxima sobre Pexels)",
        type=["mp4", "mov", "avi", "jpg", "jpeg", "png", "webp"],
        key=f"upload_{scene.id}",
    )
    if uploaded:
        media_dir = Path(settings.projects_dir) / proj.uuid / "media"
        media_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(uploaded.name).suffix
        dest   = media_dir / f"scene_{scene.id:02d}_client{suffix}"
        dest.write_bytes(uploaded.read())
        asset = E["miner"]._ingest_client_file(str(dest), scene, media_dir)
        if asset:
            scene.media = asset
            E["pm"].save(proj)
            st.session_state.project = proj
            st.success(f"✅ Arquivo salvo: {dest.name}")
            st.rerun()
        else:
            st.error("Formato não suportado.")


# ── Tab 2: Locução ────────────────────────────────────────────────────────────
def _tab_locucao():
    proj: Optional[Project] = st.session_state.project
    if not proj or not proj.scenes:
        st.info("💡 Estruture o roteiro em cenas na aba **Roteiro** primeiro.")
        return

    st.header(f"🎙️ Locução — {proj.title}")

    # Cost estimate
    estimate = E["voice"].estimate_cost(proj)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total de caracteres", f"{estimate.total_chars:,}")
    col2.metric("Já em cache", f"{estimate.cached_chars:,}")
    col3.metric("Custo estimado (USD)", f"${estimate.cost_usd:.4f}")
    col4.metric("Custo estimado (BRL)", f"R$ {estimate.cost_brl:.2f}")

    if estimate.cached_scene_ids:
        st.success(f"✅ Cenas em cache (sem custo): {estimate.cached_scene_ids}")

    st.divider()

    # ── Generate narration ─────────────────────────────────────────────────────
    if st.button("🎙️ Gerar Narrações (ElevenLabs)", type="primary"):
        prog = st.progress(0, text="Iniciando...")
        def cb(done, total):
            prog.progress(done / total, text=f"Cena {done}/{total}...")
        with st.spinner("Gerando áudios..."):
            E["voice"].generate_all(proj, progress_callback=cb)
            E["pm"].set_status(proj, ProjectStatus.VOICED)
            E["pm"].save(proj)
            st.session_state.project = proj
            st.session_state.voiced  = True
        st.success("✅ Narrações geradas!")
        st.rerun()

    st.divider()

    # ── Mídia por cena ─────────────────────────────────────────────────────────
    st.subheader("🎞️ Mídia por Cena")

    for scene in proj.scenes:
        status = _scene_media_status(scene)
        header = f"Cena {scene.id} — {scene.script_text[:55]}...  |  {status}"

        with st.expander(header):
            # Áudio
            if scene.audio_path and Path(scene.audio_path).exists():
                c_audio, c_tag = st.columns([4, 1])
                with c_audio:
                    st.audio(scene.audio_path)
                with c_tag:
                    st.caption("✅ cache" if scene.cache_hit else "🆕 gerado")
            else:
                st.caption("⏳ Narração ainda não gerada")

            st.divider()

            tab_pexels, tab_upload = st.tabs(["🔍 Buscar no Pexels", "📁 Upload de arquivo"])

            with tab_pexels:
                _scene_pexels_tab(proj, scene)

            with tab_upload:
                _scene_upload_tab(proj, scene)


# ── Tab 3: Renderização ───────────────────────────────────────────────────────
def _tab_renderizacao():
    proj: Optional[Project] = st.session_state.project
    if not proj or not st.session_state.voiced:
        st.info("💡 Gere as narrações na aba **Locução** primeiro.")
        return

    st.header(f"🎬 Renderização — {proj.title}")

    col1, col2, col3 = st.columns(3)
    with col1:
        subtitle_style = st.radio(
            "Estilo de legenda",
            [SubtitleStyle.VERTICAL, SubtitleStyle.HORIZONTAL],
            format_func=lambda s: "Centralizada (Reels)" if s == SubtitleStyle.VERTICAL else "Barra inferior",
        )
    with col2:
        lt_style = st.radio(
            "Estilo lower third",
            [LowerThirdStyle.CORPORATE, LowerThirdStyle.MODERN, LowerThirdStyle.MINIMALIST],
            format_func=lambda s: {"corporate": "Corporativo", "modern": "Moderno",
                                   "minimalist": "Minimalista"}[s.value],
        )
    with col3:
        mood_options = {m.value: m for m in MoodType}
        mood_label   = st.selectbox("Mood da trilha", list(mood_options.keys()),
                                    index=list(mood_options.keys()).index(proj.mood.value))
        proj.mood = mood_options[mood_label]

    gen_subs = st.checkbox("Gerar legendas (Whisper)", value=True)
    gen_lt   = st.checkbox("Gerar lower third animado", value=bool(proj.person_name))
    use_music = st.checkbox("Trilha sonora de fundo", value=True)

    proj.subtitle_style     = subtitle_style
    proj.lower_third_style  = lt_style
    E["pm"].save(proj)

    st.divider()

    if st.button("🚀 Renderizar Vídeo", type="primary"):
        w, h = settings.resolution(proj.video_format)

        music_clip = None
        if use_music:
            music_clip = E["music"].get_track(proj.mood)

        scene_paths = []
        total = len(proj.scenes)
        prog  = st.progress(0, "Iniciando renderização...")

        for i, scene in enumerate(proj.scenes):
            prog.progress(i / total, f"Renderizando cena {i+1}/{total}...")
            sub_frames = lt_frames = None

            if gen_subs and scene.audio_path:
                try:
                    sub_frames = E["subs"].generate_subtitle_frames(
                        scene.audio_path, w, h, proj.subtitle_style
                    )
                except Exception as e:
                    st.warning(f"Legenda cena {scene.id}: {e}")

            if gen_lt and proj.person_name:
                try:
                    total_dur = scene.audio_duration_sec or 30
                    lt_frames = E["lt"].generate_frames(proj, w, h, total_dur)
                except Exception as e:
                    st.warning(f"Lower third cena {scene.id}: {e}")

            path = E["video"].render_scene(proj, scene, sub_frames, lt_frames)
            scene_paths.append(path)

        prog.progress(0.9, "Concatenando cenas...")
        E["video"].concatenate_scenes(proj, scene_paths, music_clip)
        if music_clip:
            music_clip.close()

        E["pm"].set_status(proj, ProjectStatus.RENDERED)
        E["pm"].save(proj)
        st.session_state.project  = proj
        st.session_state.rendered = True
        prog.progress(1.0, "✅ Renderização concluída!")
        st.success("✅ Vídeo renderizado com sucesso!")
        st.rerun()


# ── Tab 4: Exportar ────────────────────────────────────────────────────────────
def _tab_exportar():
    proj: Optional[Project] = st.session_state.project
    if not proj or not st.session_state.rendered:
        st.info("💡 Renderize o vídeo na aba **Renderização** primeiro.")
        return

    st.header(f"📤 Exportar — {proj.title}")

    # Video preview
    final_path = proj.final_video_path
    if final_path and Path(final_path).exists():
        st.video(final_path)
        size_mb = Path(final_path).stat().st_size / 1e6
        st.caption(f"📦 Tamanho: {size_mb:.1f} MB")

        # Download button
        with open(final_path, "rb") as f:
            st.download_button(
                "⬇️ Baixar Vídeo",
                f,
                file_name=f"{proj.title}.mp4",
                mime="video/mp4",
            )
    else:
        st.warning("Vídeo final não encontrado.")
        return

    st.divider()

    # Drive upload
    st.subheader("☁️ Upload para Google Drive")
    if proj.drive_link:
        st.success(f"✅ Já enviado: {proj.drive_link}")
    else:
        if not E["drive"].is_configured():
            st.warning("⚠️ Google Drive não configurado. Configure `service_account.json` e `.env`.")
        else:
            if st.button("📤 Enviar para Google Drive", type="primary"):
                with st.spinner("Enviando..."):
                    link = E["drive"].upload_video(proj)
                if link:
                    E["pm"].set_status(proj, ProjectStatus.UPLOADED)
                    gc_result = E["gc"].collect(proj)
                    E["pm"].set_status(proj, ProjectStatus.DONE)
                    E["pm"].save(proj)
                    st.session_state.project = proj
                    st.success(f"✅ Upload concluído! Link: {link}")
                    st.info(f"🗑️ Limpeza: {gc_result['deleted_files']} arquivos removidos")
                    st.rerun()
                else:
                    st.error("❌ Falha no upload. Verifique os logs.")

    if proj.drive_link:
        st.markdown(f"🔗 **Link de acesso:** [{proj.drive_link}]({proj.drive_link})")


# ── Main layout ────────────────────────────────────────────────────────────────
def main():
    _sidebar()

    proj: Optional[Project] = st.session_state.project

    if proj:
        st.caption(f"Projeto ativo: `{proj.uuid}` | Status: **{proj.status.value}**")
    else:
        st.title("🎬 Máquina de Conversões")
        st.markdown("Crie ou abra um projeto na barra lateral para começar.")
        return

    tab1, tab2, tab3, tab4 = st.tabs([
        "📝 Roteiro",
        "🎙️ Locução",
        "🎬 Renderização",
        "📤 Exportar",
    ])

    with tab1:
        _tab_roteiro()
    with tab2:
        _tab_locucao()
    with tab3:
        _tab_renderizacao()
    with tab4:
        _tab_exportar()


if __name__ == "__main__":
    main()
