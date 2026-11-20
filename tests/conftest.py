"""Isola cada teste: banco, fila e saídas em pasta temporária; nenhuma chamada de rede real."""
import json
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def isolar(tmp_path, monkeypatch):
    import config
    import db
    import main

    monkeypatch.setattr(config, "HORA_INICIO", 0)  # testes rodam a qualquer hora (a guarda tem teste próprio)
    state, pend, pub, out = (tmp_path / n for n in ("state", "pending", "published", "out"))
    for d in (state, pend, pub, out):
        d.mkdir()
    monkeypatch.setattr(config, "STATE_DIR", state)
    monkeypatch.setattr(config, "QUEUE_PENDING", pend)
    monkeypatch.setattr(config, "QUEUE_PUBLISHED", pub)
    monkeypatch.setattr(config, "OUT_DIR", out)
    monkeypatch.setattr(db, "DB_PATH", state / "posts.db")
    monkeypatch.setattr(db, "LOG_PATH", state / "log.jsonl")
    monkeypatch.setattr(main, "CACHE", state / "candidatos.json")

    def sem_rede(*a, **k):
        raise AssertionError("teste tentou acessar a rede")
    import requests
    monkeypatch.setattr(requests, "get", sem_rede)
    monkeypatch.setattr(requests, "post", sem_rede)
    monkeypatch.setattr(requests.Session, "request", sem_rede)

    def sem_git(*a, **k):  # nos testes nunca publica nada no repositório
        raise RuntimeError("hospedagem pelo GitHub só funciona dentro do GitHub Actions")
    import hospedar
    monkeypatch.setattr(hospedar, "links_publicos", sem_git)
    monkeypatch.setattr(hospedar, "publicar_arquivos", sem_git)
    import audiograma  # nos testes, nada de baixar o modelo do Whisper (usa a reserva por sílabas)
    monkeypatch.setattr(audiograma, "_whisper", lambda wav: [])
    yield tmp_path


def item(titulo, fonte="ParaibaOnline", idade_min=10, rank=0, resumo="", link="", feed="gn_campina"):
    import sources
    return sources.Item(titulo, fonte, link, time.time() - idade_min * 60, feed, rank, resumo)


CARD_BASE = {
    "skip": False, "risco": "ok", "formato": "servico", "chapeu": "EMPREGO",
    "titulo": "CG tem 500 vagas em capacitação sem custo para moradores",
    "linha_fina": "Cadastro vai até sexta pelo site da prefeitura.",
    "resumo": "Moradores podem se qualificar sem pagar nada. O cadastro já está liberado.",
    "pontos": ["Capacitação sem custo", "Cadastro até sexta"],
    "legenda": "🎓 Qualificação sem custo em CG\n\nContexto da notícia.\n\nSalve este post e mande para quem precisa saber.",
    "cidade": "Campina Grande", "hashtags": ["#campinagrande", "paraiba", "cursos gratuitos"],
    "foto_busca": "classroom", "imagem_prompt": "", "gatilho": "utilidade", "potencial": 4,
}


def card(**over):
    c = json.loads(json.dumps(CARD_BASE))
    c.update(over)
    return c
