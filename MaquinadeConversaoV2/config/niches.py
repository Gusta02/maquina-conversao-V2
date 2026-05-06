"""
Seven specialised niche personas.
Each niche carries: system prompt, pain points, CTA options,
ElevenLabs voice ID, Pexels search style hint, accent colour and mood.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from models.project import MoodType


@dataclass
class NicheConfig:
    key: str
    label_pt: str
    system_prompt: str
    pain_points: list[str]
    ctas: list[str]
    voice_id: str                       # ElevenLabs voice ID
    pexels_search_style: str            # hint appended to Pexels queries
    accent_color: tuple[int, int, int]  # RGB
    mood: MoodType
    language: str = "pt-BR"
    edge_tts_voice: str = "pt-BR-FranciscaNeural"  # Microsoft edge-tts (gratuito)


NICHES: dict[str, NicheConfig] = {

    # ── 1. Corretor de Imóveis ─────────────────────────────────────────────────
    "corretor": NicheConfig(
        key="corretor",
        label_pt="Corretor de Imóveis",
        system_prompt=(
            "Você é um especialista em marketing imobiliário digital. "
            "Cria roteiros em português brasileiro para vídeos curtos (até 60 s) "
            "que ajudam corretores a captar leads, apresentar imóveis e construir "
            "autoridade nas redes sociais. Tom: confiante, aspiracional, direto. "
            "Inclua sempre um gancho forte nos primeiros 5 segundos. "
            "Use linguagem acessível, evite jargões legais excessivos."
        ),
        pain_points=[
            "Dificuldade de captar leads qualificados",
            "Concorrência acirrada no mercado",
            "Falta de tempo para produzir conteúdo",
            "Não sabe como se destacar nas redes",
        ],
        ctas=[
            "Me chama no WhatsApp para agendar uma visita!",
            "Clica no link da bio para ver mais opções.",
            "Salva esse vídeo para quando precisar comprar ou alugar.",
            "Segue o perfil para dicas diárias sobre o mercado imobiliário.",
        ],
        voice_id="21m00Tcm4TlvDq8ikWAM",   # Rachel – ElevenLabs
        edge_tts_voice="pt-BR-AntonioNeural",
        pexels_search_style="modern apartment luxury real estate",
        accent_color=(212, 175, 55),  # Gold
        mood=MoodType.CORPORATIVO,
    ),

    # ── 2. Advogado ───────────────────────────────────────────────────────────
    "advogado": NicheConfig(
        key="advogado",
        label_pt="Advogado",
        system_prompt=(
            "Você é um especialista em marketing jurídico digital para advogados. "
            "Cria roteiros em português brasileiro para vídeos curtos (até 60 s) "
            "que educam o público sobre direitos, constroem autoridade e geram "
            "consultas. Tom: sério, empático, acessível — sem juridiquês excessivo. "
            "Nunca configure como consulta jurídica; oriente a buscar assessoria. "
            "Gancho inicial: apresente um problema comum que o público tem."
        ),
        pain_points=[
            "Público não entende seus direitos",
            "Dificuldade de se destacar em mercado saturado",
            "Clientes prospectados por preço, não por valor",
            "Ausência de conteúdo educativo na área",
        ],
        ctas=[
            "Comenta aqui se você já passou por essa situação.",
            "Agende uma consulta pelo link na bio.",
            "Salva esse vídeo — você pode precisar dessa informação.",
            "Segue para mais dicas sobre seus direitos.",
        ],
        voice_id="pNInz6obpgDQGcFmaJgB",   # Adam – ElevenLabs
        edge_tts_voice="pt-BR-AntonioNeural",
        pexels_search_style="law office justice professional",
        accent_color=(25, 25, 112),   # Midnight Blue
        mood=MoodType.CORPORATIVO,
    ),

    # ── 3. Engenheiro Civil / Arquiteto ───────────────────────────────────────
    "engenheiro_civil": NicheConfig(
        key="engenheiro_civil",
        label_pt="Engenheiro Civil / Arquiteto",
        system_prompt=(
            "Você é um especialista em marketing para engenheiros civis e arquitetos. "
            "Cria roteiros em português brasileiro para vídeos curtos (até 60 s) "
            "que mostram projetos, explicam processos de construção e geram orçamentos. "
            "Tom: técnico porém acessível, inspiracional, com foco visual. "
            "Use perguntas retóricas para engajar. Destaque diferenciais do profissional."
        ),
        pain_points=[
            "Clientes não entendem o valor do projeto",
            "Falta de portfólio digital impactante",
            "Dificuldade de fechar contratos pelo preço certo",
            "Concorrência com profissionais não registrados",
        ],
        ctas=[
            "Entre em contato para seu orçamento personalizado.",
            "Veja mais projetos no link da bio.",
            "Segue para acompanhar obras do início ao fim.",
            "Comenta o que achou do projeto!",
        ],
        voice_id="VR6AewLTigWG4xSOukaG",   # Arnold – ElevenLabs
        edge_tts_voice="pt-BR-AntonioNeural",
        pexels_search_style="architecture construction blueprint modern building",
        accent_color=(70, 130, 180),  # Steel Blue
        mood=MoodType.ENERGETICO,
    ),

    # ── 4. Negócio Local ──────────────────────────────────────────────────────
    "negocio_local": NicheConfig(
        key="negocio_local",
        label_pt="Negócio Local",
        system_prompt=(
            "Você é um especialista em marketing digital para pequenos e médios "
            "negócios locais (restaurantes, lojas, serviços). "
            "Cria roteiros em português brasileiro para vídeos curtos (até 60 s) "
            "que aumentam o movimento, divulgam promoções e constroem comunidade. "
            "Tom: animado, próximo, descontraído. Use storytelling local e regional. "
            "Gancho: mostre o problema ou desejo do cliente ideal logo de cara."
        ),
        pain_points=[
            "Baixo movimento em dias específicos",
            "Dificuldade de competir com grandes redes",
            "Clientes não conhecem todos os produtos/serviços",
            "Presença digital fraca ou inexistente",
        ],
        ctas=[
            "Vem nos visitar! Endereço na bio.",
            "Usa o código PROMO para ganhar desconto hoje.",
            "Marca um amigo que precisa conhecer esse lugar!",
            "Segue para não perder nossas novidades.",
        ],
        voice_id="EXAVITQu4vr4xnSDxMaL",   # Bella – ElevenLabs
        edge_tts_voice="pt-BR-ThalitaNeural",
        pexels_search_style="local business shop street cozy",
        accent_color=(255, 140, 0),   # Dark Orange
        mood=MoodType.ENERGETICO,
    ),

    # ── 5. Clínica / Saúde ────────────────────────────────────────────────────
    "clinica": NicheConfig(
        key="clinica",
        label_pt="Clínica / Profissional de Saúde",
        system_prompt=(
            "Você é um especialista em marketing digital para clínicas e "
            "profissionais de saúde (médicos, dentistas, psicólogos, fisioterapeutas). "
            "Cria roteiros em português brasileiro para vídeos curtos (até 60 s) "
            "que educam pacientes, desmistificam tratamentos e geram agendamentos. "
            "Tom: acolhedor, confiável, educativo. Siga diretrizes do CFM/CFO: "
            "não prometa resultados, não faça comparações, não use 'antes e depois'. "
            "Foque em educação e acolhimento."
        ),
        pain_points=[
            "Pacientes não entendem a importância da prevenção",
            "Dificuldade de agendar consultas recorrentes",
            "Concorrência com planos de saúde baratos",
            "Falta de conteúdo educativo de qualidade na área",
        ],
        ctas=[
            "Agende sua consulta pelo link na bio.",
            "Comenta sua dúvida aqui que respondo.",
            "Salva esse vídeo para consultar depois.",
            "Segue para dicas diárias de saúde e bem-estar.",
        ],
        voice_id="MF3mGyEYCl7XYWbV9V6O",   # Elli – ElevenLabs
        edge_tts_voice="pt-BR-FranciscaNeural",
        pexels_search_style="medical clinic health doctor professional",
        accent_color=(0, 168, 150),   # Teal
        mood=MoodType.EMOCIONAL,
    ),

    # ── 6. Imobiliária (empresa) ──────────────────────────────────────────────
    "imobiliaria": NicheConfig(
        key="imobiliaria",
        label_pt="Imobiliária",
        system_prompt=(
            "Você é um especialista em marketing para imobiliárias e construtoras. "
            "Cria roteiros em português brasileiro para vídeos curtos (até 60 s) "
            "focados em lançamentos, diferenciais de empreendimentos e financiamento. "
            "Tom: aspiracional, premium, voltado para sonho de casa própria. "
            "Destaque localização, facilidades de pagamento e diferenciais do projeto. "
            "Gancho: projete o sonho do cliente nos primeiros 5 segundos."
        ),
        pain_points=[
            "Leads não qualificados perdendo tempo da equipe",
            "Dificuldade de apresentar o imóvel sem visita presencial",
            "Ciclo de venda longo com muitas objeções",
            "Concorrência com portais de imóveis generalistas",
        ],
        ctas=[
            "Fale com um de nossos especialistas pelo link na bio.",
            "Agende sua visita e ganhe uma consultoria grátis.",
            "Salva esse vídeo para mostrar para a família.",
            "Segue para acompanhar os nossos lançamentos.",
        ],
        voice_id="21m00Tcm4TlvDq8ikWAM",   # Rachel – ElevenLabs
        edge_tts_voice="pt-BR-AntonioNeural",
        pexels_search_style="luxury real estate development modern condo",
        accent_color=(180, 120, 60),  # Bronze
        mood=MoodType.EMOCIONAL,
    ),

    # ── 7. Genérico ───────────────────────────────────────────────────────────
    "generico": NicheConfig(
        key="generico",
        label_pt="Genérico / Outro",
        system_prompt=(
            "Você é um especialista em produção de conteúdo para redes sociais. "
            "Cria roteiros em português brasileiro para vídeos curtos (até 60 s) "
            "para qualquer tipo de negócio ou criador de conteúdo. "
            "Tom: versátil, engajador, adequado ao contexto informado. "
            "Sempre inclua um gancho forte nos primeiros 5 segundos e "
            "termine com um CTA claro orientado à ação."
        ),
        pain_points=[
            "Falta de presença digital",
            "Dificuldade de criar conteúdo regularmente",
            "Não sabe como engajar a audiência",
            "Conteúdo não converte em clientes",
        ],
        ctas=[
            "Segue o perfil para mais conteúdo como esse.",
            "Comenta o que você achou!",
            "Compartilha com quem precisa ver isso.",
            "Clica no link da bio para saber mais.",
        ],
        voice_id="21m00Tcm4TlvDq8ikWAM",   # Rachel – ElevenLabs
        edge_tts_voice="pt-BR-FranciscaNeural",
        pexels_search_style="business professional modern office",
        accent_color=(99, 102, 241),  # Indigo
        mood=MoodType.CORPORATIVO,
    ),
}


def get_niche(key: str) -> NicheConfig:
    """Return NicheConfig by key, falling back to 'generico'."""
    return NICHES.get(key, NICHES["generico"])
