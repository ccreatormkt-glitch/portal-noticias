"""Revisão com a skill STE80 Humanizer: tira cara de IA sem mexer nos fatos."""
import json

import editor

CARD = {"titulo": "Prefeitura de Campina Grande abre 120 vagas de emprego nesta segunda",
        "linha_fina": "Não é só emprego — é oportunidade para quem busca o primeiro trabalho.",
        "resumo": "O Sine abre 120 vagas às 8h, reforçando o compromisso com a geração de renda.",
        "pontos": ["Atendimento das 8h às 17h"], "legenda": "💼 Vagas no Sine!\n\nLeve RG e CPF.",
        "destaques": ["120 vagas"], "chapeu": "EMPREGO", "cidade": "Campina Grande", "hashtags": []}


def resposta(**kw):
    novo = {k: CARD[k] for k in editor.CAMPOS_TEXTO}
    novo.update(kw)
    return json.dumps(novo, ensure_ascii=False)


def test_aceita_a_revisao_que_mantem_os_fatos(monkeypatch):
    pedidos = []
    monkeypatch.setattr(editor, "generate", lambda p, s=None: pedidos.append(s) or resposta(
        linha_fina="As vagas são para quem busca o primeiro emprego.",
        resumo="O Sine abre 120 vagas às 8h desta segunda."))
    out = editor.humanizar(dict(CARD))
    assert out["humanizado"] and "—" not in out["linha_fina"] and "reforçando" not in out["resumo"]
    assert "Pass 1: AI tells" in pedidos[0] and "Fidelity rules" in pedidos[0]   # regras vêm da skill


def test_descarta_se_perder_ou_inventar_numero(monkeypatch):
    monkeypatch.setattr(editor, "generate", lambda p, s=None: resposta(pontos=["Atendimento durante o dia"]))
    assert editor.humanizar(dict(CARD)) == CARD                       # sumiu o "17h"
    monkeypatch.setattr(editor, "generate", lambda p, s=None: resposta(resumo="O Sine abre 120 vagas às 8h; 300 pessoas na fila."))
    assert editor.humanizar(dict(CARD)) == CARD                       # inventou "300"


def test_ia_fora_do_ar_mantem_o_texto(monkeypatch):
    def falha(p, s=None):
        raise RuntimeError("429")
    monkeypatch.setattr(editor, "generate", falha)
    assert editor.humanizar(dict(CARD)) == CARD
