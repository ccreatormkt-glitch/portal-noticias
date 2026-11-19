"""Fluxo completo (sem rede): escolha por potencial, publicação, repetição, novas tentativas e aprendizado."""
import argparse
import json
import time

import pytest
from conftest import card, item

import config
import db
import editor
import main
import publish
import sources

TEMAS = {
    "EMPREGO": ("Sine de Campina Grande divulga 900 vagas de emprego para vendedores", "utilidade", 5),
    "CLIMA": ("Chuva forte alaga ruas do bairro da Torre em João Pessoa nesta tarde", "identificacao", 3),
    "ESPORTE": ("Atleta pessoense conquista ouro inédito em campeonato nacional de judô", "emocao", 4),
}


@pytest.fixture
def ambiente(monkeypatch):
    def clusters():
        its = []
        for k, (t, _, _) in enumerate(TEMAS.values()):
            its += [item(t, "ParaibaOnline", rank=k), item(t, "Jornal da Paraíba", rank=k)]
        return sources.cluster_items(its)
    monkeypatch.setattr(sources, "build_clusters", clusters)

    def fake(prompt, system=None):
        for ch, (t, g, p) in TEMAS.items():
            if t[:25] in prompt:
                return json.dumps(card(chapeu=ch, titulo={"EMPREGO": "Agência abre centenas de postos para vendedores", "CLIMA": "Temporal deixa vias da Torre debaixo d'água", "ESPORTE": "Judoca pessoense fica com medalha dourada no Brasileiro"}[ch], gatilho=g,
                                       potencial=p, resumo="Fatos.", legenda="a\n\nb\n\nc",
                                       pontos=[], linha_fina="x"), ensure_ascii=False)
    monkeypatch.setattr(editor, "generate", fake)
    monkeypatch.setattr(editor, "texto_completo", lambda c: "")
    import illustrate
    monkeypatch.setattr(illustrate, "imagem_de_fundo", lambda c, b: None)
    monkeypatch.setattr(main, "_gerar_video", lambda c, bg, s: ("video.mp4", "capa.jpg"))
    monkeypatch.setattr(config, "POST_MODE", "auto")
    monkeypatch.setattr(config, "CANDIDATOS", 3)  # escolha entre 3 candidatas (o padrão rápido é 1)
    for k in ("GEMINI_API_KEY", "IG_USER_ID", "IG_ACCESS_TOKEN"):
        monkeypatch.setattr(config, k, "teste")
    monkeypatch.setattr(publish, "quota_left", lambda: 50)
    publicados = []

    def fake_publish(card, paths):
        publicados.append(card["chapeu"])
        return f"IG{len(publicados)}"
    monkeypatch.setattr(main, "_publish", fake_publish)
    return publicados


def rodar():
    main.cmd_run(argparse.Namespace(dry_run=False, count=1))


def test_escolhe_maior_potencial_e_nao_repete(ambiente):
    rodar()
    rodar()
    rodar()
    assert ambiente == ["EMPREGO", "ESPORTE", "CLIMA"]  # 5, 4, 3 — e cada uma uma vez só
    rodar()
    assert len(ambiente) == 3


def test_falha_tenta_de_novo_ate_3_vezes(ambiente, monkeypatch):
    def quebra(card, paths):
        raise RuntimeError("instagram fora")
    monkeypatch.setattr(main, "_publish", quebra)
    for _ in range(3):
        with pytest.raises(SystemExit):  # rodada fica vermelha no GitHub
            rodar()
    with sqlite_conn() as c:
        falhas = c.execute("SELECT COUNT(*) FROM posts WHERE status='falha_publicacao'").fetchone()[0]
    assert falhas >= 3
    fp = sources.build_clusters()[0].fingerprint
    assert db.seen(fp, set())  # depois de 3 falhas, desiste dessa notícia


def test_limite_diario(ambiente, monkeypatch):
    monkeypatch.setattr(config, "MAX_POSTS_PER_DAY", 1)
    rodar()
    rodar()
    assert len(ambiente) == 1


