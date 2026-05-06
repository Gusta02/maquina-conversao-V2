# 🎬 Máquina de Conversões v2.0

> Ecossistema autossuficiente de produção audiovisual automatizada.
> IA generativa + síntese de voz + montagem + distribuição em uma única pipeline.

---

## ⚡ Quick Start

```bash
# 1. Clone e crie o virtualenv
git clone <repo>
cd maquina_conversoes
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 2. Instale as dependências
pip install -r requirements.txt

# 3. Configure o .env
cp .env.example .env
# Edite .env com suas chaves de API

# 4. (Opcional) Configure o Google Drive OAuth
python setup_drive.py

# 5. Rode o dashboard Streamlit
streamlit run ui/app.py

# OU rode a API FastAPI
python main.py
```

---

## 🏗️ Estrutura do Projeto

```
maquina_conversoes/
├── main.py                    # FastAPI entry point
├── setup_drive.py             # Google Drive OAuth (run once)
├── requirements.txt
├── .env.example               # Template de variáveis de ambiente
│
├── ui/
│   └── app.py                 # Streamlit dashboard (4 abas)
│
├── core/                      # Engines independentes
│   ├── llm_engine.py          # Roteiros via Groq/LLaMA
│   ├── voice_engine.py        # TTS via ElevenLabs (com cache)
│   ├── media_miner.py         # Curadoria de b-roll (Pexels + upload)
│   ├── video_engine.py        # Montagem MoviePy + FFmpeg
│   ├── subtitle_engine.py     # Legendas via Whisper
│   ├── music_engine.py        # Trilha sonora automática
│   ├── lower_thirds_engine.py # Tarja animada
│   ├── project_manager.py     # Estado dos projetos (JSON)
│   ├── drive_manager.py       # Upload Google Drive
│   └── garbage_collector.py   # Limpeza pós-entrega
│
├── config/
│   ├── settings.py            # Pydantic Settings (lê .env)
│   └── niches.py              # 7 nichos + prompts + CTAs
│
├── models/
│   ├── project.py             # Pydantic: Project, Scene
│   └── script.py              # Pydantic: Script, CostEstimate
│
├── tests/                     # pytest — todos os mocks ativados
└── assets/music/              # MP3s livres por mood
    ├── corporativo/
    ├── energetico/
    ├── emocional/
    └── epico/
```

---

## 🔑 Variáveis de Ambiente (.env)

| Variável | Descrição | Onde obter |
|---|---|---|
| `GROQ_API_KEY` | Chave da API Groq | console.groq.com |
| `ELEVENLABS_API_KEY` | Chave ElevenLabs | elevenlabs.io |
| `PEXELS_API_KEY` | Chave Pexels | pexels.com/api |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | Caminho do JSON da Service Account | Google Cloud Console |
| `GOOGLE_DRIVE_FOLDER_ID` | ID da pasta de entrega no Drive | URL do Drive |

---

## 🎛️ Nichos Disponíveis

| Chave | Nome | Mood padrão |
|---|---|---|
| `corretor` | Corretor de Imóveis | Corporativo |
| `advogado` | Advogado | Corporativo |
| `engenheiro_civil` | Engenheiro Civil / Arquiteto | Energético |
| `negocio_local` | Negócio Local | Energético |
| `clinica` | Clínica / Saúde | Emocional |
| `imobiliaria` | Imobiliária | Emocional |
| `generico` | Genérico | Corporativo |

---

## 🧱 Adicionando um Novo Nicho

1. Abra `config/niches.py`
2. Adicione um novo `NicheConfig` ao dicionário `NICHES`
3. Defina: `system_prompt`, `pain_points`, `ctas`, `voice_id`, `pexels_search_style`, `accent_color`, `mood`
4. Pronto — o novo nicho aparece automaticamente no dashboard

---

## 🧪 Rodando os Testes

```bash
pytest tests/ -v
```

Os testes mocam todas as APIs externas — nenhuma chamada real é feita.

---

## 🎵 Adicionando Músicas de Fundo

1. Coloque arquivos `.mp3` nas pastas `assets/music/{mood}/`
2. Use músicas livres de royalties (ex: ccMixter, Free Music Archive)
3. O sistema seleciona aleatoriamente entre os arquivos disponíveis

---

## 🚀 Roadmap

- **Fase 1 (atual):** MVP Agência B2B — pipeline completa ✅
- **Fase 2:** Jump cuts automáticos, GPU AMD, preview baixa resolução
- **Fase 3:** Canais Dark — vídeos longos YouTube + upload automático
- **Fase 4:** Imovel Vision — Virtual Staging com IA generativa

---

## 💰 Custo Operacional

| Serviço | Custo mensal |
|---|---|
| ElevenLabs TTS | ~R$ 90 |
| Groq Cloud | ~R$ 20 |
| Google Drive 5TB | ~R$ 50 |
| Pexels API | R$ 0 |
| Whisper (local) | R$ 0 |
| Render GPU AMD | R$ 0 |
| **Total** | **~R$ 160** |

---

*Máquina de Conversões // Documento Técnico Interno // v2.0 // 2026*
