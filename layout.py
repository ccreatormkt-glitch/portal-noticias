"""Layout do PB Minuto no Instagram, todo por parâmetros.

Base: a estrutura editorial do g1 (medida no site em 20/11/2026), traduzida para a tela do Reels.
Do g1 vem a ORGANIZAÇÃO da notícia: chapéu > manchete > linha fina > metadado (cidade e data) >
crédito da foto. Também vêm as PROPORÇÕES entre esses tamanhos, a escala de espaços e as entrelinhas.
A identidade é a do PB Minuto: vermelho #D0331F e branco, fonte Inter. Nada da marca do g1 é usado.

Para mudar o visual, mexa só aqui:
  - K: quanto 1 px do g1 vale no desenho do Instagram (e com ele todos os espaços);
  - PAPEIS: fonte, tamanho, entrelinha e espaçamento entre letras de cada tipo de texto;
  - FORMATOS: tamanho da tela, margens e áreas seguras de cada formato (Reels, feed).
"""

# ------------------------------------------------------------------ 1) medidas do g1 (referência)
# px na tela do computador, lidos do CSS computado da home e de uma matéria do g1.
G1 = {
    "espacos": (4, 8, 16, 24, 40, 64, 104),                              # --spacing-* do g1
    "entrelinha_compacta": 1.10,                                         # títulos (110%)
    "entrelinha_espacada": 1.50,                                         # textos (150%)
    "raio": 12,                                                          # cantos dos cards
    "manchete": dict(tam=40, entrelinha=48, peso=700, track=-1.8),       # título da matéria
    "titulo_feed": dict(tam=24, entrelinha=26.4, peso=700, track=-0.84),  # título na capa do site
    "linha_fina": dict(tam=15, entrelinha=22, peso=400, track=-0.15),    # subtítulo da matéria
    "chapeu": dict(tam=16, peso=600, track=-0.3),                        # "Suspeita de tornado"
    "meta": dict(tam=12, entrelinha=16, peso=400),                       # "Há 2 horas — Em RS"
    "assinatura": dict(tam=14, entrelinha=20, peso=600),                 # "Por Fulana, g1 RS"
    "credito_foto": dict(tam=12, entrelinha=13.2),
    "manchete_ate_linha_fina": 16,                                       # espaço entre os dois
}

# ------------------------------------------------------------------ 2) tradução para o Instagram
K = 2   # 1 px do g1 = 2 px no desenho 1080 de largura (a margem de 40 do g1 vira os 80 da área segura)

# Piso de leitura no celular: no Reels, 1 px do desenho 1080 vira ~0,36 pt na tela do telefone.
PISO_TEXTO = 34   # ~12 pt: linha fina e outros textos corridos
PISO_META = 26    # ~9,5 pt: cidade, data e outros metadados


def esp(n: int) -> int:
    """Escala de espaços do g1 x K: esp(0)=8, 1=16, 2=32, 3=48, 4=80, 5=128, 6=208."""
    return G1["espacos"][n] * K


def proporcao(papel: str) -> float:
    """Tamanho do papel em relação à manchete, como no g1 (ex.: linha fina = 15/40)."""
    return G1[papel]["tam"] / G1["manchete"]["tam"]


def tam(papel: str, manchete: int) -> int:
    """Tamanho de um texto secundário seguindo a proporção do g1, com piso de leitura no celular."""
    piso = PISO_META if papel in ("meta", "credito_foto") else PISO_TEXTO
    return max(round(manchete * proporcao(papel)), piso)


# Cada tipo de texto. track = espaço entre letras em "em" (negativo = mais justo).
# A manchete do g1 usa -0,045 em na Open Sans Bold; a Inter Black é mais larga e pesada,
# então o valor equivalente é -0,03 em (abaixo disso as letras se encostam).
PAPEIS = {
    "manchete": dict(fonte="Inter-Black.otf", tamanhos=(84, 78, 72, 66, 60, 54),
                     entrelinha=G1["entrelinha_compacta"], track=-0.03, max_linhas=5),
    "linha_fina": dict(fonte="Inter-Medium.otf", entrelinha=1.32, track=-0.006, max_linhas=3),
    "chapeu": dict(fonte="Inter-Bold.otf", tam=26, track=0.06, altura=52, folga=20, raio=10),
    "meta": dict(fonte="Inter-SemiBold.otf", track=0.012),
    "credito_foto": dict(fonte="Inter-Medium.otf", tam=19, track=0.01),
}

