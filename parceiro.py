"""Vídeos do perfil parceiro (@jornaldapb) refeitos com a marca do PB Minuto.

O Arthur tem autorização do @jornaldapb para usar os vídeos dele que NÃO são collab, trocando a
marca d'água e o texto da tela pela marca e por um texto reescrito do PB Minuto. Vídeos em collab
com outras contas ficam de fora (a autorização não cobre o conteúdo das outras contas).

Fluxo de cada rodada:
  1. lê os posts recentes do perfil pela API oficial (Business Discovery, mesmo token do portal);
  2. para cada parceiro da lista (PARCEIRO_LISTA), fica só com REELS NOVOS (publicados depois da data
     em que o perfil entrou na lista), cujo dono é o próprio parceiro,
     sem sinal de collab e ainda não usados;
  3. baixa o vídeo, transcreve a fala (Whisper) e junta com a legenda do post;
  4. a IA escreve chapéu, manchete e legenda do PB Minuto com outras palavras (sem 4 palavras
     seguidas iguais ao original, sem citar o parceiro) e o texto passa pela skill STE80 Humanizer
     (regra do PB Minuto para toda escrita);
  5. monta o vídeo: desfoca as áreas onde fica a marca/texto do parceiro (PARCEIRO_COBRIR),
     pode cortar faixas de cima/baixo (PARCEIRO_CORTE) e põe por cima a barra vermelha com a logo,
     o degradê preto que cobre a manchete antiga e a etiqueta nova (editoria só em texto,
     manchete e data/cidade), tudo medido pelo layout.py e só em Inter; o áudio original fica;
  6. modo "auto" (padrão, pedido do Arthur): publica já; "review": vai para queue/parceiro esperando o "aprovar".

  python main.py parceiro [--modo review|auto|dry] [--limite N]
  python main.py parceiro-calibrar      quadros do último vídeo com grade em % (para PARCEIRO_COBRIR)
  python main.py parceiro-fila | parceiro-aprovar [--all|ID] | parceiro-descartar ID
"""
import json
import re
import shutil
import subprocess
import time
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFilter

import config

USUARIO = config.env("PARCEIRO_USUARIO", "jornaldapb").lstrip("@").lower()   # parceiro padrão (calibrar)
# Parceiros autorizados (pedido do Arthur): "perfil|desde|opções; ...". "desde" = só Reels publicados
# depois disso (data em que o perfil entrou na lista); opção "grade" = o perfil põe o vídeo dentro de
# uma moldura com a marca dele: o sistema recorta só a parte do vídeo que mexe antes de montar.
# 21/11/2026 (pedido do Arthur): entram também os Reels de ONTEM de todos os parceiros, ou seja,
# desde 20/11/2026 00h de Fortaleza; continuam valendo a janela de 48h e a regra de nunca usar collab.
LISTA_PADRAO = ("jornaldapb|2026-11-20T03:00:00+0000; "
                "paraibabussines_|2026-11-20T03:00:00+0000; "
                "portalresumopb|2026-11-20T03:00:00+0000|grade; "
                "noticiacertapb|2026-11-20T03:00:00+0000; "
                "blognewspb|2026-11-20T03:00:00+0000|grade")
MODO = config.env("PARCEIRO_MODO", "auto")            # auto = publica direto (pedido do Arthur); review = fila
JANELA_HORAS = int(config.env("PARCEIRO_JANELA_HORAS", "48"))   # vídeo mais velho que isso é ignorado
# Só Reels NOVOS (pedido do Arthur): nada publicado antes deste momento entra, mesmo dentro da janela.
# Padrão: quando o @jornaldapb ativou o download dos Reels (20/11/2026, 23h20 de Fortaleza).
DESDE = config.env("PARCEIRO_DESDE", "")   # se preenchida, vale para todos os parceiros
MAX_SEGUNDOS = int(config.env("PARCEIRO_MAX_SEGUNDOS", "180"))
# Áreas a desfocar, em % da tela final 9:16: "x,y,largura,altura; ..." (ex.: "70,3,28,8; 0,70,100,18")
COBRIR = config.env("PARCEIRO_COBRIR", "")
# Faixas do vídeo original a cortar fora (em %): "topo,base" (ex.: "12,15"); o miolo é centralizado
# sobre o próprio vídeo desfocado.
CORTE = config.env("PARCEIRO_CORTE", "0,0")
# Degradê preto (padrão em layout.PARCEIRO; a variável só sobrepõe): "y0,y1" em px de 1920
DEGRADE = tuple(int(v) for v in config.env("PARCEIRO_DEGRADE", "").split(",") if v.strip()) or None
# Procura sozinha a marca d'água do parceiro (logo/texto parado na tela enquanto a imagem mexe) acima
# do degradê e desfoca; "0" desliga. Soma-se às áreas fixas de PARCEIRO_COBRIR.
AUTO_MARCA = config.env("PARCEIRO_AUTO_MARCA", "1") not in ("0", "false", "nao", "não")
# Palavras na legenda do parceiro que indicam collab/parceria com outra conta: o vídeo é pulado.
SINAIS_COLLAB = [s.strip().lower() for s in config.env(
    "PARCEIRO_SINAIS_COLLAB", "collab,colab,em parceria com,parceria com,publi,publicidade,#ad").split(",")
    if s.strip()]



def parceiros(texto: str = None) -> list:
    """[{'usuario', 'desde', 'grade'}] da variável PARCEIRO_LISTA (ou da lista padrão)."""
    texto = texto if texto is not None else config.env("PARCEIRO_LISTA", LISTA_PADRAO)
    lista = []
    for item in texto.split(";"):
        partes = [x.strip() for x in item.split("|")]
        if not partes[0]:
            continue
        lista.append({"usuario": partes[0].lstrip("@").lower(),
                      "desde": DESDE or (partes[1] if len(partes) > 1 else ""),
                      "grade": any(x.lower() == "grade" for x in partes[2:])})
    return lista


