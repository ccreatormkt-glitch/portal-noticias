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


def ilustracao_ia(card: dict, out_path: Path):
    """Ilustração gerada pela IA do Google (Gemini) a partir do texto da notícia."""
    if IMAGE_MODE != "gemini" or not GEMINI_API_KEY:
        return None
    cena = card.get("imagem_prompt") or card.get("foto_busca") or card.get("titulo", "")
    body = {"contents": [{"parts": [{"text": GUARD + cena}]}],
            "generationConfig": {"responseModalities": ["IMAGE"]}}
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


def buscar_commons(busca: str, out_path: Path, exigir=()):
    """Wikimedia Commons: ótimo para lugares (praças, prédios, ruas) de CG e JP. Exige crédito.
    `exigir`: palavras que precisam estar no nome ou na descrição do arquivo (ex.: a cidade),
    para não pegar um prédio parecido de outro país."""
    if not busca:
        return None
    try:
        r = requests.get("https://commons.wikimedia.org/w/api.php", headers=UA, timeout=(5, 15), params={
            "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
            "gsrsearch": f"{busca} filetype:bitmap", "gsrlimit": 12, "prop": "imageinfo",
            "iiprop": "url|extmetadata|size", "iiurlwidth": 1920})  # tamanho padrão do Wikimedia (outros dão erro)
        paginas = (r.json().get("query") or {}).get("pages", {}).values()
        usadas = _usadas()
        for p in sorted(paginas, key=lambda x: x.get("index", 99)):
            info = (p.get("imageinfo") or [{}])[0]
            meta = info.get("extmetadata", {})
            lic = (meta.get("LicenseShortName") or {}).get("value", "")
            pid = "commons:" + str(p.get("pageid"))
            if pid in usadas or info.get("width", 0) < 1000 or not _licenca_ok(lic):
                continue
            onde = _fold(p.get("title", "") + " " + _texto((meta.get("ImageDescription") or {}).get("value", "")))
            if exigir and not any(_fold(x) in onde for x in exigir):
                continue
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


def foto_parecida(card: dict, base: Path):
    """Foto livre da CIDADE CITADA na notícia (Wikimedia Commons, conferindo o nome da cidade
    no arquivo). A foto da matéria original só serve de referência para a busca. Sem foto da
    cidade, não usa foto nenhuma (a arte sai com o ícone do assunto)."""
    import editor
    cidades = cidades_citadas(card)
    if not cidades:
        return None
    principal = cidades[0]
    buscas = [card.get("foto_local", "")]
    orig = _original(card)
    if orig:
        try:
            desc = editor.ver_imagem(orig[0], orig[1], f"Notícia: {card.get('titulo', '')}")
            buscas.insert(0, desc.get("busca_lugar", ""))
            if desc.get("busca_en"):
                buscas.append(f"{desc['busca_en']} {principal}")
        except Exception as e:
            print(f"[foto] não consegui descrever a foto original ({str(e)[:80]})")
    if card.get("foto_busca"):
        buscas.append(f"{card['foto_busca']} {principal}")
    buscas.append(principal)  # por último: uma foto conhecida da própria cidade
    destino = Path(f"{base}_foto.jpg")
    vistas = set()
    for q in buscas:
        if not q or q.lower() in vistas:
            continue
        vistas.add(q.lower())
        achou = buscar_commons(q, destino, exigir=cidades)
        if achou:
            print(f"[foto] {principal}: '{q}'")
            return achou
    print(f"[foto] nenhuma foto livre de {principal}; arte com ícone")
    return None


def imagem_de_fundo(card: dict, base: Path):
    """Toda arte tem imagem. Ordem:
    1) foto livre da cidade citada (Wikimedia Commons, com crédito);
    2) ilustração gerada pela IA do Google a partir do texto ("Ilustração gerada por IA");
    3) foto da própria matéria, com crédito "Reprodução/<site>" (NUNCA em polícia/tema sensível,
       para não expor suspeitos ou vítimas);
    4) só se tudo falhar: fundo da marca com ícone."""
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
    if not sensivel:
        orig = _original(card)
        if orig:
            destino = Path(f"{base}_materia.jpg")
            destino.write_bytes(orig[0])
            card["_credito"] = f"Foto: Reprodução/{orig[2]}"
            return destino
    return None
