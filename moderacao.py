"""Vigia de comentários (regra 16): com uma fonte só, um erro pode passar. Toda hora o robô lê os
comentários dos posts recentes e separa os que apontam ERRO (fake, mentira, informação errada,
lugar/data trocados). Não responde nem apaga nada: só avisa, para o Arthur conferir e, se for o caso,
publicar a correção (workflow corrigir-noticia) ou apagar o post (workflow apagar-post).

Os alertas ficam em state/alertas_comentarios.json (o mais novo primeiro) e saem no log da rodada.
"""
import calendar
import json
import re
import time

import config
import sources

# frases de quem aponta erro (comparadas sem acento e em minúsculas)
SINAIS_ERRO = [
    "fake", "mentira", "mentiroso", "boato", "falso", "falsa", "nao e verdade", "nao e assim",
    "informacao errada", "noticia errada", "ta errado", "esta errado", "errado", "errada", "corrige",
    "corrijam", "corrigir", "nao aconteceu", "nao foi assim", "nao era", "nao e ele", "nao e ela",
    "nome errado", "cidade errada", "foto errada", "foto nao e", "nao e dessa", "noticia velha",
    "desinforma", "chequem", "apurem", "apuracao", "advogado", "difamacao", "calunia",
    "apaga esse", "apague", "tira esse post",
]


def aponta_erro(texto: str) -> list:
    """Sinais de erro achados no comentário (lista vazia = comentário comum)."""
    t = " " + re.sub(r"\s+", " ", sources.fold(texto or "")) + " "
    return [s for s in SINAIS_ERRO if s in t]


def _arquivo():
    return config.STATE_DIR / "alertas_comentarios.json"


def _carregar() -> list:
    try:
        return json.loads(_arquivo().read_text(encoding="utf-8"))
    except Exception:
        return []


def vigiar(horas: int = 48) -> list:
    """Lê os comentários dos posts das últimas `horas` e grava os novos alertas. Devolve os novos."""
    import publish
    alertas = _carregar()
    vistos = {a["comentario_id"] for a in alertas}
    novos = []
    limite = time.time() - horas * 3600
    for post in publish.posts_com_comentarios():
        try:
            ts = calendar.timegm(time.strptime(post["timestamp"][:19], "%Y-%m-%dT%H:%M:%S"))
        except Exception:
            ts = time.time()
        if ts < limite:
            continue
        for c in publish.comentarios(post["id"]):
            sinais = aponta_erro(c.get("text", ""))
            if not sinais or c["id"] in vistos:
                continue
            novos.append({"comentario_id": c["id"], "post_id": post["id"], "link": post.get("permalink", ""),
                          "manchete": (post.get("caption") or "").split("\n")[0][:120],
                          "comentario": c.get("text", "")[:300], "usuario": c.get("username", ""),
                          "sinais": sinais[:5], "quando": c.get("timestamp", ""), "status": "novo"})
    if novos:
        alertas = (novos + alertas)[:300]
        _arquivo().parent.mkdir(parents=True, exist_ok=True)
        _arquivo().write_text(json.dumps(alertas, ensure_ascii=False, indent=1), encoding="utf-8")
        for a in novos:
            print(f"[alerta] comentário aponta erro em {a['post_id']} ({', '.join(a['sinais'])}): "
                  f"\"{a['comentario'][:120]}\" — {a['link']}")
        print("[alerta] para corrigir: Actions > corrigir-noticia (post_id + o que estava errado); "
              "para apagar: Actions > apagar-post")
    return novos