ESTADO = config.STATE_DIR / "parceiro.json"
FILA = config.ROOT / "queue" / "parceiro"
FILA.mkdir(parents=True, exist_ok=True)
# Quando a API não manda o arquivo do Reel (media_url vazio: acontece com reels de outra conta,
# principalmente com música do Instagram), baixa direto da página pública do post com o yt-dlp.
# O @jornaldapb ativou o download dos Reels e autorizou o uso; "0" desliga essa reserva.
BAIXAR_PAGINA = config.env("PARCEIRO_BAIXAR_PAGINA", "1") not in ("0", "false", "nao", "não")
# Opcional: cookies de uma conta do Instagram (formato Netscape, um "cookies.txt" exportado do
# navegador) para quando o Instagram exigir login. Use uma conta secundária, não a do PB Minuto.
COOKIES = config.env("PARCEIRO_IG_COOKIES", "")
CAMPOS = "id,media_type,media_product_type,media_url,caption,permalink,timestamp,username"


# ------------------------------------------------------------------ estado (o que já foi usado)
def _estado() -> dict:
    try:
        est = json.loads(ESTADO.read_text(encoding="utf-8"))
    except Exception:
        est = {}
    est.setdefault("vistos", {})
    est.setdefault("tentativas", {})
    return est


def _guardar_estado(est: dict):
    # só os últimos 400 para o arquivo não crescer para sempre
    vistos = dict(sorted(est["vistos"].items(), key=lambda kv: kv[1].get("ts", 0))[-400:])
    tent = {k: v for k, v in est.get("tentativas", {}).items() if k not in vistos}
    ESTADO.parent.mkdir(parents=True, exist_ok=True)
    ESTADO.write_text(json.dumps({"vistos": vistos, "tentativas": tent}, ensure_ascii=False, indent=1),
                      encoding="utf-8")


def _marcar(est: dict, mid: str, status: str, nota: str = ""):
    est["vistos"][mid] = {"ts": time.time(), "status": status, "nota": nota[:200]}


def publicados_24h(caminho: Path = None) -> int:
    """Vídeos de parceiro publicados nas últimas 24h (entram no limite diário das notícias, que
    divide com eles os 100 posts por dia que a API do Instagram aceita)."""
    try:
        arq = caminho or (config.STATE_DIR / "parceiro.json")   # lido na hora (os testes trocam a pasta)
        vistos = json.loads(arq.read_text(encoding="utf-8")).get("vistos", {})
    except Exception:
        return 0
    desde = time.time() - 86400
    return sum(1 for v in vistos.values() if v.get("status") == "publicado" and v.get("ts", 0) > desde)


def _sem_vaga_no_instagram() -> bool:
    """True quando o limite de 24h da API está cheio: o vídeo espera em vez de ser perdido."""
    import publish
    return publish.quota_left() == 0


# ------------------------------------------------------------------ 1-2) buscar e filtrar
def buscar(limite: int = 25, usuario: str = None) -> list:
    """Posts recentes do parceiro pela Business Discovery (a conta dele precisa ser Comercial/Criador)."""
    import publish
    publish._need_creds()
    url = f"https://{config.GRAPH_HOST}/{config.GRAPH_VERSION}/{config.IG_USER_ID}"
    campos = f"business_discovery.username({usuario or USUARIO}){{media.limit({limite}){{{CAMPOS}}}}}"
    r = publish._ig().get(url, params={"fields": campos}, timeout=40)
    dados = publish._check(r)
    return dados.get("business_discovery", {}).get("media", {}).get("data", [])


def motivo_para_pular(m: dict, vistos: dict, agora: float = None, usuario: str = None,
                      desde: str = None) -> str:
    """'' se o post pode ser usado; senão o motivo. Na dúvida, pula (a autorização é só para não-collab)."""
    agora = agora or time.time()
    usuario = usuario or USUARIO
    desde = DESDE if desde is None else desde
    if m.get("id") in vistos:
        return "já usado"
    if m.get("media_type") != "VIDEO":
        return "não é vídeo"
    if m.get("media_product_type") and m["media_product_type"] != "REELS":
        return "não é reels"
    dono = (m.get("username") or "").lower()
    if dono and dono != usuario:
        return f"collab: o dono do post é @{dono}"
    legenda = (m.get("caption") or "").lower()
    for s in SINAIS_COLLAB:
        if re.search(rf"(?<!\w){re.escape(s)}(?!\w)", legenda):
            return f"possível collab/publi (\"{s}\" na legenda)"
    if not m.get("media_url") and not (BAIXAR_PAGINA and m.get("permalink")):
        return "sem link do vídeo (o parceiro desativou downloads ou o vídeo tem música protegida)"
    ts = _epoca(m.get("timestamp", ""))
    if ts is None:
        return "sem data de publicação"
    if agora - ts > JANELA_HORAS * 3600:
        return "antigo"
    desde = _epoca(desde)
    if desde is not None and ts < desde:
        return "antigo"     # só Reels novos, publicados depois de PARCEIRO_DESDE
    return ""


def _epoca(iso: str):
    """'2026-11-21T02:20:00+0000' (UTC, como a API manda) -> segundos desde 1970; None se inválido."""
    import calendar
    try:
        return calendar.timegm(time.strptime(str(iso)[:19], "%Y-%m-%dT%H:%M:%S"))
    except (ValueError, TypeError):
        return None


