"""Layout e marca do PB Minuto no Instagram, todo por parâmetros do design do g1.

Medido no g1 (CSS computado da home e de uma matéria, 20/11/2026) e traduzido para a tela do Reels:
  - barra vermelha no topo com a logo no centro (cabeçalho do g1: 74 px de altura, logo de 48);
  - destaque do g1: foto cheia, degradê preto embaixo e texto BRANCO com sombra
    (chapéu > manchete > linha fina > metadado > crédito, alinhados à esquerda);
  - letra: Inter no estilo da CNN (regras de cada uso em FONTE/PAPEIS, abaixo); antes, Open Sans do g1, com o mesmo espaçamento
    entre letras e as mesmas entrelinhas; escala de espaços 4/8/16/24/40/64/104 e cantos de 12.
O nome, a logo e o vermelho continuam os do PB Minuto (não é a marca do g1).

Para mudar o visual, mexa só aqui:
  - K: quanto 1 px do g1 vale no desenho do Instagram (e com ele todos os espaços);
  - MARCA / COR: cores; FONTE: arquivos por peso; PAPEIS: cada tipo de texto;
  - FORMATOS: tela, margens, barra do topo e áreas seguras de cada formato (Reels, feed).
"""
import re

try:
    from config import BRAND_COLOR
except ImportError:  # pragma: no cover
    BRAND_COLOR = "#D0331F"

# ------------------------------------------------------------------ 1) medidas do g1 (referência)
G1 = {
    "vermelho": (196, 23, 12), "vermelho_2": (166, 19, 10),        # primária e secundária
    "espacos": (4, 8, 16, 24, 40, 64, 104),                        # --spacing-* do g1
    "raio": 12,                                                    # cantos dos cards
    "barra": dict(altura=74, logo=48),                             # cabeçalho vermelho
    "destaque": dict(tam=40, entrelinha=48, peso=700, track=-1.8,  # manchete branca sobre a foto
                     sombra=(0, 1, 3, 0.8)),                       # text-shadow 0 1px 3px rgba(0,0,0,.8)
    "resumo": dict(tam=16, entrelinha=20, peso=400, track=-0.32),  # linha fina do destaque
    "chapeu": dict(tam=16, peso=600, track=-0.3),                  # "Suspeita de tornado"
    "meta": dict(tam=12, entrelinha=18, peso=400),                 # "Há 2 horas — Em RS"
    "credito_foto": dict(tam=12, entrelinha=13.2, peso=400),
    "regiao": dict(tam=32, peso=300, track=-1.0),                  # nome da região na barra
}

# ------------------------------------------------------------------ 2) tradução para o Instagram
K = 2   # 1 px do g1 = 2 px no desenho 1080 (a margem de 40 do g1 vira os 80 da área segura)

# Piso de leitura no celular: no Reels, 1 px do desenho 1080 vira ~0,36 pt na tela do telefone.
PISO_TEXTO = 34   # ~12 pt: linha fina e chapéu
PISO_META = 26    # ~9,5 pt: data, cidade


def esp(n: int) -> int:
    """Escala de espaços do g1 x K: esp(0)=8, 1=16, 2=32, 3=48, 4=80, 5=128, 6=208."""
    return G1["espacos"][n] * K


def tam(papel: str, manchete: int) -> int:
    """Tamanho de um texto seguindo a proporção do g1 em relação à manchete, com piso de leitura."""
    piso = PISO_META if papel in ("meta", "credito_foto") else PISO_TEXTO
    return max(round(manchete * G1[papel]["tam"] / G1["destaque"]["tam"]), piso)


def em(papel: str) -> float:
    """Espaço entre letras do g1 em "em" (px / tamanho), para usar em qualquer tamanho."""
    return G1[papel]["track"] / G1[papel]["tam"]


def _escurecer(rgb, fator):
    return tuple(round(c * fator) for c in rgb)


