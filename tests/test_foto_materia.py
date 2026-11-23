"""Foto da própria notícia: a IA lê o texto inteiro; só foto limpa (sem marca de outro veículo)."""
import io
from pathlib import Path

from PIL import Image

import editor
import illustrate


def _jpg(w=1200, h=800):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (90, 120, 160)).save(buf, "JPEG")
    return buf.getvalue()


def _fotos(monkeypatch, n=2, w=1200, h=800):
    fotos = [(_jpg(w, h) + bytes([i]), "image/jpeg", f"site{i}.com.br", f"https://site{i}.com.br/f.jpg")
             for i in range(n)]
    monkeypatch.setattr(illustrate, "_fotos_das_materias", lambda card: fotos)
    monkeypatch.setattr(illustrate, "_usadas", lambda: set())
    monkeypatch.setattr(illustrate, "_marcar", lambda pid: None)


def test_usa_a_foto_aprovada_com_credito_do_site(monkeypatch, tmp_path):
    _fotos(monkeypatch)
    pedido = {}

    def ia(card, imgs, cena="", sistema=None, defeitos=None):
        pedido.update(sistema=sistema, defeitos=defeitos, n=len(imgs))
        return 1
    monkeypatch.setattr(editor, "escolher_foto", ia)
    arq, credito = illustrate.foto_da_noticia({"titulo": "Obra na Prata", "legenda": "texto"}, tmp_path / "x")
    assert Path(arq).exists() and credito == "site1.com.br"
    assert pedido["sistema"] == editor.CONFERIR_FOTO_MATERIA and pedido["n"] == 2
    assert {"marca", "arte", "engana", "rosto", "chocante"} <= set(pedido["defeitos"])


def test_recusa_quando_a_ia_nao_aprova_ou_foto_pequena(monkeypatch, tmp_path):
    _fotos(monkeypatch)
    monkeypatch.setattr(editor, "escolher_foto", lambda *a, **k: None)
    assert illustrate.foto_da_noticia({"titulo": "x"}, tmp_path / "x") is None
    _fotos(monkeypatch, w=400, h=300)
    monkeypatch.setattr(editor, "escolher_foto", lambda *a, **k: 0)
    assert illustrate.foto_da_noticia({"titulo": "x"}, tmp_path / "x") is None


def test_marca_dagua_recusa_a_foto():
    resp = {"fotos": [{"foto": 0, "nota": 9, "marca": True}, {"foto": 1, "nota": 8, "marca": False}]}
    assert editor._escolha(resp, 2, ("marca", "arte", "engana")) == 1
    resp = {"fotos": [{"foto": 0, "nota": 9, "arte": True}]}
    assert editor._escolha(resp, 1, ("marca", "arte", "engana")) is None
    # placa/letreiro na cena não conta como defeito na foto da matéria (o campo "texto" não é olhado)
    assert editor._escolha({"fotos": [{"foto": 0, "nota": 8, "texto": True}]}, 1, ("marca", "arte")) == 0


def test_foto_da_materia_vem_antes_do_google(monkeypatch, tmp_path):
    ordem = []
    monkeypatch.setattr(illustrate, "foto_da_noticia", lambda c, b: ordem.append("materia") or (tmp_path / "m.jpg", "g1.globo.com"))
    monkeypatch.setattr(illustrate, "foto_google", lambda c, b: ordem.append("google"))
    card = {"titulo": "x"}
    assert illustrate.imagem_de_fundo(card, tmp_path / "b") == tmp_path / "m.jpg"
    assert ordem == ["materia"] and card["_credito"] == "Foto: g1.globo.com" and not card["_ilustrativa"]
