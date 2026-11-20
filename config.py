"""Configurações centrais. Tudo vem de variáveis de ambiente (GitHub Secrets/Variables)
ou de um arquivo .env local (nunca suba o .env para o GitHub)."""
import os
from pathlib import Path

ROOT = Path(__file__).parent


def _load_env_file():
    p = ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env_file()


def env(key: str, default: str = "") -> str:
    # valor vazio (ex.: variável do GitHub não preenchida) conta como "não definido"
    return os.environ.get(key) or default


def env_bool(key: str, default: bool) -> bool:
    return env(key, "true" if default else "false").lower() in ("1", "true", "sim", "yes")


# ---- Marca do portal ----------------------------------------------------------
PORTAL_NAME = env("PORTAL_NAME", "PB Minuto")
PORTAL_HANDLE = env("PORTAL_HANDLE", "@pbminuto")
# cor principal da marca (hex). Cada editoria tem sua própria cor de destaque.
BRAND_COLOR = env("BRAND_COLOR", "#D0331F")  # vermelho da marca, tom da referência escolhida pelo Arthur
TIMEZONE = env("TIMEZONE", "America/Fortaleza")

# ---- Comportamento ------------------------------------------------------------
# auto   = publica sozinho (padrão)
# review = deixa os cards na fila queue/pending esperando aprovação
POST_MODE = env("POST_MODE", "auto")
POSTS_PER_RUN = int(env("POSTS_PER_RUN", "2"))  # até 2 por rodada quando o ritmo está atrasado
MAX_POSTS_PER_DAY = int(env("MAX_POSTS_PER_DAY", "95"))  # em 24h; a API do Instagram aceita 100 (5 ficam de folga)
HORAS_ATIVAS = 18  # 06h às 24h: o ritmo alvo é MAX_POSTS_PER_DAY / HORAS_ATIVAS posts por hora
HORA_INICIO = int(env("HORA_INICIO", "6"))  # antes disso (madrugada) a rodada normal não posta
MIN_SOURCES = int(env("MIN_SOURCES", "2"))       # veículos diferentes dando a mesma notícia
# notícia vinda de 1 só veículo é aceita se ele estiver nesta lista (veículos grandes/oficiais)
TRUSTED_SINGLE_SOURCE = env_bool("TRUSTED_SINGLE_SOURCE", True)
# como tratar polícia/tragédia: "careful" = publica com regras de cuidado, "skip" = não publica
SENSITIVE_MODE = env("SENSITIVE_MODE", "careful")
DEDUPE_HOURS = int(env("DEDUPE_HOURS", "168"))  # 7 dias de memória contra repetição
MAX_STORY_AGE_HOURS = int(env("MAX_STORY_AGE_HOURS", "12"))
# carrossel de 2 lâminas (capa + detalhes). Desligado: o post é só a capa + legenda completa
# quantas notícias a IA avalia por rodada para escolher a de maior potencial
BRASIL_RESERVA = env_bool("BRASIL_RESERVA", True)  # sem novidade da Paraíba: notícia geral do Brasil (G1)
BRASIL_A_CADA = int(env("BRASIL_A_CADA", "3"))  # 1 a cada 3 posts é notícia relevante do Brasil (0 = só reserva)
CANDIDATOS = int(env("CANDIDATOS", "1"))  # 1 = mais rápido (uma notícia por rodada de 10 min)
CAROUSEL = env_bool("CAROUSEL", False)  # padrão: só a capa; detalhes vão na legenda

# ---- IA que escreve (Gemini tem plano gratuito) --------------------------------
GEMINI_API_KEY = env("GEMINI_API_KEY")
# lista separada por vírgula: se o primeiro modelo não existir mais, tenta o próximo
# modelos do plano grátis (nov/2026); se o 1º for aposentado, o bot tenta o próximo
GEMINI_MODEL = env("GEMINI_MODEL", "gemini-3.5-flash,gemini-2.5-flash,gemini-3.1-flash-lite,gemini-2.5-flash-lite,gemini-flash-latest")  # verificados na chave em 19/11/2026
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY")
CLAUDE_MODEL = env("CLAUDE_MODEL", "claude-sonnet-5-5")
OPENAI_API_KEY = env("OPENAI_API_KEY")
OPENAI_MODEL = env("OPENAI_MODEL", "gpt-5.4-mini,gpt-5-mini")  # em ordem; cai para o próximo se um sair do ar
LLM_PROVIDER = env("LLM_PROVIDER") or ("openai" if OPENAI_API_KEY else "gemini" if GEMINI_API_KEY else "anthropic")

