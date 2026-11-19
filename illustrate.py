"""Foto de fundo das notícias.

Regra: só foto da cidade citada na notícia, de banco livre (Wikimedia Commons), com crédito
pequeno na arte. A foto da matéria original nunca é publicada: serve só de referência para a busca.
Sem foto boa da cidade, a arte sai com o ícone do assunto. O post nunca deixa de sair por isso.
"""
import base64
from pathlib import Path
from urllib.parse import urlsplit

import requests

from config import GEMINI_API_KEY, GEMINI_IMAGE_MODEL, IMAGE_MODE

GUARD = ("Editorial illustration for a news story, painterly digital art, soft cinematic light, "
         "vertical 9:16 composition, no text, no letters, no logos, no flags, no recognizable people, "
         "no faces, no weapons, no blood, not a photograph. Scene: ")


def _cena(card: dict) -> str:
    """O que desenhar: a cena da foto da matéria (descrita pela IA, sem pessoas nem textos);
    sem ela, o próprio texto da notícia."""
    v = _visao(card)
    return v.get("cena_en") or card.get("imagem_prompt") or card.get("foto_busca") or card.get("titulo", "")


def _pollinations(prompt: str, out_path: Path):
    """Reserva gratuita e sem chave para refazer a imagem (image.pollinations.ai, modelo flux).
    Gera um pouco mais alta e corta a faixa de baixo, onde o serviço pode pôr a marca dele."""
    import hashlib
    from urllib.parse import quote
    from PIL import Image
    seed = int(hashlib.sha1(prompt.encode()).hexdigest()[:6], 16)
    url = (f"https://image.pollinations.ai/prompt/{quote(prompt[:900])}"
           f"?width=1080&height=2048&model=flux&nologo=true&safe=true&seed={seed}")
    try:
        r = requests.get(url, headers=UA, timeout=(10, 120))
        tipo = r.headers.get("content-type", "")
        if r.status_code != 200 or not tipo.startswith("image/") or len(r.content) < 20_000:
            print(f"[ilustração] pollinations: HTTP {r.status_code} {tipo[:20]}")
            return None
        bruto = Path(out_path).with_suffix(".bruto")
        bruto.write_bytes(r.content)
        im = Image.open(bruto).convert("RGB")
        im = im.crop((0, 0, im.width, int(im.height * 0.93)))  # tira a faixa de baixo
        destino = Path(out_path).with_suffix(".jpg")
        im.save(destino, quality=92)
        bruto.unlink(missing_ok=True)
        print("[ilustração] gerada com pollinations (flux)")
        return destino
    except Exception as e:
        print(f"[ilustração] pollinations: {type(e).__name__}")
        return None


def ilustracao_ia(card: dict, out_path: Path):
    """Refaz a imagem com IA: Gemini (se a chave tiver cota de imagem) ou, de reserva, Pollinations."""
    prompt = GUARD + _cena(card)
    if IMAGE_MODE == "gemini" and GEMINI_API_KEY:
        body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseModalities": ["IMAGE"]}}
        for model in [m.strip() for m in GEMINI_IMAGE_MODEL.split(",") if m.strip()]:
            try:
                r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                                  json=body, headers={"x-goog-api-key": GEMINI_API_KEY}, timeout=(10, 120))
                if r.status_code != 200:
                    print(f"[ilustração] {model}: HTTP {r.status_code}")
                    continue
                for part in r.json()["candidates"][0]["content"]["parts"]:
                    data = part.get("inlineData") or part.get("inline_data")
                    if data:
                        Path(out_path).write_bytes(base64.b64decode(data["data"]))
                        print(f"[ilustração] gerada com {model}")
                        return Path(out_path)
            except Exception as e:
                print(f"[ilustração] {model}: {type(e).__name__}")
    if IMAGE_MODE in ("gemini", "pollinations"):
        return _pollinations(prompt, Path(out_path))
    return None


def _usadas() -> set:
    from config import STATE_DIR
    p = STATE_DIR / "fotos_usadas.txt"
    return set(p.read_text().split()) if p.exists() else set()


