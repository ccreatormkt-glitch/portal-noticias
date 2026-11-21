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
                         # montagens de várias fotos (ficam bagunçadas como fundo)
                         r"compilation|compilacao|montage|montagem|collage|colagem|mosaic|mosaico|"
                         r"composite|composicao|panel|grid|"
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
            if NAO_E_FOTO.search(_fold(p.get("title", ""))) or NAO_E_FOTO.search(onde) and _re.search(
                    r"compilation|montage|montagem|collage|colagem|mosaic", onde) or info.get("mime") not in (None, "image/jpeg"):
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


# ------------------------------------------------------------------ bancos de fotos grátis
# Pedido do Arthur: toda imagem vem de uma busca por palavras-chave num banco de fotos, e a IA escolhe.
# Pixabay (API grátis: 100 buscas/min; buscas guardadas por 24 h, como a API exige; fotos baixadas,
# nunca linkadas) e Pexels (a emissão de chaves novas estava pausada em 20/11/2026; liga sozinho
# se a chave existir). Licenças: uso livre, sem pessoa identificável em contexto negativo,
# político ou de doença. Por isso, numa notícia, foto com gente fica de fora: um rosto qualquer
# pareceria ser de alguém envolvido no fato.
PEXELS_URL = "https://api.pexels.com/v1/search"
PIXABAY_URL = "https://pixabay.com/api/"
BANCO_MAX_BUSCAS = 4           # buscas por notícia (cabe folgado nos limites das APIs)
PEXELS_MAX_BUSCAS = BANCO_MAX_BUSCAS
CACHE_BUSCAS = Path(__file__).parent / ".cache" / "bancos_de_fotos.json"
PESSOAS = _re.compile(
    r"\b(man|men|woman|women|person|people|persons|girl|girls|boy|boys|child|children|kid|kids|baby|"
    r"toddler|teen|teenager|couple|family|portrait|selfie|crowd|face|faces|guy|lady|gentleman|"
    r"businessman|businesswoman|student|students|doctor|nurse|officer|policeman|worker|workers|"
    r"athlete|player|model|bride|groom|homem|mulher|pessoa|pessoas|menina|menino|crianca|retrato)\b")
TEMA_PEXELS = {  # palavras-chave de reserva por editoria: cenas e objetos, sem gente
    "CIDADE": "city street aerial", "POLÍCIA": "police car lights night", "POLÍTICA": "government building",
    "SAÚDE": "hospital corridor", "EMPREGO": "office desk work", "CONCURSO": "exam paper pencil",
    "TRÂNSITO": "traffic road cars", "CLIMA": "storm clouds sky", "ESPORTE": "football stadium",
    "CULTURA": "stage lights concert", "ECONOMIA": "money coins calculator", "EDUCAÇÃO": "empty classroom",
    "SERVIÇO": "public office counter", "BRASIL": "brazil city skyline", "PARAÍBA": "beach coast brazil",
}


def palavras_chave(card: dict) -> list:
    """Buscas para o banco de fotos, da mais fiel ao fato para a mais geral: primeiro as da IA que LEU
    a notícia inteira; depois a do editor e a da leitura da foto da matéria original; por último, a
    da editoria. Cada busca: {"q": texto, "lang": "en" ou "pt"}. A foto ainda passa pela IA, que só
    aprova se corresponder à notícia."""
    import editor
    try:
        da_ia = editor.palavras_foto(card).get("buscas", [])
    except Exception as e:
        print(f"[banco] IA não gerou as palavras-chave ({str(e)[:60]}): uso as do editor")
        da_ia = []
    buscas = [*da_ia, {"q": card.get("foto_busca", ""), "lang": "en"},
              {"q": _visao(card).get("busca_en", ""), "lang": "en"}]
    if not da_ia and card.get("foto_busca") and len(card["foto_busca"].split()) > 2:
        buscas.append({"q": " ".join(card["foto_busca"].split()[:2]), "lang": "en"})
    buscas.append({"q": TEMA_PEXELS.get(card.get("chapeu", ""), ""), "lang": "en"})
    vistas, saida = set(), []
    for b in buscas:
        q = " ".join(str(b.get("q") or "").split())[:80]
        if q and q.lower() not in vistas:
            vistas.add(q.lower())
            saida.append({"q": q, "lang": b.get("lang", "en")})
    return saida


def _cache(banco: str, busca: str, buscar, lang: str = "en"):
    """Guarda cada busca por 24 h (exigência do Pixabay; economiza o limite do Pexels)."""
    import json
    import time
    chave = f"{banco}:{lang}:{busca.lower()}"
    try:
        dados = json.loads(CACHE_BUSCAS.read_text()) if CACHE_BUSCAS.exists() else {}
    except Exception:
        dados = {}
    agora = time.time()
    dados = {k: v for k, v in dados.items() if agora - v.get("t", 0) < 86400}
    if chave in dados:
        return dados[chave]["fotos"]
    fotos = buscar()
    dados[chave] = {"t": agora, "fotos": fotos}
    CACHE_BUSCAS.parent.mkdir(parents=True, exist_ok=True)
    CACHE_BUSCAS.write_text(json.dumps(dados))
    return fotos