def test_aprendizado_favorece_o_que_engaja():
    con = db._conn()
    dados = [("ESPORTE", "emocao", 260)] * 3 + [("EMPREGO", "utilidade", 60)] * 3
    for i, (ch, g, sc) in enumerate(dados):
        con.execute("INSERT INTO posts (ts,fp,stems,headline,source,status,ig_id,note) VALUES (?,?,?,?,?,?,?,?)",
                    (time.time() - 90000, f"f{i}", "", "h", "s", "published", f"IG{i}", ""))
        con.execute("INSERT INTO meta VALUES (?,?,?,?,?)", (f"f{i}", ch, g, 4, "noticia"))
        con.execute("INSERT INTO metricas VALUES (?,?,?,?,?,?,?,?)", (f"IG{i}", time.time(), 1000, 0, 0, 0, 0, sc))
    con.commit()
    bom = main._bonus_desempenho({"chapeu": "ESPORTE", "gatilho": "emocao"})
    ruim = main._bonus_desempenho({"chapeu": "EMPREGO", "gatilho": "utilidade"})
    novo = main._bonus_desempenho({"chapeu": "POLÍTICA", "gatilho": "debate"})
    assert bom > 0 > ruim and novo == 0


def test_metricas_salvas_e_score():
    s = db.save_metrics("IGx", {"reach": 1000, "saved": 10, "shares": 5, "likes": 50, "comments": 3})
    assert s == pytest.approx(63.0)


def sqlite_conn():
    import sqlite3
    return sqlite3.connect(db.DB_PATH)


def test_sem_configuracao_sai_sem_erro(monkeypatch, capsys):
    monkeypatch.setattr(config, "POST_MODE", "auto")
    monkeypatch.setattr(config, "CANDIDATOS", 3)  # escolha entre 3 candidatas (o padrão rápido é 1)
    monkeypatch.setattr(config, "IG_ACCESS_TOKEN", "")
    rodar()
    assert "aguardando configuração" in capsys.readouterr().out


def test_manchete_parecida_de_outra_fonte_nao_volta():
    import db
    import sources
    db.record("fp1", sources.stems_of("Câmara de João Pessoa elege Corujinha presidente"),
              "Corujinha é eleito presidente da Câmara de João Pessoa", "", "published")
    assert db.manchete_repetida("Unanimidade elege João Corujinha à frente do Legislativo pessoense")
    assert not db.manchete_repetida("Natal Iluminado começa em Campina Grande")


def test_gpt_primeiro_e_gemini_de_reserva(monkeypatch):
    import editor
    monkeypatch.setattr(editor, "OPENAI_API_KEY", "x")
    monkeypatch.setattr(editor, "GEMINI_API_KEY", "y")
    monkeypatch.setattr(editor, "LLM_PROVIDER", "openai")

    def gpt_fora(p, s):
        raise RuntimeError("fora do ar")
    monkeypatch.setattr(editor, "_openai", gpt_fora)
    monkeypatch.setattr(editor, "_gemini", lambda p, s: '{"ok": true}')
    assert editor.generate("p") == '{"ok": true}'


def test_sem_novidade_da_paraiba_publica_noticia_do_brasil(ambiente, monkeypatch):
    nacional = "Governo federal anuncia novo calendário de pagamento do Bolsa Família em dezembro"

    def clusters():
        return sources.cluster_items([item(nacional, "g1", feed="g1_brasil", link="https://g1.globo.com/economia/noticia/2026/11/19/bolsa.ghtml")])
    monkeypatch.setattr(sources, "build_clusters", clusters)

    def fake(prompt, system=None):
        return json.dumps(card(chapeu="BRASIL", cidade="Brasil", titulo="Bolsa Família tem novas datas de pagamento em dezembro",
                               resumo="Fatos.", legenda="a\n\nb\n\nc", pontos=[], linha_fina="x"), ensure_ascii=False)
    monkeypatch.setattr(editor, "generate", fake)
    rodar()
    assert ambiente == ["BRASIL"]