def baixar(m: dict, destino: Path) -> Path:
    """Arquivo do Reel: pelo link da API; sem ele, pela página pública do post (yt-dlp)."""
    if m.get("media_url"):
        with requests.get(m["media_url"], stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(destino, "wb") as f:
                for parte in r.iter_content(1 << 20):
                    f.write(parte)
        return destino
    if not (BAIXAR_PAGINA and m.get("permalink")):
        raise RuntimeError("sem link do vídeo")
    return baixar_pela_pagina(m["permalink"], destino)


def baixar_pela_pagina(url: str, destino: Path) -> Path:
    """Baixa o vídeo (com áudio) da página do post com o yt-dlp e devolve o .mp4 em `destino`."""
    import tempfile
    import yt_dlp
    destino = Path(destino)
    for velho in destino.parent.glob(destino.stem + ".*"):
        velho.unlink()
    opcoes = {
        "outtmpl": str(destino.parent / (destino.stem + ".%(ext)s")),
        "format": "bv*+ba/b",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "retries": 3,
        "socket_timeout": 60,
    }
    arq_cookies = None
    if COOKIES.strip():
        arq_cookies = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8")
        arq_cookies.write(COOKIES.strip() + "\n")
        arq_cookies.close()
        opcoes["cookiefile"] = arq_cookies.name
    try:
        with yt_dlp.YoutubeDL(opcoes) as ydl:
            ydl.download([url])
    finally:
        if arq_cookies:
            Path(arq_cookies.name).unlink(missing_ok=True)
    feitos = sorted(destino.parent.glob(destino.stem + ".*"))
    if not feitos:
        raise RuntimeError("o yt-dlp não salvou nenhum arquivo")
    if feitos[0] != destino:
        feitos[0].replace(destino)
    if destino.stat().st_size < 50_000:
        raise RuntimeError(f"arquivo pequeno demais ({destino.stat().st_size} bytes)")
    return destino


def testar_download(limite: int = 25) -> bool:
    """Para cada parceiro: baixa o Reel mais recente (sem filtro de data) e monta com o layout, para
    prévia. Não publica, não enfileira e não mexe no estado. True se todos funcionaram."""
    tudo_ok = True
    for k, p in enumerate(parceiros(), 1):
        try:
            ok = _testar_um(p, k, limite)
        except Exception as e:
            print(f"[parceiro] teste @{p['usuario']}: FALHOU ({str(e)[:300]})")
            ok = False
        tudo_ok = tudo_ok and ok
    return tudo_ok


def _testar_um(p: dict, k: int, limite: int) -> bool:
    usuario = p["usuario"]
    posts = buscar(limite, usuario=usuario)
    reels = [m for m in posts if m.get("media_type") == "VIDEO"]
    if not reels:
        print(f"[parceiro] teste @{usuario}: nenhum vídeo entre os {len(posts)} posts")
        return False
    m = max(reels, key=lambda x: x.get("timestamp", ""))
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)
    destino = config.OUT_DIR / f"parceiro_original_{k}.mp4"   # vai para a prévia junto com o montado
    via = "API" if m.get("media_url") else "página do post (yt-dlp)"
    try:
        baixar(m, destino)
    except Exception as e:
        print(f"[parceiro] teste @{usuario}: FALHOU o download de {m.get('permalink')} pela {via}: {str(e)[:400]}")
        return False
    print(f"[parceiro] teste @{usuario}: OK {m.get('permalink')} pela {via}: "
          f"{destino.stat().st_size // 1024} KB, {_duracao(destino):.0f}s, "
          f"áudio={'sim' if _tem_audio(destino) else 'não'}, tamanho={_tamanho(destino)}")
    # o nome casa com o passo "Prévia" do workflow (quadros de 1s e 4s no ramo previa-parceiro)
    final = config.OUT_DIR / f"parceiro_teste_{k}.mp4"
    try:
        card = escrever(m.get("caption") or "", transcrever(destino))
        if card.get("skip"):
            print(f"[parceiro] teste @{usuario}: a IA pularia este vídeo ({card.get('motivo', '')}); "
                  "montando assim mesmo só para ver o layout")
        print(f"[parceiro] teste @{usuario}: {card.get('chapeu')} | {card.get('titulo')} | {card.get('cidade')}")
        montar(destino, card, final, grade=p["grade"])
        print(f"[parceiro] teste @{usuario}: vídeo montado -> {final.name}")
    except Exception as e:
        print(f"[parceiro] teste @{usuario}: baixou, mas falhou a montagem: {str(e)[:400]}")
        return False
    return True


def _duracao(video: Path) -> float:
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                            str(video)], capture_output=True, text=True, timeout=30)
        return float(r.stdout.strip() or 0)
    except Exception:
        return 0.0


# ------------------------------------------------------------------ 3) o que o vídeo diz
def transcrever(video: Path) -> str:
    """Fala do vídeo em texto (Whisper na CPU). '' se não houver áudio ou Whisper."""
    try:
        import audiograma
        palavras = audiograma._whisper(video)
        return " ".join(p for p, *_ in palavras)
    except Exception as e:
        print(f"[parceiro] sem transcrição ({str(e)[:100]})")
        return ""


# ------------------------------------------------------------------ 4) texto novo do PB Minuto
SISTEMA = """Você é o editor do {portal}. Recebe a legenda e a transcrição de um vídeo de
notícia de um portal parceiro, que autorizou o uso do vídeo. O vídeo vai ao ar com a marca do
{portal}, então o texto precisa ser TODO nosso.
Regras:
- Use só fatos que estão no material. Nada inventado.
- Outras palavras e outra estrutura: nenhuma sequência de 4 palavras seguidas igual ao material.
- Nunca cite o portal parceiro, @, sites, veículos ou jornalistas.
- chapeu: editoria em MAIÚSCULAS, uma destas: {editorias}.
- titulo: a etiqueta que aparece na tela; frase informativa no presente, até 12 palavras e
  80 caracteres, sem ponto final, sem exclamação, específica (quem, o quê, onde).
- legenda: 3 blocos separados por linha em branco: 1) o fato com 1 emoji no início;
  2) contexto em 2 a 4 frases simples; 3) uma chamada curta para comentar ou compartilhar.
  Sem hashtags e sem "siga" (o sistema acrescenta).
- cidade: "Campina Grande", "João Pessoa", "Paraíba" ou "Brasil".
- hashtags: 5 a 7, sem '#', locais primeiro.
- risco: "skip" para suicídio, crime sexual, menor identificável, acusação sem confirmação contra
  pessoa identificada ou boato; "cuidado" para polícia/acidente/morte (sem nomes de vítimas ou
  suspeitos, atribuindo à autoridade); "ok" para o resto.
- skip = true se o material não tiver fato claro (só propaganda, sorteio, vídeo sem notícia).
{regra_escrita}
Responda APENAS com JSON: skip, motivo, risco, chapeu, titulo, legenda, cidade, hashtags."""


