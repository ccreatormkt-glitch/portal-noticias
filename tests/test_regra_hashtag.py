"""Regra 5 (REGRAS.md): hashtags só em letras minúsculas."""
import publish


def test_hashtags_da_legenda_saem_em_minusculas():
    card = {"titulo": "Teste", "legenda": "Texto do post.", "hashtags": ["JoaoPessoa", "#Cultura", "PARAIBA", "joaopessoa"]}
    legenda = publish.build_caption(card)
    tags = [p for p in legenda.split() if p.startswith("#")]
    assert tags and all(t == t.lower() for t in tags)
    assert tags.count("#joaopessoa") == 1


def test_qualquer_hashtag_no_texto_vira_minuscula():
    saida = publish.hashtags_minusculas("Siga @PBMinuto #JoaoPessoa #ConscienciaNegra #São_João")
    assert saida == "Siga @PBMinuto #joaopessoa #consciencianegra #são_joão"   # só a hashtag muda
