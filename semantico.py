"""Trava anti-repetição por significado (embeddings).

As travas de db.ja_publicada comparam palavras. Esta compara o SENTIDO: dois portais que contam o
mesmo fato com palavras diferentes ("Prefeitura de CG antecipa salário" x "Servidores campinenses
recebem pagamento mais cedo") ficam com vetores muito próximos e a segunda notícia é barrada.

- Usa o Gemini (gemini-embedding-001, mesma chave GEMINI_API_KEY, plano grátis) e, sem ele, a OpenAI.
- Se a API falhar ou não houver chave, a trava simplesmente não age: nunca impede uma publicação
  por erro técnico (as travas por palavras continuam valendo).
- Cada notícia publicada guarda o vetor no banco (tabela `vetores`), para comparar com as próximas.
"""
import hashlib
import json
import math
import time

import requests

import config

_CACHE = {}  # texto -> (modelo, vetor), para não pagar duas vezes pela mesma notícia na rodada


def _texto(card: dict) -> str:
    partes = [card.get("titulo", ""), card.get("linha_fina", ""), str(card.get("resumo", "") or "")]
    return " ".join(p.strip() for p in partes if p and p.strip())[:2000]


def _gemini(texto: str):
    for modelo in [m.strip() for m in config.EMBED_MODEL.split(",") if m.strip()]:
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:embedContent",
                headers={"x-goog-api-key": config.GEMINI_API_KEY},
                json={"content": {"parts": [{"text": texto}]}, "taskType": "SEMANTIC_SIMILARITY",
                      "outputDimensionality": 768},
                timeout=(10, 30))
        except requests.RequestException:
            continue
        if r.status_code == 200:
            v = (r.json().get("embedding") or {}).get("values")
            if v:
                return f"gemini:{modelo}", v
    return None


def _openai(texto: str):
    try:
        r = requests.post("https://api.openai.com/v1/embeddings",
                          headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"},
                          json={"model": "text-embedding-3-small", "input": texto, "dimensions": 768},
                          timeout=(10, 30))
    except requests.RequestException:
        return None
    if r.status_code == 200:
        return "openai:text-embedding-3-small", r.json()["data"][0]["embedding"]
    return None


def vetor(card: dict):
    """(modelo, vetor) da notícia, ou None se não der para calcular agora."""
    if not config.SEMANTICO:
        return None
    texto = _texto(card)
    if len(texto) < 20:
        return None
    chave = hashlib.sha1(texto.encode()).hexdigest()
    if chave in _CACHE:
        return _CACHE[chave]
    res = None
    try:
        if config.GEMINI_API_KEY:
            res = _gemini(texto)
        if res is None and config.OPENAI_API_KEY:
            res = _openai(texto)
    except Exception as e:  # nunca derruba a rodada
        print(f"[semântico] sem vetor ({type(e).__name__})")
        res = None
    if res:
        _CACHE[chave] = res
    return res


def cosseno(a, b) -> float:
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if not na or not nb or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def _tabela(c):
    c.execute("""CREATE TABLE IF NOT EXISTS vetores (
        ig_id TEXT PRIMARY KEY, ts REAL, titulo TEXT, modelo TEXT, vetor TEXT)""")


def guardar(conn, card: dict, ig_id: str):
    """Grava o vetor da notícia publicada (chamado por db.registrar_publicada)."""
    res = vetor(card)
    if not res:
        return
    modelo, v = res
    _tabela(conn)
    conn.execute("INSERT OR REPLACE INTO vetores VALUES (?,?,?,?,?)",
                 (str(ig_id), time.time(), card.get("titulo", ""), modelo,
                  json.dumps([round(x, 5) for x in v])))


def repetida(conn, card: dict, desde: float) -> str:
    """Motivo se a notícia tem o mesmo sentido de uma já publicada desde `desde`; senão ''."""
    res = vetor(card)
    if not res:
        return ""
    modelo, v = res
    _tabela(conn)
    melhor, titulo = 0.0, ""
    for tit, vet in conn.execute("SELECT titulo, vetor FROM vetores WHERE ts > ? AND modelo = ?",
                                 (desde, modelo)):
        s = cosseno(v, json.loads(vet))
        if s > melhor:
            melhor, titulo = s, tit
    if melhor:
        print(f"[semântico] mais parecida já postada: {melhor:.3f} ({titulo[:60]})")
    if melhor >= config.SIMILARIDADE_MAX:
        return f"mesmo fato já postado (sentido {melhor:.2f}): {titulo[:60]}"
    return ""