def _regra_escrita() -> str:
    """A REGRA DE ESCRITA da skill STE80 Humanizer, a mesma do editor do portal."""
    import editor
    i = editor.SYSTEM.find("REGRA DE ESCRITA DO PB MINUTO")
    j = editor.SYSTEM.find("Responda APENAS", i)
    return editor.SYSTEM[i:j].strip() if i >= 0 and j > i else ""


def _palavras(t: str) -> list:
    return re.findall(r"[\wÀ-ÿ]+", (t or "").lower())


def repetidos(novo: str, original: str, n: int = 4) -> list:
    """Sequências de n palavras do texto novo que também estão no original."""
    o = _palavras(original)
    grams = {" ".join(o[i:i + n]) for i in range(len(o) - n + 1)}
    p = _palavras(novo)
    return sorted({" ".join(p[i:i + n]) for i in range(len(p) - n + 1)} & grams)


def escrever(legenda_original: str, transcricao: str, tentativas: int = 3) -> dict:
    import editor
    sistema = SISTEMA.format(portal=config.PORTAL_NAME, editorias=", ".join(editor.EDITORIAS),
                             regra_escrita=_regra_escrita())
    material = f"LEGENDA DO POST:\n{legenda_original.strip()}\n\nFALA DO VÍDEO:\n{transcricao.strip()}"
    original = legenda_original + " " + transcricao
    pedido, card = material, {}
    for _ in range(tentativas):
        card = editor._extract_json(editor.generate(pedido, sistema))
        if card.get("skip") or card.get("risco") == "skip":
            card["skip"] = True
            return card
        rep = repetidos(" ".join([card.get("titulo", ""), card.get("legenda", "")]), original)
        if not rep:
            break
        pedido = (material + "\n\nSUA VERSÃO ANTERIOR repetiu trechos do material; reescreva "
                  f"tudo com outras palavras. Trechos repetidos: {rep[:12]}")
    else:
        raise ValueError("a IA não conseguiu escrever sem repetir o original")
    for k in ("titulo", "legenda", "chapeu"):
        if not str(card.get(k, "")).strip():
            raise ValueError(f"faltou o campo {k}")
    card["titulo"] = " ".join(card["titulo"].split()).rstrip(".!")
    card["chapeu"] = card["chapeu"].strip().upper()
    if card["chapeu"] not in editor.EDITORIAS:
        card["chapeu"] = "CIDADE"
    card["hashtags"] = [re.sub(r"[^\wÀ-ÿ]", "", str(h)) for h in card.get("hashtags", [])][:7]
    card.setdefault("pontos", [])
    # regra do PB Minuto: todo texto passa pela skill STE80 Humanizer (sem voltar a copiar o original)
    if config.HUMANIZAR:
        revisado = editor.humanizar(dict(card), None, validar=False)
        if repetidos(" ".join([revisado.get("titulo", ""), revisado.get("legenda", "")]), original):
            print("[parceiro] revisão descartada (ficou parecida com o original)")
        else:
            card = revisado
            card["titulo"] = " ".join(card["titulo"].split()).rstrip(".!")
    return card


# ------------------------------------------------------------------ 5) visual
def caixas(texto: str) -> list:
    """'70,3,28,8; 0,70,100,18' -> [(70,3,28,8), (0,70,100,18)] em %, validado."""
    out = []
    for parte in (texto or "").split(";"):
        nums = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", parte)]
        if len(nums) != 4:
            continue
        x, y, w, h = nums
        x, y = max(0.0, min(x, 100.0)), max(0.0, min(y, 100.0))
        w, h = max(0.0, min(w, 100.0 - x)), max(0.0, min(h, 100.0 - y))
        if w >= 1 and h >= 1:
            out.append((x, y, w, h))
    return out


def corte(texto: str) -> tuple:
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", texto or "")] + [0, 0]
    return min(nums[0], 45.0), min(nums[1], 45.0)


def _degrade_parceiro(camada: Image.Image):
    """Degradê preto que cobre a manchete antiga do parceiro (suave no começo, sólido a partir de y1)."""
    import audiograma as A
    import layout as L
    W, H = camada.size
    y0, y1 = (A.z(v) for v in (DEGRADE or L.PARCEIRO["degrade"]))
    dd = ImageDraw.Draw(camada)
    for y in range(y0, H):
        t = min(1.0, (y - y0) / max(y1 - y0, 1))
        dd.line((0, y, W, y), fill=L.MARCA["preto"] + (round(255 * t * t * (3 - 2 * t)),))