def test_um_a_cada_tres_posts_e_do_brasil(ambiente, monkeypatch):
    """Fluxo misto: depois de 2 posts da Paraíba, o próximo é notícia relevante do Brasil (G1)."""
    nacional = "Governo federal anuncia novo calendário de pagamento do Bolsa Família em dezembro"
    locais = sources.build_clusters

    def clusters():
        return locais() + sources.cluster_items([item(nacional, "g1", feed="g1_brasil", link="https://g1.globo.com/economia/noticia/2026/11/19/bolsa.ghtml")])
    monkeypatch.setattr(sources, "build_clusters", clusters)
    gerar = editor.generate

    def fake(prompt, system=None):
        if nacional[:25] in prompt:
            return json.dumps(card(chapeu="POLÍTICA", cidade="Brasil", titulo="Bolsa Família tem novas datas de pagamento em dezembro",
                                   resumo="Fatos.", legenda="a\n\nb\n\nc", pontos=[], linha_fina="x"), ensure_ascii=False)
        return gerar(prompt, system)
    monkeypatch.setattr(editor, "generate", fake)
    monkeypatch.setattr(config, "CANDIDATOS", 1)
    monkeypatch.setattr(config, "BRASIL_A_CADA", 3)
    rodar()
    rodar()
    rodar()
    assert len(ambiente) == 3 and ambiente[2] == "POLÍTICA" and "POLÍTICA" not in ambiente[:2]
    assert db.vez_do_brasil(3) is False


def test_brasil_so_editorias_nacionais_do_g1():
    """Matéria regional de outro estado (ex.: Amazonas) não conta como notícia relevante do Brasil."""
    nac = item("Governo anuncia novo salário mínimo", "g1", feed="g1_brasil",
               link="https://g1.globo.com/economia/noticia/2026/11/19/salario.ghtml")
    reg = item("Palhaço leva arte a escolas", "g1", feed="g1_brasil",
               link="https://g1.globo.com/am/amazonas/noticia/2026/11/19/palhaco.ghtml")
    pb = item("Chuva em João Pessoa", "g1", feed="g1_pb", link="https://g1.globo.com/pb/paraiba/noticia/x.ghtml")
    assert sources.g1_nacional(nac) and not sources.g1_nacional(reg) and not sources.g1_nacional(pb)


def test_ritmo_recupera_com_dois_posts_quando_atrasado(ambiente, monkeypatch):
    """Última hora abaixo da meta (~5/h): a rodada publica até 2; no ritmo, publica 1."""
    monkeypatch.setattr(config, "CANDIDATOS", 1)
    monkeypatch.setattr(config, "POSTS_PER_RUN", 2)
    monkeypatch.setattr(config, "BRASIL_A_CADA", 0)
    sem_count = argparse.Namespace(dry_run=False, count=None)  # como roda no GitHub
    main.cmd_run(sem_count)
    assert len(ambiente) == 2  # nenhuma na última hora -> recupera com 2
    for i in range(3):
        db.record(f"x{i}", set(), f"manchete {i}", "", "published")
    main.cmd_run(sem_count)
    assert len(ambiente) == 3  # 5 na última hora (meta ~5) -> só 1


def test_mesclar_historico_de_duas_rodadas(tmp_path):
    import sqlite3
    db.record("fpA", {"a"}, "Notícia A", "", "published", ig_id="1")
    outro = tmp_path / "outro.db"
    original = db.DB_PATH
    db.DB_PATH = outro
    try:
        db.record("fpB", {"b"}, "Notícia B", "", "published", ig_id="2")
        db.marcar_regiao("fpB", "brasil")
    finally:
        db.DB_PATH = original
    main.cmd_mesclar(argparse.Namespace(banco=str(outro)))
    main.cmd_mesclar(argparse.Namespace(banco=str(outro)))  # rodar de novo não duplica
    c = sqlite3.connect(db.DB_PATH)
    assert sorted(r[0] for r in c.execute("SELECT headline FROM posts")) == ["Notícia A", "Notícia B"]
    assert c.execute("SELECT regiao FROM regiao WHERE fp='fpB'").fetchone()[0] == "brasil"


def test_cnn_brasil_e_agencia_brasil_contam_como_brasil():
    cnn = item("Senado aprova reforma do setor elétrico", "CNN Brasil", feed="gn_cnnbrasil")
    ebc = item("Prazo do Simples acaba nesta sexta", "Agência Brasil", feed="agenciabrasil",
               link="https://agenciabrasil.ebc.com.br/economia/noticia/2026-11/prazo")
    local = item("Chuva em Campina Grande", "ParaibaOnline")
    assert sources.nacional(cnn) and sources.nacional(ebc) and not sources.nacional(local)
    assert "gn_cnnbrasil" in sources.FEEDS and "cnnbrasil.com.br" in sources.FEEDS["gn_cnnbrasil"]