def _marcar(pid: str):
    from config import STATE_DIR
    with open(STATE_DIR / "fotos_usadas.txt", "a") as f:
        f.write(pid + "\n")


SEM_FOTO = ("POLÍCIA", "URGENTE")
UA = {"User-Agent": "PBMinutoBot/1.0 (portal de noticias; contato via Instagram @pbminuto)"}
LICENCAS_OK = ("cc0", "pdm", "public domain", "domínio público", "cc by", "cc-by", "by", "by-sa")


def _licenca_ok(nome: str) -> bool:
    n = (nome or "").lower().replace("-", " ")
    if " nc" in f" {n}" or " nd" in f" {n}" or "nc" in n.split() or "nd" in n.split():
        return False  # sem uso comercial ou sem adaptação: fora
    return any(x.replace("-", " ") in n for x in LICENCAS_OK)


def _texto(html: str) -> str:
    import re
    return " ".join(re.sub(r"<[^>]+>", " ", html or "").split())


def foto_original(card: dict):
    """Acha a foto de capa da matéria original (og:image), respeitando o robots.txt.
    Usada para descrever a cena e, como último recurso (fora de polícia), na arte com crédito
    "Reprodução". Devolve (bytes, tipo, domínio) ou None."""
    import re

    import editor
    for link in card.get("links", []):
        if not link or "news.google.com" in link or not editor._robots_ok(link):
            continue
        try:
            r = requests.get(link, headers=UA, timeout=(5, 12))
            m = re.search(r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]+content=["\']([^"\']+)',
                          r.text) or re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']og:image',
                                               r.text)
            if not m:
                continue
            img = requests.get(m.group(1), headers=UA, timeout=(5, 15))
            tipo = img.headers.get("content-type", "image/jpeg").split(";")[0]
            if img.status_code == 200 and tipo.startswith("image/") and 10_000 < len(img.content) < 6_000_000:
                return img.content, tipo, urlsplit(link).netloc.replace("www.", "")
        except Exception:
            continue
    return None