def etiqueta(card: dict, out_png: Path) -> Path:
    """Camada transparente do tamanho do vídeo, toda medida por layout.py (só Inter): barra vermelha
    com a logo (barra_video), degradê preto que cobre a manchete antiga (PARCEIRO["degrade"]) e a
    etiqueta nova alinhada à esquerda, como o destaque da capa: editoria na caixa com a cor fixa do
    tema (COR_EDITORIA), manchete (papel "manchete", com sombra) e data e cidade (papel "meta")."""
    import audiograma as A
    import layout as L
    import logo as _logo

    P, z = L.PARCEIRO, A.z
    W, H = A.VW, A.VH
    camada = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    # 1) degradê preto (suave no começo, sólido a partir de y1)
    _degrade_parceiro(camada)

    # 2) barra do topo com a logo
    b = L.barra_video()
    camada.alpha_composite(_logo.barra(W, z(b["fim"]), z(b["logo"]), z(b["centro"]), z(b["borda"])), (0, 0))

    # 3) manchete: maior tamanho da lista que cabe em max_linhas
    man = L.PAPEIS["manchete"]
    largura = z(P["largura"])
    for tam in man["tamanhos"]:
        linhas = A._quebrar(A._palavras_com_fonte(card["titulo"], [], z(tam)), largura, track=man["track"])
        if len(linhas) <= P["max_linhas"]:
            break
    passo = round(z(tam) * man["entrelinha"])
    cap = lambda t: round(z(t) * L.ALTURA_MAIUSCULA)   # noqa: E731
    desc = lambda t: round(z(t) * L.DESCENDENTE)        # noqa: E731

    # posições de baixo para cima (baselines), como layout.pilha_capa
    meta_p = L.PAPEIS["meta"]
    t_meta, t_chap = L.tam("meta", tam), L.tam("chapeu", tam)
    y_meta = z(P["pe"])
    y_ult = y_meta - cap(t_meta) - z(P["manchete_meta"]) - desc(tam)
    y_tit = y_ult - passo * (len(linhas) - 1)
    folga = round(z(t_chap) * L.CAIXA_EDITORIA["folga_y"])
    y_chap = y_tit - cap(tam) - z(P["editoria_manchete"]) - folga
    m = z(L.FORMATOS["reels"]["margem"])

    d = ImageDraw.Draw(camada)
    A._editoria(d, m, y_chap, card, z(t_chap))          # editoria só em texto (layout.EDITORIA_CAIXA)

    # manchete + data/cidade numa camada própria, para levar a sombra
    txt = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dt = ImageDraw.Draw(txt)
    for i, linha in enumerate(linhas):
        x = m
        for p, f, _ in linha:
            x += A._texto(dt, (x, y_tit + i * passo), p, f, L.COR["texto"], track=man["track"]) + f.getlength(" ")
    f_meta = A.fonte(meta_p["fonte"], z(t_meta))
    A._texto(dt, (m, y_meta), f"{A._data_g1()}  —  {card.get('cidade') or 'Paraíba'}", f_meta,
             L.COR["texto_aux"], track=meta_p["track"])
    sombra = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sombra.putalpha(txt.split()[3].point(lambda v: int(v * L.SOMBRA["opacidade"])))
    sombra = sombra.filter(ImageFilter.GaussianBlur(z(L.SOMBRA["raio"]) / 2))
    camada.alpha_composite(sombra, (0, z(L.SOMBRA["dy"])))
    camada.alpha_composite(txt)
    camada.save(out_png)
    return out_png


def _filtro(cobrir: list, topo: float, base: float, W: int, H: int) -> str:
    """Filtro do FFmpeg: enquadra o vídeo 9:16, corta faixas e desfoca as áreas da marca antiga."""
    partes = []
    if topo or base:
        meio = (100 - topo - base) / 100
        partes.append("[0:v]split[s1][s2]")
        partes.append(f"[s1]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                      f"boxblur=40:3,eq=brightness=-0.12[fundo]")
        partes.append(f"[s2]crop=iw:ih*{meio:.4f}:0:ih*{topo / 100:.4f},"
                      f"scale={W}:{H}:force_original_aspect_ratio=decrease,setsar=1[miolo]")
        partes.append("[fundo][miolo]overlay=(W-w)/2:(H-h)/2[v0]")
    else:
        partes.append(f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1[v0]")
    atual = "v0"
    for i, (x, y, w, h) in enumerate(cobrir):
        px, py = round(W * x / 100), round(H * y / 100)
        pw, ph = max(2, round(W * w / 100) // 2 * 2), max(2, round(H * h / 100) // 2 * 2)
        raio = max(4, min(pw, ph) // 4)
        partes.append(f"[{atual}]split[a{i}][b{i}]")
        partes.append(f"[b{i}]crop={pw}:{ph}:{px}:{py},boxblur={raio}:4[c{i}]")
        partes.append(f"[a{i}][c{i}]overlay={px}:{py}[v{i + 1}]")
        atual = f"v{i + 1}"
    partes.append(f"[{atual}][1:v]overlay=0:0,format=yuv420p,fps=30[saida]")
    return ";".join(partes)


def _tem_audio(video: Path) -> bool:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                        "-of", "csv=p=0", str(video)], capture_output=True, text=True)
    return bool(r.stdout.strip())


def detectar_marcas(video: Path, amostras: int = 16) -> list:
    """Áreas (x, y, largura, altura em % da tela 9:16) com marca d'água ou texto parado do parceiro.
    Marca d'água = pedaço com contorno (letra/logo) que fica IGUAL em todos os quadros enquanto a
    imagem atrás mexe. Só olha acima do degradê (abaixo dele o preto já cobre tudo). Se quase tudo
    estiver parado (câmera fixa), não dá para separar marca de cenário: devolve []."""
    import numpy as np
    import layout as L
    W, H, C = 360, 640, 18                      # 18 px = 5% da largura
    dur = _duracao(video) or 10.0
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf",
                        f"fps={amostras / max(dur, 1):.4f},scale={W}:{H}:force_original_aspect_ratio=increase,"
                        f"crop={W}:{H},format=gray", "-f", "rawvideo", "-"], capture_output=True, timeout=300)
    n = len(r.stdout) // (W * H)
    if n < 6:
        return []
    q = np.frombuffer(r.stdout[:n * W * H], dtype=np.uint8).reshape(n, H, W).astype(np.float32)
    var = q.std(axis=0)
    borda = (np.abs(np.diff(q, axis=2))[:, :-1, :] + np.abs(np.diff(q, axis=1))[:, :, :-1]).mean(axis=0)
    y_fim = (DEGRADE or L.PARCEIRO["degrade"])[0] / 1920      # começo do degradê
    lin, col = int(H * y_fim) // C, W // C
    # pixel de marca: não muda entre os quadros e é contorno (letra/logo); a célula conta como marca
    # quando boa parte dos pixels dela é assim (pega também letra fina sem fundo, como um @ na tela)
    px_marca = (var[:H - 1, :W - 1] < 10) & (borda > 20)
    parado = np.zeros((lin, col), bool)
    for i in range(lin):
        for j in range(col):
            parado[i, j] = px_marca[i * C:(i + 1) * C, j * C:(j + 1) * C].mean() > 0.12
    if parado.mean() > 0.25:
        return []
    areas, visto = [], np.zeros_like(parado)
    for i in range(lin):
        for j in range(col):
            if not parado[i, j] or visto[i, j]:
                continue
            pilha, cel = [(i, j)], []
            visto[i, j] = True
            while pilha:
                a, b = pilha.pop()
                cel.append((a, b))
                for da in (-1, 0, 1):
                    for db in (-1, 0, 1):
                        x, y = a + da, b + db
                        if 0 <= x < lin and 0 <= y < col and parado[x, y] and not visto[x, y]:
                            visto[x, y] = True
                            pilha.append((x, y))
            i0, i1 = min(c[0] for c in cel) - 1, max(c[0] for c in cel) + 2      # 1 célula de folga
            j0, j1 = min(c[1] for c in cel) - 1, max(c[1] for c in cel) + 2
            i0, j0, j1 = max(i0, 0), max(j0, 0), min(j1, col)
            px = lambda v, tot: round(100 * v * C / tot, 1)  # noqa: E731
            areas.append((px(j0, W), px(i0, H), px(j1 - j0, W), px(i1 - i0, H)))
    return areas