# Proporção da altura das maiúsculas e das descendentes na Inter (para medir espaços pelo olho,
# do pé de uma linha ao topo da letra da linha seguinte, e não pela caixa do texto).
ALTURA_MAIUSCULA = 0.727
DESCENDENTE = 0.22

# Cores por função (no g1: vermelho, texto #1f2123 e texto auxiliar #4f5257 sobre branco).
# Aqui a marca inverte: tudo sobre vermelho; o texto auxiliar é um branco levemente rosado
# (não cinza, que fica lavado sobre cor) com contraste de 4,5:1 sobre o vermelho da marca.
COR = {
    "texto": (255, 255, 255),
    "texto_aux": (255, 240, 236),
    "credito": (255, 230, 225),
    "chapeu_fundo": (255, 255, 255),
}

# ------------------------------------------------------------------ 3) formatos do Instagram
# Coordenadas no desenho de 1080 de largura (o arquivo final sai em 2K pela ESCALA do vídeo).
FORMATOS = {
    # Reels 9:16. A grade do perfil mostra só o meio em 3:4 (y 240 a 1680). Na reprodução, a
    # interface cobre ~250 px no topo, ~380 px embaixo (nome, legenda, áudio) e a coluna de botões.
    "reels": dict(w=1080, h=1920, margem=80, topo=300, grade=(240, 1680), base_segura=1540,
                  direita_segura=950, largura_texto=890, logo=66),
    # Feed 4:5 (carrossel/foto). A grade corta só as laterais (3:4), então a margem cobre o corte.
    "feed": dict(w=1080, h=1350, margem=80, topo=72, grade=(0, 1350), base_segura=1350,
                 direita_segura=1000, largura_texto=890, logo=60),
}

# Vídeo do Reels: posições ajustadas com o Arthur (onda centralizada, legenda abaixo dela).
VIDEO = {
    "material": (840, 1150),            # onde o vermelho translúcido começa e fica sólido
    "onda": ((1080 - 800) // 2, 1190, 800, 104),   # x, y, largura, altura do visualizador
    "legenda_y": 1420,                  # centro da legenda
    "legenda_w": 820,                   # largura máxima da legenda (longe dos botões)
}


def pilha_capa(n_linhas_titulo: int, tam_titulo: int, n_linhas_fina: int, tem_credito: bool,
               fmt: dict) -> dict:
    """Posições (baselines) da pilha da capa, de baixo para cima, como no topo da matéria do g1:
    chapéu, manchete, linha fina, metadado e crédito. Tudo termina acima do corte da grade."""
    t_fina, t_meta = tam("linha_fina", tam_titulo), tam("meta", tam_titulo)
    t_cred = PAPEIS["credito_foto"]["tam"]
    cap = lambda t: round(t * ALTURA_MAIUSCULA)
    desc = lambda t: round(t * DESCENDENTE)
    passo_tit = round(tam_titulo * PAPEIS["manchete"]["entrelinha"])
    passo_fina = round(t_fina * PAPEIS["linha_fina"]["entrelinha"])

    y = fmt["grade"][1] - esp(3)                       # pé de tudo: 48 px acima do corte da grade
    pos = {}
    if tem_credito:
        pos["credito"] = y
        y -= cap(t_cred) + esp(1) + desc(t_meta)
    pos["meta"] = y
    y -= cap(t_meta)
    if n_linhas_fina:
        y -= esp(3) + desc(t_fina)                     # linha fina -> metadado: 48 (g1: 24)
        pos["fina"] = y - passo_fina * (n_linhas_fina - 1)   # baseline da 1ª linha
        y = pos["fina"] - cap(t_fina) - esp(2) - desc(tam_titulo)   # manchete -> linha fina: 32
    else:
        y -= esp(3) + desc(tam_titulo)
    pos["titulo"] = y - passo_tit * (n_linhas_titulo - 1)    # baseline da 1ª linha da manchete
    pos["chapeu_fim"] = pos["titulo"] - cap(tam_titulo) - esp(2)   # chapéu -> manchete: 32
    pos["chapeu"] = pos["chapeu_fim"] - PAPEIS["chapeu"]["altura"]
    pos.update(passo_titulo=passo_tit, passo_fina=passo_fina, tam_fina=t_fina, tam_meta=t_meta,
               tam_credito=t_cred)
    return pos


def cabe(pos: dict, fmt: dict) -> bool:
    """A pilha não sobe até a logo: fica pelo menos 80 px (esp 4) abaixo dela."""
    return pos["chapeu"] >= fmt["topo"] + fmt["logo"] + esp(4)
