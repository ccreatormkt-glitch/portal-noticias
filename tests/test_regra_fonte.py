"""REGRA: a Inter é a única família de letra do PB Minuto (capa, vídeo, legenda, logo, avatar).
Este teste falha se o sistema voltar a usar outra fonte."""
import re
from pathlib import Path

import layout as L

RAIZ = Path(__file__).resolve().parent.parent
ARQUIVO_DE_FONTE = re.compile(r"[\w{}-]+\.(?:ttf|otf)\b")


def test_codigo_so_cita_fontes_inter():
    for py in RAIZ.glob("*.py"):
        for nome in ARQUIVO_DE_FONTE.findall(py.read_text(encoding="utf-8")):
            assert L.FONTES_PERMITIDAS.match(nome), f"{py.name} usa {nome}: a regra é só Inter"


def test_tokens_de_layout_e_logo_sao_inter():
    usados = [*L.FONTE.values(), *L.FONTE_DISPLAY.values(), *L.FONTE_LOGO.values(),
              *[p["fonte"] for p in L.PAPEIS.values() if "fonte" in p]]
    assert usados and all(L.FONTES_PERMITIDAS.match(f) for f in usados)
    assert L.FAMILIA_DISPLAY in L.FAMILIAS_PERMITIDAS


def test_pasta_de_fontes_so_tem_inter_e_icones():
    for f in (RAIZ / "fonts").glob("*.*tf"):
        assert L.FONTES_PERMITIDAS.match(f.name), f"fonts/{f.name} não é Inter"


def test_legenda_do_video_em_inter(tmp_path):
    import audiograma
    palavras = [(p, i * 0.4, i * 0.4 + 0.35, 0) for i, p in enumerate("Sine abre 825 vagas".split())]
    ass = audiograma.legenda_ass(palavras, ["825 vagas"], tmp_path / "l.ass", total=3).read_text(encoding="utf-8")
    fontes = {linha.split(",")[1] for linha in ass.splitlines() if linha.startswith("Style:")}
    assert fontes and fontes <= set(L.FAMILIAS_PERMITIDAS), fontes
    assert not re.search(r"\\fn(?!Inter)", ass)   # nenhuma troca de fonte no meio da legenda
