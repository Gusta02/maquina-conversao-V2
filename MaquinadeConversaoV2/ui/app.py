"""
Máquina de Conversões — Streamlit Dashboard

5 tabs:
  📝 Roteiro      — LLM Phase 1 + Phase 2 checkpoint
  🎙️ Locução      — TTS generation + scene media upload
  🎬 Renderização — render with subtitles, lower thirds, jump cuts, crossfade
  📤 Exportar     — Drive upload + GC + download
  📊 Histórico    — project history dashboard
"""
import sys
import logging
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

st.set_page_config(
    page_title="Máquina de Conversões",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

IMPORTS_OK   = False
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
    from core.jump_cut_engine import JumpCutEngine
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
    IMPORTS_OK   = False
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
    div[data-testid="stExpander"] details summary p {
        font-weight: 600;
        font-size: 15px;
    }
</style>
""", unsafe_allow_html=True)


# ── Session state ─────────────────────────────────────────────────────────────
def _init_state():
    defaults = {
        "project":    None,
        "draft_text": "",
        "structured": False,
        "voiced":     False,
        "rendered":   False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()

if not IMPORTS_OK:
    st.error(f"❌ Import error: {IMPORT_ERROR}")
    st.info("Run `pip install -r requirements.txt` then restart.")
    st.stop()


# ── Singleton engines ─────────────────────────────────────────────────────────
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
        "jc":    JumpCutEngine(),
        "pm":    ProjectManager(),
        "drive": DriveManager(),
        "gc":    GarbageCollector(),
    }

E = _engines()


# ── Sidebar ───────────────────────────────────────────────────────────────────
def _sidebar():
    st.sidebar.title("🎬 Máquina de Conversões")
    st.sidebar.caption("v2.0 — Sprint 2")
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
    _sidebar_tools()
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

        submitted = st.form_submit_button("✨ Criar Projeto")
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
            st.session_state.voiced     = proj.status.value in (
                "voiced", "media_ready", "rendered", "uploaded", "done"
            )
            st.session_state.rendered = proj.status.value in (
                "rendered", "uploaded", "done"
            )
            st.rerun()


def _sidebar_tools():
    st.sidebar.subheader("🛠️ Ferramentas")

    if st.sidebar.button("🔄 Reiniciar Engines", help="Limpa cache e recarrega todos os módulos"):
        _engines.clear()
        st.sidebar.success("Cache limpo — recarregando...")
        st.rerun()

    # Ngrok tunnel
    if st.sidebar.button("🌐 Compartilhar via Ngrok", help="Expõe o dashboard para acesso remoto"):
        _start_ngrok()


def _start_ngrok():
    try:
        from pyngrok import ngrok
        tunnels = ngrok.get_tunnels()
        if tunnels:
            url = tunnels[0].public_url
        else:
            url = ngrok.connect(8501).public_url
        st.sidebar.success(f"Ngrok ativo: {url}")
        st.session_state["ngrok_url"] = url
    except ImportError:
        st.sidebar.error("pyngrok não instalado — `pip install pyngrok`")
    except Exception as e:
        st.sidebar.error(f"Ngrok error: {e}")

    if st.session_state.get("ngrok_url"):
        st.sidebar.caption(f"URL: {st.session_state['ngrok_url']}")


def _sidebar_health():
    st.sidebar.subheader("🔌 Status das APIs")
    apis = {
        "Groq":         bool(settings.groq_api_key),
        "ElevenLabs":   bool(settings.elevenlabs_api_key),
        "Pexels":       bool(settings.pexels_api_key),
        "Google Drive": E["drive"].is_configured(),
    }
    for name, ok in apis.items():
        st.sidebar.caption(f"{'🟢' if ok else '🔴'} {name}")


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
    col3.metric("Cenas", len(proj.scenes) if proj.scenes else 0)

    st.divider()

    st.subheader("Fase 1 — Gerar Rascunho")
    theme = st.text_input("Tema / assunto do vídeo",
                          placeholder="Ex: 5 direitos do inquilino que todo mundo ignora")

    niche_cfg = get_niche(proj.niche)
    cta_idx   = st.selectbox("CTA final", range(len(niche_cfg.ctas)),
                             format_func=lambda i: niche_cfg.ctas[i])

    if st.button("🤖 Gerar Rascunho com IA", disabled=not theme):
        with st.spinner("Gerando roteiro..."):
            try:
                draft = E["llm"].generate_draft(theme, proj.niche, proj.video_format.value, cta_idx)
                st.session_state.draft_text        = draft
                st.session_state["draft_editor"]   = draft
            except Exception as e:
                st.error(f"❌ Erro ao gerar roteiro: {e}")
                logger.exception("generate_draft failed")

    draft = st.text_area(
        "✏️ Revise e edite o roteiro livremente:",
        value=st.session_state.draft_text,
        height=300,
        key="draft_editor",
    )
    st.session_state.draft_text = draft

    if draft:
        metrics = E["llm"].count_metrics(draft)
        m1, m2, m3 = st.columns(3)
        m1.metric("Palavras", metrics["words"])
        m2.metric("Caracteres", metrics["chars"])
        m3.metric("Duração estimada", f"{metrics['duration_sec']:.0f}s")

    st.divider()

    st.subheader("Fase 2 — Estruturar em Cenas")
    if st.button("⚙️ Estruturar Roteiro em Cenas", disabled=len(draft) < 50):
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

    if st.session_state.structured and proj.scenes:
        st.subheader(f"📋 {len(proj.scenes)} Cenas")
        for scene in proj.scenes:
            with st.expander(f"Cena {scene.id} — {scene.audio_duration_sec:.0f}s estimado"):
                new_text = st.text_area("Texto", scene.script_text,
                                        key=f"scene_text_{scene.id}", height=100)
                st.caption(f"🔍 Busca Pexels: `{scene.search_query}`")
                if new_text != scene.script_text:
                    scene.script_text = new_text
                    scene.dirty       = True
                    E["pm"].save(proj)


# ── Helpers: mídia por cena ────────────────────────────────────────────────────
def _scene_media_status(scene) -> str:
    if scene.media and scene.media.media_type != MediaType.NONE and scene.media.path:
        tipo = "🎬" if scene.media.media_type == MediaType.VIDEO else "🖼️"
        return f"{tipo} {Path(scene.media.path).name}"
    return "⏳ Sem mídia"


def _scene_pexels_tab(proj, scene) -> None:
    key_q   = f"pexels_q_{scene.id}"
    key_res = f"pexels_res_{scene.id}"

    if key_q not in st.session_state:
        st.session_state[key_q] = scene.search_query

    col_q, col_btn = st.columns([5, 1])
    with col_q:
        st.text_input("Busca em inglês", key=key_q, label_visibility="collapsed",
                      placeholder="modern office business meeting")
    with col_btn:
        buscar = st.button("🔍", key=f"btn_pex_{scene.id}")

    if buscar:
        query = st.session_state[key_q]
        if query:
            with st.spinner("Buscando..."):
                try:
                    st.session_state[key_res] = E["miner"].search_pexels(query, n=5)
                except Exception as e:
                    st.error(f"❌ Erro Pexels: {e}")

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
    uploaded = st.file_uploader(
        "Foto ou vídeo",
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
            st.success(f"✅ {dest.name}")
            st.rerun()
        else:
            st.error("Formato não suportado.")


# ── Tab 2: Locução ────────────────────────────────────────────────────────────
def _tab_locucao():
    proj: Optional[Project] = st.session_state.project
    if not proj or not proj.scenes:
        st.info("💡 Estruture o roteiro na aba **Roteiro** primeiro.")
        return

    st.header(f"🎙️ Locução — {proj.title}")

    estimate = E["voice"].estimate_cost(proj)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total de caracteres", f"{estimate.total_chars:,}")
    col2.metric("Já em cache", f"{estimate.cached_chars:,}")
    col3.metric("Custo estimado (USD)", f"${estimate.cost_usd:.4f}")
    col4.metric("Custo estimado (BRL)", f"R$ {estimate.cost_brl:.2f}")

    if estimate.cached_scene_ids:
        st.success(f"✅ Cenas em cache (sem custo): {estimate.cached_scene_ids}")

    st.divider()

    if st.button("🎙️ Gerar Narrações", type="primary"):
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
    st.subheader("🎞️ Mídia por Cena")

    for scene in proj.scenes:
        status = _scene_media_status(scene)
        header = f"Cena {scene.id} — {scene.script_text[:55]}...  |  {status}"
        with st.expander(header):
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

    # ── Opções ────────────────────────────────────────────────────────────────
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

    col_a, col_b, col_c, col_d = st.columns(4)
    gen_subs   = col_a.checkbox("Legendas (Whisper + fallback)", value=True)
    gen_lt     = col_b.checkbox("Lower third", value=bool(proj.person_name))
    use_music  = col_c.checkbox("Trilha sonora", value=True)
    use_jc     = col_d.checkbox("Jump Cuts (remove silêncios)", value=False,
                                help="Detecta e remove pausas abaixo de -30 dBFS")
    use_cross  = st.checkbox("Crossfade entre cenas", value=True,
                             help="Transição suave de 0.5s entre cenas")

    proj.subtitle_style    = subtitle_style
    proj.lower_third_style = lt_style
    E["pm"].save(proj)

    st.divider()

    # ── Seleção de cenas ──────────────────────────────────────────────────────
    st.subheader("Seleção de cenas para renderizar")
    all_ids    = [s.id for s in proj.scenes]
    sel_ids    = st.multiselect(
        "Cenas a renderizar (deixe em branco = todas)",
        options=all_ids,
        default=[],
        format_func=lambda sid: f"Cena {sid}",
        help="Útil para re-renderizar apenas cenas modificadas",
    )
    scenes_to_render = [s for s in proj.scenes if s.id in sel_ids] if sel_ids else proj.scenes

    st.caption(f"Cenas selecionadas: {[s.id for s in scenes_to_render]}")

    # ── Botões de ação ────────────────────────────────────────────────────────
    col_prev, col_full = st.columns(2)

    with col_prev:
        if st.button("👁️ Preview (360p)", help="Renderiza rápido sem legendas para aprovação"):
            _render_preview(proj, scenes_to_render[0] if scenes_to_render else proj.scenes[0])

    with col_full:
        if st.button("🚀 Renderizar Vídeo Final", type="primary"):
            _render_full(proj, scenes_to_render, gen_subs, gen_lt, use_music, use_jc, use_cross)


def _render_preview(proj: Project, scene: Scene):
    with st.spinner(f"Gerando preview da cena {scene.id}..."):
        try:
            out = E["video"].render_scene_preview(proj, scene)
            st.video(str(out))
            st.caption(f"Preview gerado: {out.name} ({out.stat().st_size / 1e6:.1f} MB)")
        except Exception as e:
            st.error(f"❌ Erro no preview: {e}")
            logger.exception("preview failed")


def _render_full(proj, scenes, gen_subs, gen_lt, use_music, use_jc, use_cross):
    w, h = settings.resolution(proj.video_format)

    music_clip = None
    if use_music:
        music_clip = E["music"].get_track(proj.mood)

    scene_paths = []
    total = len(scenes)
    prog  = st.progress(0, "Iniciando renderização...")

    for i, scene in enumerate(scenes):
        prog.progress(i / total, f"Renderizando cena {i+1}/{total}...")
        sub_frames = lt_frames = jc_segments = None

        # ── Jump cuts ──────────────────────────────────────────────────────
        cut_audio_path = None
        if use_jc and scene.audio_path:
            try:
                jc_segments = E["jc"].detect_keep_segments(scene.audio_path)
                if len(jc_segments) > 1:
                    cut_path = (
                        Path(settings.projects_dir) / proj.uuid / "audio"
                        / f"scene_{scene.id:02d}_jc.mp3"
                    )
                    E["jc"].apply_to_audio(scene.audio_path, jc_segments, str(cut_path))
                    cut_audio_path = str(cut_path)
            except Exception as e:
                st.warning(f"Jump cut cena {scene.id}: {e}")

        # ── Legendas: Whisper → fallback texto ────────────────────────────
        if gen_subs and scene.audio_path:
            try:
                sub_frames = E["subs"].generate_subtitle_frames(
                    scene.audio_path, w, h, proj.subtitle_style
                )
            except Exception as e:
                st.warning(f"Legenda Whisper cena {scene.id}: {e}")
                sub_frames = []

            if not sub_frames and scene.script_text:
                dur        = scene.audio_duration_sec or 20.0
                sub_frames = E["subs"].generate_frames_from_text(
                    scene.script_text, dur, w, h, proj.subtitle_style
                )

        # ── Lower third ────────────────────────────────────────────────────
        if gen_lt and proj.person_name:
            try:
                dur      = scene.audio_duration_sec or 30.0
                lt_frames = E["lt"].generate_frames(proj, w, h, dur)
            except Exception as e:
                st.warning(f"Lower third cena {scene.id}: {e}")

        # ── Render ─────────────────────────────────────────────────────────
        try:
            path = E["video"].render_scene(
                proj, scene, sub_frames, lt_frames,
                jump_cut_segments=jc_segments,
                audio_path_override=cut_audio_path,
            )
            scene_paths.append(path)
        except Exception as e:
            st.error(f"❌ Erro cena {scene.id}: {e}")
            logger.exception("render_scene failed scene %d", scene.id)

    if not scene_paths:
        st.error("Nenhuma cena renderizada.")
        return

    # Para cenas não re-renderizadas, usa o rendered_path salvo
    all_paths: list[Path] = []
    for s in proj.scenes:
        p = next((x for x in scene_paths if x.name.startswith(f"scene_{s.id:02d}")), None)
        if p:
            all_paths.append(p)
        elif s.rendered_path and Path(s.rendered_path).exists():
            all_paths.append(Path(s.rendered_path))

    prog.progress(0.9, "Concatenando cenas...")
    E["video"].concatenate_scenes(proj, all_paths, music_clip, crossfade=use_cross)
    if music_clip:
        music_clip.close()

    E["pm"].set_status(proj, ProjectStatus.RENDERED)
    E["pm"].save(proj)
    st.session_state.project  = proj
    st.session_state.rendered = True
    prog.progress(1.0, "✅ Concluído!")
    st.success("✅ Vídeo renderizado com sucesso!")
    st.rerun()


# ── Tab 4: Exportar ────────────────────────────────────────────────────────────
def _tab_exportar():
    proj: Optional[Project] = st.session_state.project
    if not proj or not st.session_state.rendered:
        st.info("💡 Renderize o vídeo na aba **Renderização** primeiro.")
        return

    st.header(f"📤 Exportar — {proj.title}")

    final_path = proj.final_video_path
    if final_path and Path(final_path).exists():
        st.video(final_path)
        size_mb = Path(final_path).stat().st_size / 1e6
        st.caption(f"📦 Tamanho: {size_mb:.1f} MB")
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

    st.subheader("☁️ Upload para Google Drive")
    if proj.drive_link:
        st.success(f"✅ Já enviado: {proj.drive_link}")
        st.markdown(f"🔗 **Link:** [{proj.drive_link}]({proj.drive_link})")
    else:
        if not E["drive"].is_configured():
            st.warning("⚠️ Google Drive não configurado.")
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


# ── Tab 5: Histórico ──────────────────────────────────────────────────────────
def _tab_historico():
    st.header("📊 Histórico de Projetos")

    projects = E["pm"].list_all()
    if not projects:
        st.info("Nenhum projeto encontrado.")
        return

    st.caption(f"{len(projects)} projeto(s) encontrado(s)")

    # Resumo em métricas
    status_counts: dict[str, int] = {}
    for p in projects:
        s = p.get("status", "unknown")
        status_counts[s] = status_counts.get(s, 0) + 1

    cols = st.columns(len(status_counts) or 1)
    for col, (status, count) in zip(cols, status_counts.items()):
        col.metric(status.capitalize(), count)

    st.divider()

    # Tabela de projetos
    for p in sorted(projects, key=lambda x: x.get("updated_at", ""), reverse=True):
        uuid      = p.get("uuid", "")
        title     = p.get("title", "Sem título")
        status    = p.get("status", "—")
        updated   = p.get("updated_at", "—")[:16].replace("T", " ")
        n_scenes  = len(p.get("scenes", []))
        has_video = bool(p.get("final_video_path"))
        drive_ok  = bool(p.get("drive_link"))

        with st.expander(f"{'✅' if has_video else '🔄'} {title}  —  {status}  |  {updated}"):
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("UUID", uuid[:8])
            col2.metric("Cenas", n_scenes)
            col3.metric("Vídeo final", "✅" if has_video else "❌")
            col4.metric("Drive", "✅" if drive_ok else "❌")

            if p.get("drive_link"):
                st.markdown(f"🔗 [Abrir no Drive]({p['drive_link']})")

            col_open, col_del = st.columns([1, 3])
            with col_open:
                if st.button("📂 Abrir projeto", key=f"hist_open_{uuid}"):
                    proj = E["pm"].load(uuid)
                    if proj:
                        st.session_state.project    = proj
                        st.session_state.structured = bool(proj.scenes)
                        st.session_state.voiced     = proj.status.value in (
                            "voiced", "media_ready", "rendered", "uploaded", "done"
                        )
                        st.session_state.rendered = proj.status.value in (
                            "rendered", "uploaded", "done"
                        )
                        st.rerun()


# ── Main layout ────────────────────────────────────────────────────────────────
def main():
    _sidebar()

    proj: Optional[Project] = st.session_state.project
    if proj:
        st.caption(f"Projeto ativo: `{proj.uuid}` | Status: **{proj.status.value}**")
    else:
        st.title("🎬 Máquina de Conversões")
        st.markdown("Crie ou abra um projeto na barra lateral para começar.")

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📝 Roteiro",
        "🎙️ Locução",
        "🎬 Renderização",
        "📤 Exportar",
        "📊 Histórico",
    ])

    with tab1:
        _tab_roteiro()
    with tab2:
        _tab_locucao()
    with tab3:
        _tab_renderizacao()
    with tab4:
        _tab_exportar()
    with tab5:
        _tab_historico()


if __name__ == "__main__":
    main()
