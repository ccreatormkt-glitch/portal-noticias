import json

import pytest
from conftest import card, item

import editor
import sources


def cluster(*titulos):
    return sources.cluster_items([item(t, f"Fonte{i}") for i, t in enumerate(titulos)])[0]


def test_validate_normaliza_campos():
    c = editor.validate(card(chapeu="emprego", titulo="Título com ponto final.", gatilho="xyz",
                             potencial="9", formato="desconhecido"))
    assert c["chapeu"] == "EMPREGO"
    assert c["titulo"] == "Título com ponto final"
    assert c["gatilho"] == "utilidade" and c["potencial"] == 5 and c["formato"] == "noticia"
    assert c["hashtags"] == ["campinagrande", "paraiba", "cursosgratuitos"]


def test_validate_rejeita_titulo_gigante_e_campo_faltando():
    with pytest.raises(ValueError):
        editor.validate(card(titulo="x" * 140))
    with pytest.raises(ValueError):
        editor.validate(card(legenda=""))


def test_risco_skip_vira_skip():
    assert editor.validate(card(risco="skip"))["skip"] is True


def test_detecta_trechos_copiados_da_fonte():
    cl = cluster("Prefeitura de Campina Grande abre inscrições para cursos gratuitos de qualificação",
                 "Campina Grande abre inscrições para cursos gratuitos de qualificação profissional")
    copiado = card(titulo="Prefeitura de Campina Grande abre inscrições para cursos gratuitos")
    assert editor.trechos_repetidos(copiado, cl)
    original = card(titulo="CG libera 500 vagas em capacitação sem custo", resumo="Cadastro liberado hoje.",
                    legenda="🎓 Vagas sem custo\n\nTexto próprio.\n\nSalve.", pontos=["Sem custo"],
                    linha_fina="Prazo curto.")
    assert editor.trechos_repetidos(original, cl) == []


def test_agente_reescritor_corrige_ou_descarta(monkeypatch):
    cl = cluster("Prefeitura de Campina Grande abre inscrições para cursos gratuitos de qualificação",
                 "Campina Grande abre inscrições para cursos gratuitos de qualificação profissional")
    copiado = card(titulo="Prefeitura de Campina Grande abre inscrições para cursos gratuitos")
    reescrito = card(titulo="CG libera 500 vagas em capacitação sem custo", resumo="Cadastro liberado hoje.",
                     legenda="🎓 Vagas sem custo\n\nTexto próprio.\n\nSalve.", pontos=["Sem custo"],
                     linha_fina="Prazo curto.")
    chamadas = []

    def fake(prompt, system=None):
        reescritor = bool(system) and "VERSÃO DESTE POST" not in system   # o editor leva a versão do gancho
        chamadas.append("reescritor" if reescritor else "editor")
        return json.dumps(reescrito if reescritor else copiado, ensure_ascii=False)
    monkeypatch.setattr(editor, "generate", fake)
    monkeypatch.setattr(editor, "texto_completo", lambda c: "")
    out = editor.make_card(cl)
    assert chamadas == ["editor", "reescritor"] and out["original"] and not out.get("skip")

    monkeypatch.setattr(editor, "generate", lambda p, system=None: json.dumps(copiado, ensure_ascii=False))
    assert editor.make_card(cl)["skip"] is True  # não conseguiu ficar original -> não publica


def test_prompt_proibe_inventar_e_citar_veiculos():
    s = editor.SYSTEM
    assert "Nunca invente" in s and "Nunca cite nomes de veículos" in s
    assert "suicídio" in s and "criança ou adolescente" in s