def _fold(t: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()


import re as _re

NAO_E_FOTO = _re.compile(r"\b(map|mapa|carta|planta|brasao|bandeira|flag|coat of arms|escudo|logo|"
                         r"desenho|drawing|gravura|engraving|pintura|painting|diagrama|seal|selo|"
                         # imagens com texto (o Arthur pediu arte sem imagem com texto)
                         r"cartaz|poster|banner|placa|sign|signage|letreiro|outdoor|billboard|panfleto|"
                         r"flyer|screenshot|captura|infografico|infographic|texto|text|jornal|newspaper|"
                         r"1[5-8]\d\d)\b")


def buscar_commons(busca: str, out_path: Path, exigir=(), repetir=False, sem=None):
    """Wikimedia Commons: ótimo para lugares (praças, prédios, ruas) de CG e JP. Exige crédito.
    `exigir`: palavras que precisam estar no nome ou na descrição do arquivo (ex.: a cidade),
    para não pegar um prédio parecido de outro país."""
    if not busca:
        return None
    try:
        r = requests.get("https://commons.wikimedia.org/w/api.php", headers=UA, timeout=(5, 15), params={
            "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
            "gsrsearch": f"{busca} filetype:bitmap", "gsrlimit": 12, "prop": "imageinfo",
            "iiprop": "url|extmetadata|size|mime", "iiurlwidth": 1920})  # tamanho padrão do Wikimedia (outros dão erro)
        paginas = (r.json().get("query") or {}).get("pages", {}).values()
        usadas = _usadas()
        for p in sorted(paginas, key=lambda x: x.get("index", 99)):
            info = (p.get("imageinfo") or [{}])[0]
            meta = info.get("extmetadata", {})
            lic = (meta.get("LicenseShortName") or {}).get("value", "")
            pid = "commons:" + str(p.get("pageid"))
            if (pid in usadas and not repetir) or info.get("width", 0) < 1000 or not _licenca_ok(lic):
                continue
            onde = _fold(p.get("title", "") + " " + _texto((meta.get("ImageDescription") or {}).get("value", "")))
            if exigir and not any(_fold(x) in onde for x in exigir):
                continue
            if (sem is not None and sem.search(onde)) or LETREIRO.search(onde):
                continue
            if NAO_E_FOTO.search(_fold(p.get("title", ""))) or info.get("mime") not in (None, "image/jpeg"):
                continue  # mapas, brasões, bandeiras, desenhos antigos: não servem de foto de notícia
            img = None
            for url in (info.get("thumburl"), info.get("url")):  # miniatura padrão; se falhar, o original
                if not url:
                    continue
                r2 = requests.get(url, headers=UA, timeout=(5, 30))
                if r2.status_code == 200 and r2.headers.get("content-type", "").startswith("image/"):
                    img = r2
                    break
            if img is None:
                continue
            Path(out_path).write_bytes(img.content)
            _marcar(pid)
            autor = _texto((meta.get("Artist") or {}).get("value", "")) or "autor desconhecido"
            return Path(out_path), f"Foto: {autor[:40]} / Wikimedia Commons ({lic})"
    except Exception as e:
        print(f"[foto] Commons sem resultado ({type(e).__name__})")
    return None


# cidades da Paraíba que aparecem nas notícias (para exigir que a foto seja do lugar citado)
CIDADES_PB = ["Campina Grande", "João Pessoa", "Cabedelo", "Bayeux", "Santa Rita", "Conde", "Lucena",
              "Patos", "Sousa", "Cajazeiras", "Guarabira", "Monteiro", "Queimadas", "Esperança",
              "Areia", "Bananeiras", "Pombal", "Itaporanga", "Princesa Isabel", "Mamanguape",
              "Lagoa Seca", "Alagoa Grande", "Catolé do Rocha", "Picuí", "Solânea", "Sapé"]


def cidades_citadas(card: dict) -> list:
    """Cidades citadas no texto da notícia (a primeira é a principal)."""
    texto = _fold(" ".join([card.get("titulo", ""), card.get("linha_fina", ""), card.get("resumo", ""),
                            card.get("cidade", "")]))
    achadas = [c for c in CIDADES_PB if _fold(c) in texto]
    if not achadas and _fold(card.get("cidade", "")) == "paraiba":
        achadas = ["Paraíba"]
    return achadas


_ORIG = {}


def _original(card: dict):
    """Busca a foto da matéria uma vez só por notícia (fica em memória, fora do card)."""
    chave = card.get("fp") or card.get("titulo", "")
    if chave not in _ORIG:
        _ORIG[chave] = foto_original(card)
    return _ORIG[chave]


_VISAO = {}


def _visao(card: dict) -> dict:
    """Descrição da foto da matéria (a foto só é LIDA, nunca publicada), uma vez por notícia."""
    chave = card.get("fp") or card.get("titulo", "")
    if chave not in _VISAO:
        _VISAO[chave] = {}
        orig = _original(card)
        if orig:
            try:
                import editor
                _VISAO[chave] = editor.ver_imagem(orig[0], orig[1], f"Notícia: {card.get('titulo', '')}") or {}
            except Exception as e:
                print(f"[foto] não consegui descrever a foto original ({str(e)[:80]})")
    return _VISAO[chave]


def foto_parecida(card: dict, base: Path):
    """Foto livre de um lugar específico da CIDADE CITADA (Wikimedia Commons, conferindo o nome da
    cidade no arquivo). A foto da matéria original só serve de referência para a busca."""
    cidades = cidades_citadas(card)
    if not cidades:
        return None
    principal = cidades[0]
    v = _visao(card)
    buscas = [v.get("busca_lugar", ""), card.get("foto_local", "")]
    if v.get("busca_en"):
        buscas.append(f"{v['busca_en']} {principal}")
    destino = Path(f"{base}_foto.jpg")
    vistas = set()
    for q in buscas:
        if not q or q.lower() in vistas:
            continue
        vistas.add(q.lower())
        achou = buscar_commons(q, destino, exigir=cidades, sem=RETRATO)
        if achou:
            print(f"[foto] {principal}: '{q}'")
            return achou
    print(f"[foto] nenhum lugar específico de {principal} no Wikimedia")
    return None


def foto_semelhante(card: dict, base: Path):
    """Foto livre ligada ao ASSUNTO da notícia (parecida com a da matéria ou com o tema do texto):
    objetos e cenas genéricas, sem pessoas em destaque, sem letreiros e sem lugar identificável de
    outra cidade (Wikimedia Commons, imagem ilustrativa)."""
    v = _visao(card)
    destino = Path(f"{base}_semelhante.jpg")
    vistas = set()
    buscas = [v.get("busca_en", ""), card.get("foto_busca", "")]
    if not cidades_citadas(card):  # notícia de fora da Paraíba: pode ser o lugar da foto original
        buscas.insert(0, v.get("busca_lugar", ""))
    for q in buscas:
        if not q or q.lower() in vistas:
            continue
        vistas.add(q.lower())
        achou = buscar_commons(q, destino, sem=RETRATO)
        if achou:
            print(f"[foto] semelhante: '{q}'")
            return achou
    return None


RETRATO = _re.compile(r"\b(retrato|portrait|selfie|deputad|vereador|prefeit|governador|senador|candidat)")
# fachadas comerciais quase sempre têm letreiro/logo (texto na imagem): fora da arte
LETREIRO = _re.compile(r"\b(shopping|mall|loja|store|fachada|facade|letreiro|logo|marca|supermercado|"
                       r"atacad|farmacia|pharmacy|hotel|banco do|caixa economica|bradesco|itau|santander|"
                       r"agencia|outdoor|placa|totem|posto de combustivel|gas station|restaurante|restaurant)")


def foto_da_cidade(card: dict, base: Path):
    """Reserva: vista geral da cidade citada (Wikimedia Commons), marcada como imagem ilustrativa.
    Sem mapas, brasões ou retratos de pessoas. Repete uma foto já usada só se não houver outra."""
    cidades = cidades_citadas(card)
    if not cidades:
        return None
    cidade = cidades[0]
    destino = Path(f"{base}_cidade.jpg")
    buscas = [f"{cidade} Paraíba", f"vista {cidade}", f"centro {cidade}", cidade]
    if cidade == "Paraíba":
        buscas = ["Paraíba Brasil paisagem", "João Pessoa orla", "Campina Grande"]
    for repetir in (False, True):
        for q in buscas:
            achou = buscar_commons(q, destino, exigir=[cidade, "Paraiba"] if cidade == "Paraíba" else [cidade],
                                   repetir=repetir, sem=RETRATO)
            if achou:
                print(f"[foto] vista geral de {cidade}: '{q}'")
                return achou
    return None


def imagem_de_fundo(card: dict, base: Path):
    """Toda arte tem imagem, sem textos. A foto da matéria original NUNCA vai para a arte (costuma
    ter texto, logo ou marca do site): serve só de referência. Ordem:
    1) foto livre do lugar ligado ao fato, na cidade citada (Wikimedia Commons, com crédito);
    2) a cena da notícia refeita por IA, a partir da foto original ou do texto ("Ilustração por IA");
    3) foto livre ligada ao assunto (tema da notícia), sem pessoas em destaque nem letreiros;
    4) vista geral da cidade citada (Wikimedia Commons, "Imagem ilustrativa");
    5) só se tudo falhar: fundo da marca com ícone."""
    card["_credito"], card["_ilustrativa"] = "", False
    sensivel = card.get("chapeu") in SEM_FOTO or card.get("risco") == "cuidado"
    if not sensivel:
        achou = foto_parecida(card, base)
        if achou:
            card["_ilustrativa"], card["_credito"] = True, achou[1]
            return achou[0]
    img = ilustracao_ia(card, Path(f"{base}_ia.png"))
    if img:
        card["_credito"] = "Ilustração gerada por IA"
        return img
    achou = (None if sensivel else foto_semelhante(card, base)) or foto_da_cidade(card, base)
    if achou:
        card["_ilustrativa"], card["_credito"] = True, achou[1]
        return achou[0]
    print("[foto] sem imagem nenhuma; arte com ícone")
    return None