def _tamanho(video: Path) -> tuple:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height", "-of", "csv=p=0", str(video)], capture_output=True, text=True)
    w, h = r.stdout.strip().split("\n")[0].split(",")[:2]
    return int(w), int(h)


def detectar_video(video: Path, amostras: int = 16):
    """Na moldura ("grade") de alguns parceiros, só o vídeo de dentro mexe; a moldura com a marca fica
    parada. Devolve (x, y, largura, altura) em pixels do vídeo original da parte que mexe, ou None se
    o vídeo já ocupa quase a tela toda (não há moldura para tirar)."""
    import numpy as np
    W0, H0 = _tamanho(video)
    W = 360
    H = max(2, round(W * H0 / W0 / 2) * 2)
    dur = _duracao(video) or 10.0
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf",
                        f"fps={amostras / max(dur, 1):.4f},scale={W}:{H},format=gray", "-f", "rawvideo", "-"],
                       capture_output=True, timeout=300)
    n = len(r.stdout) // (W * H)
    if n < 6:
        return None
    q = np.frombuffer(r.stdout[:n * W * H], dtype=np.uint8).reshape(n, H, W).astype(np.float32)
    mexe = q.std(axis=0) > 12

    def faixa(frac):
        # linha/coluna "mexe" com pouco movimento já (cena parada, ex.: entrevista); buracos curtos
        # (até 4% do tamanho) dentro da faixa não a quebram
        ativo = list(frac > 0.08)
        buraco = max(2, len(ativo) // 25)
        i = 0
        while i < len(ativo):
            if not ativo[i]:
                j = i
                while j < len(ativo) and not ativo[j]:
                    j += 1
                if 0 < i and j < len(ativo) and j - i <= buraco:
                    ativo[i:j] = [True] * (j - i)
                i = j
            else:
                i += 1
        melhor, ini = (0, 0), None
        for i, a in enumerate(ativo + [False]):
            if a and ini is None:
                ini = i
            elif not a and ini is not None:
                if i - ini > melhor[1] - melhor[0]:
                    melhor = (ini, i)
                ini = None
        return melhor

    y0, y1 = faixa(mexe.mean(axis=1))
    if y1 - y0 < H * 0.15:
        return None
    x0, x1 = faixa(mexe[y0:y1].mean(axis=0))
    if x1 - x0 < W * 0.15:
        return None
    if (y1 - y0) > H * 0.92 and (x1 - x0) > W * 0.92:
        return None
    k = W0 / W
    x, y = int(x0 * k) // 2 * 2, int(y0 * H0 / H) // 2 * 2
    w, h = int((x1 - x0) * k) // 2 * 2, int((y1 - y0) * H0 / H) // 2 * 2
    return x, y, min(w, W0 - x), min(h, H0 - y)


def recortar_grade(origem: Path) -> Path:
    """Tira a moldura do parceiro: grava só a parte do vídeo que mexe (com o áudio)."""
    caixa = detectar_video(origem)
    if not caixa:
        print("[parceiro] grade: não achei moldura, uso o vídeo inteiro")
        return origem
    x, y, w, h = caixa
    saida = origem.with_name(origem.stem + "_recorte.mp4")
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(origem), "-vf", f"crop={w}:{h}:{x}:{y}",
           "-c:v", "libx264", "-preset", "medium", "-crf", "16"]
    cmd += ["-c:a", "copy"] if _tem_audio(origem) else ["-an"]
    subprocess.run(cmd + [str(saida)], check=True, capture_output=True, timeout=900)
    print(f"[parceiro] grade: recortei só o vídeo ({w}x{h} em {x},{y})")
    return saida


