"""Regra 16: vigia de comentários que apontam erro e chave de pausa."""
import json
import time

import config
import moderacao
import publish


def test_aponta_erro_so_quando_o_comentario_contesta_a_noticia():
    assert moderacao.aponta_erro("Isso é FAKE, não aconteceu assim")
    assert moderacao.aponta_erro("informação errada, foi em Queimadas")
    assert moderacao.aponta_erro("Corrijam o nome por favor")
    assert not moderacao.aponta_erro("Que tristeza, força à família")
    assert not moderacao.aponta_erro("Parabéns pela notícia, processo seletivo top")


def test_vigiar_grava_alerta_novo_uma_vez(monkeypatch):
    agora = time.strftime("%Y-%m-%dT%H:%M:%S+0000", time.gmtime())
    monkeypatch.setattr(publish, "posts_com_comentarios", lambda: [
        {"id": "P1", "caption": "🚨 Acidente na BR-230\n\ntexto", "timestamp": agora, "permalink": "https://ig/p1"}])
    monkeypatch.setattr(publish, "comentarios", lambda mid: [
        {"id": "C1", "text": "notícia errada, não foi aqui", "username": "ana"},
        {"id": "C2", "text": "que horror", "username": "bia"}])
    novos = moderacao.vigiar()
    assert [a["comentario_id"] for a in novos] == ["C1"] and novos[0]["manchete"] == "🚨 Acidente na BR-230"
    assert moderacao.vigiar() == []          # não repete o mesmo alerta
    salvos = json.loads((config.STATE_DIR / "alertas_comentarios.json").read_text(encoding="utf-8"))
    assert len(salvos) == 1 and salvos[0]["status"] == "novo"


def test_pausar_nao_publica(monkeypatch, capsys):
    import argparse
    import main
    monkeypatch.setattr(config, "PAUSAR", True)
    main.cmd_run(argparse.Namespace())
    main.cmd_parceiro(argparse.Namespace(modo=None))
    saida = capsys.readouterr().out
    assert saida.count("PAUSADO") == 2