def _busca_pexels(busca: str, lang: str = "en") -> list:
    from config import PEXELS_API_KEY
    r = requests.get(PEXELS_URL, headers={"Authorization": PEXELS_API_KEY}, timeout=(5, 15), params={
        "query": busca, "orientation": "portrait", "size": "large", "per_page": 15,
        "locale": "pt-BR" if lang == "pt" else "en-US"})
    if r.status_code == 429:
        raise RuntimeError("limite de buscas do Pexels atingido")
    r.raise_for_status()
    return [{"id": f"pexels:{f.get('id')}", "texto": f.get("alt") or "", "w": f.get("width", 0),
             "h": f.get("height", 0), "autor": f.get("photographer") or "Pexels",
             "miniatura": (f.get("src") or {}).get("medium"),
             "grande": f"{(f.get('src') or {}).get('original')}?auto=compress&cs=tinysrgb&h=2600"}
            for f in r.json().get("photos", [])]


def _busca_pixabay(busca: str, lang: str = "en") -> list:
    from config import PIXABAY_API_KEY
    r = requests.get(PIXABAY_URL, timeout=(5, 15), params={
        "key": PIXABAY_API_KEY, "q": busca[:100], "lang": lang, "image_type": "photo",
        "orientation": "vertical", "min_height": 1600, "safesearch": "true", "per_page": 20})
    if r.status_code == 429:
        raise RuntimeError("limite de buscas do Pixabay atingido")
    r.raise_for_status()
    return [{"id": f"pixabay:{f.get('id')}", "texto": (f.get("tags") or "").replace(",", " "),
             "w": f.get("imageWidth", 0), "h": f.get("imageHeight", 0), "autor": f.get("user") or "Pixabay",
             "miniatura": f.get("webformatURL"),
             "grande": f.get("fullHDURL") or f.get("largeImageURL")}   # 1920 se a conta tiver acesso total
            for f in r.json().get("hits", [])]


def bancos_ativos() -> list:
    """(nome, site, função de busca) dos bancos com chave configurada, na ordem de preferência."""
    from config import PEXELS_API_KEY, PIXABAY_API_KEY
    bancos = []
    if PEXELS_API_KEY:
        bancos.append(("Pexels", "pexels.com", _busca_pexels))
    if PIXABAY_API_KEY:
        bancos.append(("Pixabay", "pixabay.com", _busca_pixabay))
    return bancos


def _filtrar(fotos: list) -> list:
    """Sem as já usadas, as pequenas e as com gente, texto ou letreiro na descrição."""
    usadas = _usadas()
    boas = []
    for f in fotos:
        texto = _fold(f.get("texto", ""))
        if f["id"] in usadas or min(f.get("w", 0), f.get("h", 0)) < 1000 or max(f.get("w", 0), f.get("h", 0)) < 1500:
            continue
        if PESSOAS.search(texto) or NAO_E_FOTO.search(texto) or LETREIRO.search(texto):
            continue
        if f.get("miniatura") and f.get("grande"):
            boas.append(f)
    return boas


def _candidatas_pexels(busca: str) -> list:  # mantido para os testes e para uso direto
    return _filtrar(_busca_pexels(busca))