def _filtro_encaixe(W: int, H: int, y_topo: int) -> str:
    """Vídeo largo (ex.: 16:9 tirado da moldura): vai inteiro logo abaixo da barra, acima do degradê,
    sobre o próprio vídeo ampliado e desfocado."""
    return (f"[0:v]split[s1][s2];[s1]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
            f"boxblur=40:3,eq=brightness=-0.12[fundo];"
            f"[s2]scale={W}:-2,setsar=1[miolo];[fundo][miolo]overlay=0:{y_topo}[v0];"
            f"[v0][1:v]overlay=0:0,format=yuv420p,fps=30[saida]")


def montar(origem: Path, card: dict, out_mp4: Path, grade: bool = False) -> Path:
    import audiograma as A
    import layout as L
    png = etiqueta(card, out_mp4.with_suffix(".etiqueta.png"))
    if grade:
        origem = recortar_grade(origem)
    topo, base = corte(CORTE)
    cobrir = caixas(COBRIR)
    w0, h0 = _tamanho(origem)
    if w0 / h0 > 0.8:     # largo demais para encher a tela 9:16 sem cortar a cena
        filtro = _filtro_encaixe(A.VW, A.VH, A.z(L.barra_video()["fim"]))
        _quadro_limpo(origem, filtro, out_mp4)
        return _rodar_ffmpeg(origem, png, filtro, out_mp4)
    if AUTO_MARCA and not (topo or base):
        try:
            achadas = detectar_marcas(origem)
        except Exception as e:
            achadas = []
            print(f"[parceiro] não deu para procurar marca d'água ({str(e)[:120]})")
        if achadas:
            print(f"[parceiro] marca d'água/texto parado desfocado em: {achadas}")
        cobrir += achadas
    filtro = _filtro(cobrir, topo, base, A.VW, A.VH)
    _quadro_limpo(origem, filtro, out_mp4)
    return _rodar_ffmpeg(origem, png, filtro, out_mp4)


def _quadro_limpo(origem: Path, filtro: str, out_mp4: Path, segundo: float = 1.0) -> Path:
    """Um quadro do vídeo já tratado (marca d'água desfocada, moldura recortada, manchete antiga sob o
    degradê), sem a nossa barra nem texto: é a foto da capa do Reels. Falha aqui não para o vídeo."""
    from PIL import Image as _Img
    import audiograma as A
    out_jpg = out_mp4.with_suffix(".limpo.jpg")
    png = out_mp4.with_suffix(".degrade.png")
    camada = _Img.new("RGBA", (A.VW, A.VH), (0, 0, 0, 0))
    _degrade_parceiro(camada)
    camada.save(png)
    try:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(segundo), "-i", str(origem), "-loop", "1",
                        "-i", str(png), "-filter_complex", filtro, "-map", "[saida]", "-frames:v", "1",
                        "-q:v", "2", str(out_jpg)], check=True, capture_output=True, timeout=120)
    except Exception as e:
        print(f"[parceiro] sem quadro limpo para a capa ({str(e)[:120]})")
    return out_jpg


def _rodar_ffmpeg(origem: Path, png: Path, filtro: str, out_mp4: Path) -> Path:
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(origem), "-loop", "1", "-i", str(png),
           "-filter_complex", filtro, "-map", "[saida]"]
    if _tem_audio(origem):
        cmd += ["-map", "0:a:0", "-c:a", "aac", "-b:a", "160k"]
    cmd += ["-t", str(MAX_SEGUNDOS), "-shortest", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-profile:v", "high", "-movflags", "+faststart", str(out_mp4)]
    subprocess.run(cmd, check=True, capture_output=True, timeout=900)
    return out_mp4


def capa(video: Path, out_jpg: Path, segundo: float = 1.0, card: dict = None) -> Path:
    """Capa do Reels no mesmo padrão das notícias (barra vermelha visível na grade, foto, manchete,
    data e cidade acima do contador de visualizações), com a foto tirada do vídeo já tratado.
    Sem o quadro limpo (ou sem o card), usa um quadro do vídeo pronto."""
    limpo = video.with_suffix(".limpo.jpg")
    if card and limpo.exists():
        try:
            import audiograma as A
            return A.capa(dict(card, _credito=""), out_jpg, image_path=limpo)
        except Exception as e:
            print(f"[parceiro] capa no padrão falhou, uso um quadro do vídeo ({str(e)[:120]})")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(segundo), "-i", str(video), "-frames:v", "1",
                    "-q:v", "2", str(out_jpg)], check=True, capture_output=True)
    return out_jpg


# ------------------------------------------------------------------ 6) publicar ou enfileirar
def _publicar(card: dict, video: Path, capa_jpg: Path) -> str:
    import publish
    return publish.post_reel(video, publish.build_caption(card), capa=str(capa_jpg))


def rodada(modo: str = None, limite: int = 1) -> int:
    """Uma rodada em todos os parceiros: até `limite` vídeos novos de cada um. Devolve quantos fez."""
    est = _estado()
    total = 0
    for p in parceiros():
        total += _rodada_parceiro(p, est, modo or MODO, limite)
    if (modo or MODO) != "dry":
        _guardar_estado(est)
    return total


