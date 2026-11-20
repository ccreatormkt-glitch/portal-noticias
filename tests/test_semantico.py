"""Trava por sentido: barra o mesmo fato com outras palavras e nunca trava a publicação por erro."""
import config
import db
import semantico


def _card(titulo, fina="", resumo=""):
    return {"titulo": titulo, "linha_fina": fina, "resumo": resumo, "links": [], "fp": titulo}


def _vetores_falsos(monkeypatch, tabela):
    """Substitui a API: cada manchete vira o vetor da tabela (sem rede)."""
    monkeypatch.setattr(config, "SEMANTICO", True)
    monkeypatch.setattr(semantico, "_CACHE", {})

    def falso(card):
        return ("teste:modelo", tabela[card["titulo"]])
    monkeypatch.setattr(semantico, "vetor", falso)


def test_mesmo_fato_com_outras_palavras_e_barrado(monkeypatch):
    _vetores_falsos(monkeypatch, {
        "Prefeitura de Campina Grande antecipa salário dos servidores": [1.0, 0.0, 0.1],
        "Servidores campinenses recebem pagamento mais cedo em dezembro": [0.98, 0.02, 0.12],
    })
    db.registrar_publicada(_card("Prefeitura de Campina Grande antecipa salário dos servidores"), "111")
    motivo = db.ja_publicada(_card("Servidores campinenses recebem pagamento mais cedo em dezembro"))
    assert "sentido" in motivo


def test_fato_diferente_passa(monkeypatch):
    _vetores_falsos(monkeypatch, {
        "Prefeitura de Campina Grande antecipa salário dos servidores": [1.0, 0.0, 0.0],
        "Chuva forte alaga ruas do centro de João Pessoa nesta tarde": [0.0, 1.0, 0.0],
    })
    db.registrar_publicada(_card("Prefeitura de Campina Grande antecipa salário dos servidores"), "111")
    assert db.ja_publicada(_card("Chuva forte alaga ruas do centro de João Pessoa nesta tarde")) == ""


def test_limite_configuravel(monkeypatch):
    _vetores_falsos(monkeypatch, {"Notícia A sobre obras na BR-230": [1.0, 0.0],
                                  "Notícia B sobre obras na BR-230": [0.8, 0.6]})
    db.registrar_publicada(_card("Notícia A sobre obras na BR-230"), "1")
    monkeypatch.setattr(config, "SIMILARIDADE_MAX", 0.95)
    with db._conn() as c:
        assert semantico.repetida(c, _card("Notícia B sobre obras na BR-230"), 0) == ""
    monkeypatch.setattr(config, "SIMILARIDADE_MAX", 0.75)
    with db._conn() as c:
        assert "sentido" in semantico.repetida(c, _card("Notícia B sobre obras na BR-230"), 0)


def test_sem_chave_ou_api_fora_do_ar_nao_trava(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    monkeypatch.setattr(semantico, "_CACHE", {})
    db.registrar_publicada(_card("Prefeitura de Campina Grande antecipa salário dos servidores"), "111")
    assert db.ja_publicada(_card("Servidores campinenses recebem pagamento mais cedo")) == ""

    monkeypatch.setattr(config, "GEMINI_API_KEY", "x")  # a rede dos testes levanta erro: a trava só pula
    assert semantico.vetor(_card("Qualquer notícia com texto suficiente aqui")) is None


def test_desligado_por_variavel(monkeypatch):
    monkeypatch.setattr(config, "SEMANTICO", False)
    monkeypatch.setattr(config, "GEMINI_API_KEY", "x")
    assert semantico.vetor(_card("Qualquer notícia com texto suficiente aqui")) is None


def test_cosseno():
    assert abs(semantico.cosseno([1, 0], [1, 0]) - 1) < 1e-9
    assert semantico.cosseno([1, 0], [0, 1]) == 0
    assert semantico.cosseno([1, 0], [1, 0, 0]) == 0  # tamanhos diferentes = modelos diferentes