def foto_banco(card: dict, base: Path):
    """Busca por palavras-chave no banco de fotos, a IA escolhe a que melhor combina com a notícia
    (e recusa as que têm gente, texto ou logo), baixa e devolve (arquivo, crédito)."""
    bancos = bancos_ativos()
    if not bancos:
        print("[banco] sem chave do Pixabay/Pexels (segredos PIXABAY_API_KEY / PEXELS_API_KEY): outras fontes")
        return None
    import editor
    buscas = palavras_chave(card)[:BANCO_MAX_BUSCAS]
    cena = (card.get("_foto_ia") or {}).get("cena", "")
    if cena:
        print(f"[banco] foto ideal: {cena}")
    for nome, site, buscar in bancos:
        for b in buscas:
            busca, lang = b["q"], b["lang"]
            try:
                cands = _filtrar(_cache(nome, busca, lambda: buscar(busca, lang), lang))[:8]
            except Exception as e:
                print(f"[banco] {nome} '{busca}': {str(e)[:80]}")
                if "limite" in str(e):
                    break
                continue
            if not cands:
                print(f"[banco] {nome} '{busca}': nada utilizável")
                continue
            miniaturas = []
            for f in cands:
                try:
                    m = requests.get(f["miniatura"], timeout=(5, 15))
                    m.raise_for_status()
                    miniaturas.append((m.content, m.headers.get("content-type", "image/jpeg").split(";")[0]))
                except Exception:
                    miniaturas.append(None)
            validas = [f for f, m in zip(cands, miniaturas) if m]
            try:  # a IA lê a notícia e só aprova foto que corresponda ao fato (ou cena bem parecida)
                idx = editor.escolher_foto(card, [m for m in miniaturas if m], cena=cena)
                escolhida = validas[idx] if idx is not None and 0 <= idx < len(validas) else None
            except Exception as e:  # sem IA para conferir, não arrisca foto que não combine
                print(f"[banco] a IA não conseguiu conferir as fotos ({str(e)[:60]})")
                escolhida = None
            if escolhida is None:
                print(f"[banco] {nome} '{busca}': nenhuma das {len(cands)} fotos corresponde à notícia")
                continue
            try:
                img = requests.get(escolhida["grande"], timeout=(5, 40))
                img.raise_for_status()
            except Exception as e:
                print(f"[banco] download falhou ({type(e).__name__})")
                continue
            destino = Path(f"{base}_banco.jpg")
            destino.write_bytes(img.content)
            _marcar(escolhida["id"])
            autor = " ".join(str(escolhida.get("autor") or nome).split())[:40]
            print(f"[banco] {nome} '{busca}': foto {escolhida['id']} de {autor}")
            card["_credito_legenda"] = f"📷 Foto: {autor} / {nome} ({site})"
            return destino, f"Foto: {autor} / {nome}"
    return None


foto_pexels = foto_banco  # nome antigo


# ------------------------------------------------------------------ vídeo de banco (Pixabay)
PIXABAY_VIDEO_URL = "https://pixabay.com/api/videos/"
VIDEO_MIN_ALTURA = 1600     # altura mínima do trecho: abaixo disso o vídeo 2K sairia ampliado (borrado)
VIDEO_MAX_BYTES = 150_000_000
VIDEO_MIN_SEG = 6


def _busca_pixabay_videos(busca: str, lang: str = "en") -> list:
    """Trechos de vídeo do Pixabay; de cada um, a versão mais leve que ainda tem altura suficiente."""
    from config import PIXABAY_API_KEY
    r = requests.get(PIXABAY_VIDEO_URL, timeout=(5, 15), params={
        "key": PIXABAY_API_KEY, "q": busca[:100], "lang": lang, "video_type": "film",
        "safesearch": "true", "per_page": 30})
    if r.status_code == 429:
        raise RuntimeError("limite de buscas do Pixabay atingido")
    r.raise_for_status()
    saida = []
    for v in r.json().get("hits", []):
        versoes = [x for x in ((v.get("videos") or {}).get(k) or {} for k in ("medium", "large"))
                   if x.get("url") and x.get("height", 0) >= VIDEO_MIN_ALTURA
                   and 0 < (x.get("size") or 1) <= VIDEO_MAX_BYTES]
        if not versoes:
            continue
        x = versoes[0]                      # a mais leve que já basta (medium vertical, senão large 4K)
        mini = ((v.get("videos") or {}).get("medium") or {}).get("thumbnail") or x.get("thumbnail")
        saida.append({"id": f"pixabay-video:{v.get('id')}", "texto": (v.get("tags") or "").replace(",", " "),
                      "w": x.get("width", 0), "h": x.get("height", 0), "seg": v.get("duration", 0),
                      "autor": v.get("user") or "Pixabay", "miniatura": mini, "grande": x["url"]})
    saida.sort(key=lambda c: c["h"] < c["w"])   # verticais primeiro (sem corte), depois as 4K deitadas
    return saida


def _filtrar_videos(cands: list) -> list:
    usadas = _usadas()
    boas = []
    for c in cands:
        texto = _fold(c.get("texto", ""))
        if c["id"] in usadas or c.get("seg", 0) < VIDEO_MIN_SEG or not c.get("miniatura"):
            continue
        if PESSOAS.search(texto) or NAO_E_FOTO.search(texto) or LETREIRO.search(texto):
            continue
        boas.append(c)
    return boas


def _quadro_do_video(mp4: Path, destino: Path, seg: float) -> bool:
    """Um quadro nítido do próprio trecho, para a capa do Reels (capa e vídeo combinam)."""
    import subprocess
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{min(1.5, seg / 3):.2f}", "-i", str(mp4),
                        "-frames:v", "1", "-q:v", "1", str(destino)], capture_output=True)
    return r.returncode == 0 and destino.exists() and destino.stat().st_size > 0