def _rodada_parceiro(p: dict, est: dict, modo: str, limite: int) -> int:
    usuario = p["usuario"]
    feitos = 0
    try:
        posts = buscar(usuario=usuario)
    except Exception as e:
        print(f"[parceiro] não deu para ler @{usuario}: {str(e)[:300]}")
        return 0
    print(f"[parceiro] @{usuario}: {len(posts)} posts lidos")
    for m in sorted(posts, key=lambda x: x.get("timestamp", "")):   # do mais antigo ao mais novo
        if feitos >= limite:
            break
        motivo = motivo_para_pular(m, est["vistos"], usuario=usuario, desde=p["desde"])
        if motivo:
            if motivo not in ("já usado", "antigo", "não é vídeo") and modo != "dry":
                _marcar(est, m["id"], "pulado", motivo)
            if motivo != "já usado":
                print(f"[parceiro] pulei {m.get('permalink', m.get('id'))}: {motivo}")
            continue
        if modo == "auto" and _sem_vaga_no_instagram():
            print("[parceiro] limite de 24h do Instagram cheio: o vídeo fica para a próxima rodada")
            break
        stamp = f"parceiro_{m['id']}"
        pasta = config.OUT_DIR
        pasta.mkdir(parents=True, exist_ok=True)
        try:
            origem = baixar(m, pasta / f"{stamp}_original.mp4")
            card = escrever(m.get("caption") or "", transcrever(origem))
            if card.get("skip"):
                print(f"[parceiro] a IA pulou {m.get('permalink')}: {card.get('motivo', '')}")
                if modo != "dry":
                    _marcar(est, m["id"], "pulado", "IA: " + str(card.get("motivo", "")))
                continue
            card["_origem"] = {"id": m["id"], "permalink": m.get("permalink"), "timestamp": m.get("timestamp"),
                               "parceiro": usuario}
            video = montar(origem, card, pasta / f"{stamp}.mp4", grade=p["grade"])
            capa_jpg = capa(video, pasta / f"{stamp}_capa.jpg", card=card)
        except Exception as e:
            print(f"[parceiro] falhou {m.get('permalink')}: {str(e)[:300]}")
            if modo != "dry":  # tenta de novo nas próximas rodadas; na 3ª falha desiste
                tent = est["tentativas"].get(m["id"], 0) + 1
                est["tentativas"][m["id"]] = tent
                if tent >= 3:
                    _marcar(est, m["id"], "erro", str(e))
            continue
        print(f"[parceiro] pronto: {card['chapeu']} | {card['titulo']}")
        if modo == "dry":
            feitos += 1
            continue
        if modo == "auto":
            try:
                mid = _publicar(card, video, capa_jpg)
                _marcar(est, m["id"], "publicado", mid)
                print(f"[parceiro] publicado {mid}")
            except Exception as e:
                _marcar(est, m["id"], "falha_publicacao", str(e))
                print(f"[parceiro] falha ao publicar: {str(e)[:300]}")
        else:
            for arq in (video, capa_jpg):
                shutil.copy(arq, FILA / arq.name)
            card["_video"], card["_capa"] = video.name, capa_jpg.name
            (FILA / f"{stamp}.json").write_text(json.dumps(card, ensure_ascii=False, indent=1), encoding="utf-8")
            _marcar(est, m["id"], "na_fila")
            print(f"[parceiro] na fila para aprovar: {stamp}")
        feitos += 1
    return feitos


def aprovar(todos: bool = False, ident: str = "") -> int:
    est = _estado()
    n = 0
    for js in sorted(FILA.glob("*.json")):
        if not todos and js.stem != ident:
            continue
        card = json.loads(js.read_text(encoding="utf-8"))
        video, capa_jpg = FILA / card["_video"], FILA / card["_capa"]
        try:
            mid = _publicar(card, video, capa_jpg)
        except Exception as e:
            print(f"[parceiro] falhou {js.stem}: {str(e)[:300]}")
            continue
        _marcar(est, card["_origem"]["id"], "publicado", mid)
        for f in (js, video, capa_jpg):
            f.unlink(missing_ok=True)
        print(f"[parceiro] publicado {mid}: {card['titulo']}")
        n += 1
    _guardar_estado(est)
    return n


def descartar(ident: str) -> bool:
    """Tira um vídeo da fila sem publicar (e não volta mais)."""
    js = FILA / f"{ident}.json"
    if not js.exists():
        return False
    card = json.loads(js.read_text(encoding="utf-8"))
    for nome in (card.get("_video"), card.get("_capa")):
        if nome:
            (FILA / nome).unlink(missing_ok=True)
    js.unlink()
    est = _estado()
    _marcar(est, card["_origem"]["id"], "descartado")
    _guardar_estado(est)
    return True


def calibrar() -> list:
    """Baixa o vídeo mais recente do parceiro e salva 3 quadros 9:16 com uma grade de 10 em 10%
    (e as áreas de PARCEIRO_COBRIR em vermelho), para medir onde ficam a marca e o texto dele."""
    import audiograma as A
    posts = [m for m in buscar(12) if m.get("media_type") == "VIDEO" and m.get("media_url")]
    if not posts:
        raise RuntimeError(f"nenhum vídeo com link disponível em @{USUARIO}")
    m = posts[0]
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)
    origem = baixar(m, config.OUT_DIR / "calibrar_original.mp4")
    saidas = []
    for s in (1, 4, 8):
        q = config.OUT_DIR / f"calibrar_{s}s.jpg"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(s), "-i", str(origem), "-frames:v", "1",
                        "-vf", f"scale={A.VW}:{A.VH}:force_original_aspect_ratio=increase,crop={A.VW}:{A.VH}",
                        str(q)], check=True, capture_output=True)
        im = Image.open(q).convert("RGB")
        d = ImageDraw.Draw(im)
        W, H = im.size
        for i in range(1, 10):
            d.line((W * i / 10, 0, W * i / 10, H), fill=(0, 255, 255), width=2)
            d.line((0, H * i / 10, W, H * i / 10), fill=(0, 255, 255), width=2)
            d.text((6, H * i / 10 + 4), f"{i * 10}%", fill=(0, 255, 255))
            d.text((W * i / 10 + 4, 6), f"{i * 10}%", fill=(0, 255, 255))
        for x, y, w, h in caixas(COBRIR):
            d.rectangle((W * x / 100, H * y / 100, W * (x + w) / 100, H * (y + h) / 100), outline=(255, 0, 0), width=6)
        im.save(q, quality=90)
        saidas.append(q)
    print(f"[parceiro] calibrar: {m.get('permalink')} -> {[p.name for p in saidas]}")
    return saidas