# ---- Foto de banco gratuito (Pexels: chave grátis em pexels.com/api) --------
PEXELS_API_KEY = env("PEXELS_API_KEY")

# ---- Formato do post ----------------------------------------------------------
# reels  = vídeo animado com narração (Piper + FFmpeg); se falhar, publica a imagem
# imagem = só a capa estática
FORMATO = env("FORMATO", "reels")
PIPER_VOICE = env("PIPER_VOICE", "pt_BR-faber-medium")   # reserva offline: pt_BR-cadu-medium, pt_BR-jeff-medium
# voz: "gemini" (voz neural do Google, padrão) ou "clonada" (voz do Arthur via Chatterbox)
VOZ_MOTOR = env("VOZ_MOTOR", "gemini")  # "clonada" só com máquina mais forte (na CPU grátis passa de 5 min)
# reserva: TTS do Gemini (neural, português do Brasil, mesma chave do Google)
# Padrão de áudio de todos os spots = o da 1ª postagem: gemini-3.1-flash-tts-preview, voz Charon.
# Com VOZ_FIXA (padrão), só a 1ª voz da lista é usada: se ela falhar, a notícia espera a próxima
# rodada em vez de sair com outra voz. Sem VOZ_FIXA, as outras da lista (e o Piper) viram reserva.
TTS_MODEL = env("TTS_MODEL", "gemini-3.1-flash-tts-preview,gemini-3.8-flash-tts,gemini-2.5-flash-preview-tts")
VOZ_FIXA = env_bool("VOZ_FIXA", True)
ESTILO_VIDEO = env("ESTILO_VIDEO", "audiograma")  # "audiograma" (onda + legenda) ou "estatico"
VIDEO_2K = env_bool("VIDEO_2K", True)  # vídeo em 2K (1440x2560); false = 1080x1920
# anti-redundância na narração/legenda: uma frase sai se esta fração (ou mais) das palavras
# importantes dela já foi dita antes (0.6 = 60%). Menor = mais rigoroso; 1.0 = desliga.
REDUNDANCIA_MAX = float(env("REDUNDANCIA_MAX", "0.6"))
WHISPER_MODELO = env("WHISPER_MODELO", "small")  # tempo de cada palavra da legenda (faster-whisper, CPU; "small" acerta mais em português)
TTS_VOICE = env("TTS_VOICE", "Charon")  # voz de biblioteca, tom informativo; outras: Kore, Orus, Puck

# ---- Imagem ilustrativa por IA (opcional) --------------------------------------
# none = card só tipográfico (padrão, custo zero)
# gemini = gera uma ilustração de fundo (nunca pessoas reais nem "foto" do fato).
#          ATENÇÃO: modelos de imagem do Gemini são pagos; o padrão grátis é a foto do Pexels.
IMAGE_MODE = env("IMAGE_MODE", "gemini")  # ilustração por IA quando não houver foto livre da cidade
GEMINI_IMAGE_MODEL = env("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image,gemini-2.5-flash-image,gemini-3-pro-image")

# ---- Instagram (API oficial da Meta) --------------------------------------------
IG_USER_ID = env("IG_USER_ID")
IG_ACCESS_TOKEN = env("IG_ACCESS_TOKEN")
GRAPH_VERSION = env("GRAPH_VERSION", "v26.0")
# graph.facebook.com (conta ligada a Página) ou graph.instagram.com (login do Instagram)
GRAPH_HOST = env("GRAPH_HOST", "graph.facebook.com")

# ---- Hospedagem pública da imagem (o Instagram baixa a imagem de um link) -------
IMGBB_API_KEY = env("IMGBB_API_KEY")          # opção simples e gratuita
S3_ENDPOINT = env("S3_ENDPOINT")               # opção alternativa (Cloudflare R2 etc.)
S3_BUCKET = env("S3_BUCKET")
S3_ACCESS_KEY = env("S3_ACCESS_KEY")
S3_SECRET_KEY = env("S3_SECRET_KEY")
S3_PUBLIC_BASE_URL = env("S3_PUBLIC_BASE_URL")

# ---- Pastas ---------------------------------------------------------------------
STATE_DIR = ROOT / "state"
QUEUE_PENDING = ROOT / "queue" / "pending"
QUEUE_PUBLISHED = ROOT / "queue" / "published"
OUT_DIR = ROOT / "out"
FONT_DIR = ROOT / "fonts"
for _d in (STATE_DIR, QUEUE_PENDING, QUEUE_PUBLISHED, OUT_DIR):
    _d.mkdir(parents=True, exist_ok=True)
DB_PATH = STATE_DIR / "posts.db"
LOG_PATH = STATE_DIR / "log.jsonl"