VERMELHO = tuple(int(BRAND_COLOR.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
MARCA = {
    "vermelho": VERMELHO,                                            # primária: barra, monograma
    # secundária na mesma relação do g1 (#a6130a / #c4170c): borda da barra, botões pressionados
    "vermelho_2": _escurecer(VERMELHO, G1["vermelho_2"][0] / G1["vermelho"][0]),
    "branco": (255, 255, 255),
    "preto": (0, 0, 0),
}
COR = {
    "texto": (255, 255, 255),          # branco no preto, como o destaque do g1
    "texto_aux": (214, 214, 214),      # metadado (no g1, #555 sobre branco; aqui o inverso)
    "credito": (196, 196, 196),
    "sombra": (0, 0, 0),
}

# Tipografia no estilo da CNN. A CNN Sans é exclusiva da CNN (sem licença para terceiros), então
# usamos a Inter 4 (SIL OFL), a alternativa livre mais próxima: grotesca neutra, de redação, com duas
# versões como a CNN Sans tem: "Display" (desenhada para tamanhos grandes) e "Text" (para tamanhos pequenos).
# Regras de variação por uso, como na CNN:
#   - manchete: Display Bold, letras apertadas (-2,5%), entrelinha curta (1,10), caixa normal;
#   - chapéu (editoria): Text Bold, CAIXA ALTA, letras abertas (+6%), pequeno, só o texto em branco,
#     sem caixa colorida (pedido do Arthur, 21/11/2026; EDITORIA_CAIXA = True volta a caixa);
#   - linha fina: Text Regular, entrelinha confortável (1,30), quase sem aperto;
#   - data/cidade: Text Medium, cinza, letras levemente abertas (+1%);
#   - crédito da foto: Text Regular, o menor de todos;
#   - legenda do vídeo: Display Bold, apertada (-2%), como os letreiros da tela da CNN.
FONTE = {400: "Inter-Regular.ttf", 500: "Inter-Medium.ttf", 600: "Inter-SemiBold.ttf",
         700: "Inter-Bold.ttf"}
FONTE_DISPLAY = {600: "InterDisplay-SemiBold.ttf", 700: "InterDisplay-Bold.ttf",
                 800: "InterDisplay-ExtraBold.ttf"}
FAMILIA_DISPLAY = "Inter Display"   # nome da família para a legenda (libass)
# REGRA (pedido do Arthur, 20/11/2026): a Inter é a ÚNICA família de letra do PB Minuto. Capa, vídeo,
# legenda do vídeo, logo, avatar e qualquer arte nova usam só os arquivos abaixo (Inter / Inter Display).
# Nada de outra fonte nem de "destaque em outra fonte": destaque é peso, tamanho ou caixa, não família.
# A única exceção são os ícones (MaterialIcons), que são desenhos, não letras. O teste
# tests/test_regra_fonte.py falha se algum arquivo do sistema usar outra fonte.
FONTE_LOGO = {600: FONTE_DISPLAY[600], 700: FONTE_DISPLAY[700], 800: FONTE_DISPLAY[800]}
FONTES_PERMITIDAS = re.compile(r"^(Inter|InterDisplay)-[\w{}]+\.(ttf|otf)$|^MaterialIcons-Regular\.ttf$")
FAMILIAS_PERMITIDAS = ("Inter", "Inter Display")

# Cada tipo de texto: arquivo, espaço entre letras (em), entrelinha e caixa. Tamanhos e espaços
# continuam na escala de antes (proporção em relação à manchete, com piso de leitura).
PAPEIS = {
    "manchete": dict(fonte=FONTE_DISPLAY[700], tamanhos=(68, 64, 60, 56, 52, 48),
                     entrelinha=1.10, track=-0.025, max_linhas=5),
    "linha_fina": dict(fonte=FONTE[400], entrelinha=1.30, track=-0.005, max_linhas=3),
    "chapeu": dict(fonte=FONTE[700], track=0.06, caixa_alta=True),
    "meta": dict(fonte=FONTE[500], track=0.01),
    "credito_foto": dict(fonte=FONTE[400], tam=4, track=0.0),  # 4 px: pedido do Arthur (crédito quase invisível)
    "legenda": dict(fonte=FONTE_DISPLAY[700], track=-0.02),
}

# Editoria dentro de uma caixa com a cor do tema. Regra fixa: cada editoria tem SEMPRE a mesma cor.
# Cores escolhidas pela associação mais comum de cada tema (sinalização, psicologia das cores e
# convenção de redações), todas com contraste de leitura >= 4,5:1 com o texto da caixa (WCAG AA).
# (fundo, texto)
COR_EDITORIA = {
    "POLÍCIA":  ("#B3261E", "#FFFFFF"),  # vermelho escuro: alerta, perigo (mais fechado que o vermelho da marca)
    "POLÍTICA": ("#14213D", "#FFFFFF"),  # azul-marinho: seriedade, poder, instituições
    "SAÚDE":    ("#00838F", "#FFFFFF"),  # verde-azulado hospitalar: cuidado, bem-estar
    "EMPREGO":  ("#C2410C", "#FFFFFF"),  # laranja: energia, oportunidade ("temos vagas")
    "CONCURSO": ("#6A1B9A", "#FFFFFF"),  # roxo: estudo, conquista
    "TRÂNSITO": ("#F5B800", "#111111"),  # amarelo de sinalização de trânsito, texto preto
    "CLIMA":    ("#0277BD", "#FFFFFF"),  # azul-céu: tempo, chuva
    "ESPORTE":  ("#2E7D32", "#FFFFFF"),  # verde-gramado
    "CULTURA":  ("#C2185B", "#FFFFFF"),  # magenta: arte, criatividade, festa
    "ECONOMIA": ("#8A6A00", "#FFFFFF"),  # dourado: dinheiro, preço
    "EDUCAÇÃO": ("#3949AB", "#FFFFFF"),  # azul-índigo: escola, conhecimento
    "SERVIÇO":  ("#5D4037", "#FFFFFF"),  # marrom: utilidade pública, guia prático
    "CIDADE":   ("#37474F", "#FFFFFF"),  # grafite: o urbano, assunto geral da cidade
    "BRASIL":   ("#006B28", "#FFDF00"),  # verde e amarelo da bandeira
}
COR_EDITORIA_PADRAO = COR_EDITORIA["CIDADE"]
# REGRA (pedido do Arthur, 21/11/2026): na capa e nos Reels a editoria vai SÓ como texto (branco,
# CAIXA ALTA), sem o quadrado colorido do tema. COR_EDITORIA fica guardada para quem quiser voltar.
EDITORIA_CAIXA = False
# Caixa da editoria (em múltiplos do tamanho da letra): folga dos lados, acima/abaixo e canto.
# Sem caixa, as folgas são zero e a editoria alinha com a margem da manchete.
CAIXA_EDITORIA = (dict(folga_x=0.55, folga_y=0.42, raio=0.18) if EDITORIA_CAIXA
                  else dict(folga_x=0.0, folga_y=0.0, raio=0.0))


def cor_editoria(chapeu: str) -> tuple:
    """(fundo, texto) em RGB para a editoria; editoria desconhecida usa a cor de CIDADE."""
    fundo, texto = COR_EDITORIA.get((chapeu or "").strip().upper(), COR_EDITORIA_PADRAO)
    rgb = lambda h: tuple(int(h.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))  # noqa: E731
    return rgb(fundo), rgb(texto)

# Sombra do texto (g1: 0 1px 3px preto 80%), x K.
SOMBRA = dict(dy=G1["destaque"]["sombra"][1] * K, raio=G1["destaque"]["sombra"][2] * K,
              opacidade=G1["destaque"]["sombra"][3])

# Proporção da altura das maiúsculas e das descendentes na Inter (medidas do arquivo da fonte), para
# medir espaços pelo olho, do pé de uma linha ao topo da letra da linha seguinte.
ALTURA_MAIUSCULA = 0.7275
DESCENDENTE = 0.2412

# ------------------------------------------------------------------ 3) formatos do Instagram
# Coordenadas no desenho de 1080 de largura (o arquivo final sai em 2K pela ESCALA do vídeo).
# Reels 9:16: a grade do perfil mostra só o meio em 3:4 (y 240 a 1680); na reprodução a interface
# cobre ~250 px no topo, ~380 px embaixo e a coluna de botões à direita.
# A barra vai do topo até "barra"; a parte que aparece na grade (de grade[0] até barra) tem a
# proporção do cabeçalho do g1 e a logo ocupa 48/74 dela, centralizada.
FORMATOS = {
    # pe_capa: pé do texto da capa. Na grade o Instagram desenha o contador de visualizações no canto
    # de baixo (de y ~1510 a ~1620 no desenho 1080x1920): o texto termina acima dele.
    "reels": dict(w=1080, h=1920, margem=80, grade=(240, 1680), barra=388, base_segura=1540,
                  direita_segura=950, largura_texto=900, pe_capa=1460),
    "feed": dict(w=1080, h=1350, margem=80, grade=(0, 1350), barra=148, base_segura=1350,
                 direita_segura=1000, largura_texto=900),
}


def barra(fmt: dict) -> dict:
    """Barra vermelha do topo: altura visível na grade, altura e centro da logo."""
    visivel = fmt["barra"] - fmt["grade"][0]
    logo = round(visivel * G1["barra"]["logo"] / G1["barra"]["altura"])
    return dict(fim=fmt["barra"], logo=logo, centro=fmt["grade"][0] + visivel // 2,
                borda=max(2, K))  # filete da cor secundária no pé da barra


def barra_video() -> dict:
    """Barra do vídeo: colada no topo da tela, na proporção exata do cabeçalho do g1 (74 x K de
    altura, logo de 48 x K no centro). A capa mantém a barra alta, pensada para o corte da grade."""
    alt = G1["barra"]["altura"] * K
    return dict(fim=alt, logo=G1["barra"]["logo"] * K, centro=alt // 2, borda=max(2, K))


# Degradê preto da capa (destaque do g1), mais leve para a foto aparecer: começa logo acima do texto,
# chega ao máximo na altura da data e não passa de ~70% de preto (a sombra do texto garante a leitura).
CAPA_PRETO = dict(antes_do_texto=200, ate=0.80, opacidade=180)

# Vídeo do Reels: posições ajustadas com o Arthur (onda centralizada, legenda abaixo dela).
VIDEO = {
    "topo_seguro": 250,                 # chapéu e data abaixo da faixa que o Instagram cobre
    "fundo_preto": (1010, 1270),        # onde o preto começa e fica sólido (onda + legenda), mais baixo
    "preto": 0.80,                      # quanto de preto sobre a foto desfocada (antes 0,86)
    "preto_video": 0.86,                # com vídeo de fundo: preto sólido (o movimento não atrapalha a legenda)
    # onda logo acima e legenda numa faixa fixa embaixo dela (2 linhas no máximo, centralizadas),
    # sem nunca encostar na onda e terminando antes do nome/legenda do Instagram (~1600)
    "onda": ((1080 - 800) // 2, 1240, 800, 104),   # x, y, largura, altura do visualizador
    "legenda_y": 1480,                  # centro da faixa da legenda (1370 a 1590)
    "legenda_w": 820,                   # largura máxima da legenda (longe dos botões)
}


# Vídeo do parceiro (@jornaldapb, parceiro.py): o vídeo dele com a nossa etiqueta por cima.
# Coordenadas no desenho 1080x1920 (saem em 2K pela ESCALA). Letras, cores e a caixa da editoria
# vêm de PAPEIS/COR/COR_EDITORIA (regra: só Inter; editoria na caixa com a cor fixa do tema).
PARCEIRO = {
    # degradê preto: começa em [0] e fica 100% preto de [1] até o pé da tela, cobrindo a manchete
    # antiga do parceiro (terço de baixo do vídeo)
    "degrade": (760, 1100),
    "pe": FORMATOS["reels"]["base_segura"] - esp(3),   # pé da data (última linha), acima da legenda do IG
    "largura": FORMATOS["reels"]["direita_segura"] - FORMATOS["reels"]["margem"],  # longe dos botões
    "max_linhas": 4,                                   # da manchete; se não couber, a letra diminui
    "editoria_manchete": esp(1),                       # do pé da caixa da editoria ao topo da manchete
    "manchete_meta": esp(2),                           # do pé da manchete à data e cidade
}

def pilha_capa(n_linhas_titulo: int, tam_titulo: int, n_linhas_fina: int, tem_credito: bool,
               fmt: dict) -> dict:
    """Posições (baselines) da pilha da capa, de baixo para cima, como o destaque do g1:
    chapéu, manchete, linha fina, metadado e crédito. Tudo termina acima do corte da grade."""
    t_fina, t_meta = tam("resumo", tam_titulo), tam("meta", tam_titulo)
    t_chapeu, t_cred = tam("chapeu", tam_titulo), PAPEIS["credito_foto"]["tam"]
    cap = lambda t: round(t * ALTURA_MAIUSCULA)  # noqa: E731
    desc = lambda t: round(t * DESCENDENTE)      # noqa: E731
    passo_tit = round(tam_titulo * PAPEIS["manchete"]["entrelinha"])
    passo_fina = round(t_fina * PAPEIS["linha_fina"]["entrelinha"])

    # pé de tudo: acima do contador de visualizações da grade (Reels) ou 48 px acima do corte
    y = fmt.get("pe_capa", fmt["grade"][1] - esp(3))
    pos = {}
    if tem_credito:
        pos["credito"] = y
        y -= cap(t_cred) + esp(1) + desc(t_meta)       # metadado -> crédito: 16
    pos["meta"] = y
    y -= cap(t_meta)
    if n_linhas_fina:
        y -= esp(2) + desc(t_fina)                     # linha fina -> metadado: 32 (g1: 16)
        pos["fina"] = y - passo_fina * (n_linhas_fina - 1)          # baseline da 1ª linha
        y = pos["fina"] - cap(t_fina) - esp(2) - desc(tam_titulo)   # manchete -> linha fina: 32 (g1: 16)
    else:
        y -= esp(2) + desc(tam_titulo)
    pos["titulo"] = y - passo_tit * (n_linhas_titulo - 1)          # baseline da 1ª linha
    folga = round(t_chapeu * CAIXA_EDITORIA["folga_y"])                       # caixa da editoria
    pos["chapeu"] = pos["titulo"] - cap(tam_titulo) - esp(1) - folga           # caixa -> manchete: 16
    pos["topo"] = pos["chapeu"] - cap(t_chapeu) - folga
    pos.update(passo_titulo=passo_tit, passo_fina=passo_fina, tam_fina=t_fina, tam_meta=t_meta,
               tam_chapeu=t_chapeu, tam_credito=t_cred)
    return pos


def cabe(pos: dict, fmt: dict) -> bool:
    """A pilha não sobe até a barra: o texto começa pelo menos 128 px (esp 5) abaixo dela,
    deixando a foto aparecer entre a barra e o texto."""
    return pos["topo"] >= fmt["barra"] + esp(5)
