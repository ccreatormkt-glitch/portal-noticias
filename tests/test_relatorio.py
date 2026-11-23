"""Relatório semanal: números só do banco (métricas da API), mediana, mix sugerido e lacunas."""
import json
import time

import config
import db
import relatorio


def _post(ig, reach, cat, chapeu, horas_atras=30, titulo="Notícia"):
    fp = "fp" + ig
    db.record(fp, set(), titulo, "", "published", ig_id=ig)
    db.marcar_regiao(fp, cat)
    db.save_meta(fp, {"chapeu": chapeu})
    db.save_metrics(ig, {"reach": reach, "shares": 1, "saved": 1, "likes": 2, "views": reach * 2})


def test_relatorio_mediana_e_recomendacoes():
    for i in range(6):
        _post(f"1{i}", 300, "cg", "CIDADE")
        _post(f"2{i}", 100, "brasil", "ECONOMIA")
    _post("99", 50000, "brasil", "ECONOMIA", titulo="Viral")
    texto = relatorio.gerar(7)
    assert "13 posts medidos" in texto
    assert "| Campina Grande | 6 | 300 |" in texto          # mediana não é puxada pelo viral
    assert "## 3 recomendações" in texto and texto.count("\n1. **") == 1
    assert "Mix:** mudar" in texto and "cg:40" in texto     # CG rende 3x: sobe 10 pontos (teto semanal)


def test_relatorio_sem_dados_avisa_em_vez_de_inventar():
    assert "Sem métricas no período" in relatorio.gerar(7)


def test_mix_sugerido_ignora_diferenca_pequena_e_amostra_pequena():
    mix = {"cg": 30, "jp": 20, "brasil": 30, "mundo": 20}
    g = [{"chave": "cg", "n": 10, "alcance": 110}, {"chave": "brasil", "n": 10, "alcance": 100},
         {"chave": "jp", "n": 2, "alcance": 900}]
    assert relatorio.mix_sugerido(g, mix) == mix
    novo = relatorio.mix_sugerido([{"chave": "cg", "n": 9, "alcance": 400}, {"chave": "brasil", "n": 9, "alcance": 100}], mix)
    assert sum(novo.values()) == 100 and novo["cg"] > 30 and novo["brasil"] < 30


def test_parceiro_entra_no_relatorio_e_na_coleta():
    agora = time.time()
    est = {"vistos": {"orig1": {"ts": agora - 30 * 3600, "status": "publicado", "nota": "555",
                                "categoria": "jp", "editoria": "POLÍCIA"}}}
    (config.STATE_DIR / "parceiro.json").write_text(json.dumps(est), encoding="utf-8")
    assert relatorio.parceiros_sem_metricas() == ["555"]
    db.save_metrics("555", {"reach": 700})
    assert relatorio.parceiros_sem_metricas() == []
    linhas = relatorio._linhas(7)
    assert linhas[0]["origem"] == "parceiro" and linhas[0]["categoria"] == "jp"