def video_banco(card: dict, base: Path):
    """Fundo do Reels em movimento: busca trechos de vídeo no Pixabay com as mesmas palavras-chave da
    foto, a IA olha a miniatura de cada um e só aprova o que corresponde à notícia (sem gente, texto ou
    logo). Devolve (vídeo, quadro para a capa, crédito) ou None (aí entra a foto, como antes)."""
    from config import PIXABAY_API_KEY, VIDEO_FUNDO
    if not (VIDEO_FUNDO and PIXABAY_API_KEY):
        return None
    import editor
    buscas = palavras_chave(card)[:BANCO_MAX_BUSCAS]
    cena = (card.get("_foto_ia") or {}).get("cena", "")
    for b in buscas:
        busca, lang = b["q"], b["lang"]
        try:
            cands = _filtrar_videos(_cache("PixabayVideo", busca, lambda: _busca_pixabay_videos(busca, lang),
                                           lang))[:8]
        except Exception as e:
            print(f"[vídeo] Pixabay '{busca}': {str(e)[:80]}")
            if "limite" in str(e):
                break
            continue
        if not cands:
            print(f"[vídeo] Pixabay '{busca}': nenhum trecho utilizável (altura >= {VIDEO_MIN_ALTURA}px)")
            continue
        miniaturas = []
        for c in cands:
            try:
                m = requests.get(c["miniatura"], timeout=(5, 15))
                m.raise_for_status()
                miniaturas.append((m.content, m.headers.get("content-type", "image/jpeg").split(";")[0]))
            except Exception:
                miniaturas.append(None)
        validas = [c for c, m in zip(cands, miniaturas) if m]
        try:
            idx = editor.escolher_foto(card, [m for m in miniaturas if m], cena=cena)
            escolhido = validas[idx] if idx is not None and 0 <= idx < len(validas) else None
        except Exception as e:
            print(f"[vídeo] a IA não conseguiu conferir os trechos ({str(e)[:60]})")
            escolhido = None
        if escolhido is None:
            print(f"[vídeo] Pixabay '{busca}': nenhum dos {len(cands)} trechos corresponde à notícia")
            continue
        destino = Path(f"{base}_fundo.mp4")
        try:
            with requests.get(escolhido["grande"], timeout=(5, 120), stream=True) as r:
                r.raise_for_status()
                with open(destino, "wb") as f:
                    for bloco in r.iter_content(1 << 20):
                        f.write(bloco)
        except Exception as e:
            print(f"[vídeo] download falhou ({type(e).__name__})")
            continue
        capa = Path(f"{base}_fundo.jpg")
        if not _quadro_do_video(destino, capa, escolhido.get("seg", 6)):
            print("[vídeo] não consegui tirar o quadro da capa; vou de foto")
            continue
        _marcar(escolhido["id"])
        autor = " ".join(str(escolhido.get("autor") or "Pixabay").split())[:40]
        print(f"[vídeo] Pixabay '{busca}': trecho {escolhido['id']} de {autor} "
              f"({escolhido['w']}x{escolhido['h']}, {escolhido.get('seg')}s)")
        card["_credito_legenda"] = f"🎬 Vídeo: {autor} / Pixabay (pixabay.com)"
        return destino, capa, f"Vídeo: {autor} / Pixabay"
    return None


def imagem_de_fundo(card: dict, base: Path):
    """Toda arte tem imagem, sem textos. A foto da matéria original NUNCA vai para a arte (costuma
    ter texto, logo ou marca do site): serve só de referência. Ordem de reserva:
    1) foto livre do lugar ligado ao fato, na cidade citada (Wikimedia Commons, com crédito);
    2) a cena da notícia refeita por IA, a partir da foto original ou do texto ("Ilustração por IA");
    3) foto livre ligada ao assunto (tema da notícia), sem pessoas em destaque nem letreiros;
    4) vista geral da cidade citada (Wikimedia Commons, "Imagem ilustrativa");
    5) só se tudo falhar: fundo da marca com ícone.
    Antes de tudo, o trecho de VÍDEO de banco (Pixabay, pedido do Arthur): o vídeo vira o fundo do Reels
    e um quadro dele vira a capa. Sem vídeo bom, o banco de fotos: palavras-chave da notícia -> busca no
    Pixabay (ou Pexels) -> a IA escolhe. As outras fontes só entram se o banco não tiver foto boa."""
    card["_credito"], card["_ilustrativa"], card["_credito_legenda"] = "", False, ""
    card.pop("_video_fundo", None)
    try:  # primeiro: trecho de vídeo de banco (fundo em movimento); o quadro dele vira a capa
        achou = video_banco(card, base)
    except Exception as e:
        print(f"[vídeo] busca falhou ({type(e).__name__}); vou de foto")
        achou = None
    if achou:
        card["_video_fundo"] = str(achou[0])
        card["_ilustrativa"], card["_credito"] = True, achou[2]
        return achou[1]
    achou = foto_banco(card, base)
    if achou:
        card["_ilustrativa"], card["_credito"] = True, achou[1]
        return achou[0]
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
