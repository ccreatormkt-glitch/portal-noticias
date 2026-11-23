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


def test_mix_de_publicacoes_alterna_pela_categoria_mais_atrasada(ambiente, monkeypatch):
    """Mix CG 30%, JP 20%, Brasil 30%, Mundo 20%: depois de um post da Paraíba (cota de Campina),
    a categoria mais atrasada é o Brasil, e a notícia nacional sai em seguida."""
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
    monkeypatch.setattr(config, "MIX", {"cg": .3, "jp": .2, "brasil": .3, "mundo": .2})
    rodar()
    rodar()
    assert len(ambiente) == 2 and ambiente[1] == "POLÍTICA" and ambiente[0] != "POLÍTICA"
    assert [c for _, c in sorted(db.categorias_recentes(5))][-1] == "brasil"


def test_categoria_pela_cidade_e_regiao():
    assert sources.categoria_texto("Prefeitura de Campina Grande abre vagas") == ("cg", 2)
    assert sources.categoria_texto("Alagamento no bairro de Mangabeira") == ("jp", 2)
    assert sources.categoria_texto("Feira de artesanato em Patos") == ("cg", 1)
    assert sources.categoria_texto("Maré alta em Cabedelo") == ("jp", 1)
    assert sources.categoria_texto("Governo da Paraíba anuncia concurso") == ("pb", 0)
    mundo = item("Terremoto atinge o Japão", "g1", feed="g1_brasil", link="https://g1.globo.com/mundo/noticia/2026/11/22/x.ghtml")
    assert sources.eh_mundo(mundo)


def test_brasil_so_editorias_nacionais_do_g1():
    """Matéria regional de outro estado (ex.: Amazonas) não conta como notícia relevante do Brasil."""
    nac = item("Governo anuncia novo salário mínimo", "g1", feed="g1_brasil",
               link="https://g1.globo.com/economia/noticia/2026/11/19/salario.ghtml")
    reg = item("Palhaço leva arte a escolas", "g1", feed="g1_brasil",
               link="https://g1.globo.com/am/amazonas/noticia/2026/11/19/palhaco.ghtml")
    pb = item("Chuva em João Pessoa", "g1", feed="g1_pb", link="https://g1.globo.com/pb/paraiba/noticia/x.ghtml")
    assert sources.g1_nacional(nac) and not sources.g1_nacional(reg) and not sources.g1_nacional(pb)


def test_ritmo_um_post_a_cada_15_min_contando_parceiros(ambiente, monkeypatch):
    """Ritmo único do perfil: 1 post por rodada e só se o último post (notícia ou parceiro) tiver
    mais de ~14 min; sem rajadas que enchem o limite de 24h do Instagram."""
    import json
    monkeypatch.setattr(config, "CANDIDATOS", 1)
    monkeypatch.setattr(config, "BRASIL_A_CADA", 0)
    sem_count = argparse.Namespace(dry_run=False, count=None)  # como roda no GitHub
    main.cmd_run(sem_count)
    assert len(ambiente) == 1            # nenhum post recente -> sai 1 (não 2)
    main.cmd_run(sem_count)
    assert len(ambiente) == 1            # acabou de postar -> espera
    con = db._conn()
    con.execute("UPDATE posts SET ts = ts - 3600")
    con.commit()
    (config.STATE_DIR / "parceiro.json").write_text(json.dumps(
        {"vistos": {"p1": {"ts": time.time() - 120, "status": "publicado"}}}))
    main.cmd_run(sem_count)
    assert len(ambiente) == 1            # vídeo de parceiro há 2 min também conta
    (config.STATE_DIR / "parceiro.json").write_text(json.dumps({"vistos": {}}))
    main.cmd_run(sem_count)
    assert len(ambiente) == 2


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


def test_banco_de_noticias_ja_postadas_barra_repeticao(ambiente, monkeypatch):
    """Publicou -> entra no banco (SQLite + planilha CSV). A mesma notícia, de outro portal e com
    outras palavras, não sai de novo; e uma notícia que já está no Instagram também é barrada."""
    monkeypatch.setattr(config, "CANDIDATOS", 1)
    rodar()
    assert len(ambiente) == 1
    csv = db.banco_csv().read_text(encoding="utf-8")
    assert "Agência abre centenas de postos para vendedores" in csv and "IG1" in csv
    outra = {"titulo": "Sine de CG oferece 900 postos para vendedores",
             "titulo_fonte": "Sine de Campina Grande divulga 900 vagas de emprego para vendedores", "links": []}
    assert db.ja_publicada(outra)
    nova = {"titulo": "Temporal deixa ruas da Torre alagadas em João Pessoa", "titulo_fonte": "Chuva na Torre", "links": []}
    assert not db.ja_publicada(nova)
    assert db.ja_publicada(nova, ["🌧️ Temporal deixa ruas da Torre alagadas em João Pessoa\n\nTexto..."])


def test_pauta_pedida_busca_e_refaz_noticia_descartada(ambiente, monkeypatch):
    """Pauta "Natal Iluminado": só notícias do assunto; uma tentativa antiga descartada pode ser refeita."""
    tema = "Natal Iluminado 2026 de Campina Grande começa nesta quinta-feira com programação"
    monkeypatch.setattr(sources, "fetch_items", lambda verbose=False, extra=None: [
        item(tema, "ParaibaOnline"), item(tema, "Jornal da Paraíba"),
        item("Chuva forte alaga ruas do bairro da Torre em João Pessoa nesta tarde", "ParaibaOnline")])
    monkeypatch.setattr(sources, "build_clusters", lambda pauta="": [
        c for c in sources.cluster_items(sources.fetch_items()) if not pauta or "natal" in c.rep.title.lower()])
    c0 = sources.cluster_items([item(tema, "ParaibaOnline"), item(tema, "Jornal da Paraíba")])[0]
    db.record(c0.fingerprint, c0.stems, tema, "", "pulado", note="texto ainda parecido com a fonte")
    gerar = editor.generate

    def fake(prompt, system=None):
        if "Natal Iluminado" in prompt:
            return json.dumps(card(chapeu="CULTURA", titulo="Luzes de Natal acendem no Açude Velho em CG",
                                   resumo="Fatos.", legenda="a\n\nb\n\nc", pontos=[], linha_fina="x"), ensure_ascii=False)
        return gerar(prompt, system)
    monkeypatch.setattr(editor, "generate", fake)
    main.cmd_run(argparse.Namespace(dry_run=False, count=None, pauta="Natal Iluminado"))
    assert ambiente == ["CULTURA"]


def test_ia_barra_mesmo_fato_escrito_de_outro_jeito(ambiente, monkeypatch):
    """Ex. real de 19/11: 4 posts de "horários no feriado" com manchetes diferentes. A IA barra o repetido."""
    db.record("velho", set(), "Shoppings e bancos alteram funcionamento no feriado em João Pessoa", "", "published", ig_id="9")
    gerar = editor.generate
    perguntas = []

    def fake(prompt, system=None):
        if system == editor.MESMA_NOTICIA:
            perguntas.append(prompt)
            repetida = "Agência abre centenas" in prompt  # só a de emprego "repete"
            return json.dumps({"repetida": repetida, "igual_a": "Shoppings e bancos..." if repetida else ""})
        return gerar(prompt, system)
    monkeypatch.setattr(editor, "generate", fake)
    monkeypatch.setattr(config, "CANDIDATOS", 1)
    rodar()
    assert perguntas and "Shoppings e bancos alteram funcionamento" in perguntas[0]
    assert ambiente and ambiente[0] != "EMPREGO"  # a repetida ficou de fora; saiu outra


def test_pauta_exige_o_assunto_na_manchete(monkeypatch):
    monkeypatch.setattr(sources, "fetch_items", lambda verbose=False, extra=None: [
        item("Dia da Consciência Negra: veja o que abre e fecha no feriadão", "ParaibaOnline",
             resumo="Comércio funciona; Natal Iluminado segue com programação"),
        item("Natal Iluminado de Campina Grande abre com show e milhares de pessoas", "ParaibaOnline")])
    grupos = sources.build_clusters("Natal Iluminado")
    assert [c.rep.title[:13] for c in grupos] == ["Natal Ilumina"]


def test_nome_de_evento_nao_conta_como_copia():
    """ "Natal Iluminado 2026 de Campina Grande" não tem como ser reescrito: não barra a notícia."""
    c = sources.cluster_items([item("Natal Iluminado 2026 de Campina Grande começa nesta quinta-feira", "ParaibaOnline"),
                               item("Natal Iluminado 2026 de Campina Grande começa nesta quinta-feira", "Jornal da Paraíba")])[0]
    ok = {"titulo": "Luzes do Natal Iluminado 2026 de Campina Grande acendem hoje", "linha_fina": "", "resumo": "",
          "pontos": [], "legenda": ""}
    copiado = {"titulo": "Evento em Campina Grande começa nesta quinta-feira com luzes", "linha_fina": "", "resumo": "",
               "pontos": [], "legenda": ""}
    assert editor.trechos_repetidos(ok, c) == []
    assert editor.trechos_repetidos(copiado, c)  # "começa nesta quinta-feira" continua tendo que ser reescrito


def test_nome_de_evento_recorrente_nao_junta_noticias_diferentes():
    a = "Procon-CG mobiliza equipe e abre plantão no Natal Iluminado 2026"
    b = "Natal Iluminado 2026 de Campina Grande começa nesta quinta-feira com show"
    sources.NOMES_RECORRENTES.clear()
    assert sources.mesma_historia(a, b)  # sem contexto: o nome do evento junta as duas
    grupos = sources.cluster_items([item(t, "ParaibaOnline") for t in (
        a, b, "STTP define plano de mobilidade para o Natal Iluminado 2026", "Natal Iluminado terá 49 dias de festa")])
    sources.marcar_recorrentes(grupos)
    assert not sources.mesma_historia(a, b)  # "Natal Iluminado" está em vários assuntos: não serve
    assert sources.mesma_historia("Corujinha é eleito presidente da Câmara de João Pessoa",
                                  "Unanimidade elege João Corujinha à frente do Legislativo pessoense")
    sources.NOMES_RECORRENTES.clear()


def test_refazer_post_com_foto_escolhida(ambiente, monkeypatch, tmp_path):
    """Pedido do Arthur: postar de novo (já tinha saído) usando a foto dele."""
    from PIL import Image
    foto = tmp_path / "papai_noel.jpg"
    Image.new("RGB", (1080, 1920), (200, 30, 30)).save(foto)
    tema = "Procon-CG inicia plantão especial de atendimento durante o Natal Iluminado"
    monkeypatch.setattr(sources, "build_clusters", lambda pauta="": sources.cluster_items(
        [item(tema, "ParaibaOnline"), item(tema, "Jornal da Paraíba")]))
    c0 = sources.cluster_items([item(tema, "ParaibaOnline"), item(tema, "Jornal da Paraíba")])[0]
    db.record(c0.fingerprint, c0.stems, "Procon-CG mobiliza equipe e abre plantão no Natal Iluminado 2026", "",
              "published", ig_id="IGvelho")
    gerar = editor.generate
    usados = []
    monkeypatch.setattr(main, "_gerar_video", lambda c, bg, s: (usados.append(str(bg)) or ("v.mp4", "c.jpg")))

    def fake(prompt, system=None):
        if "Procon" in prompt:
            return json.dumps(card(chapeu="SERVIÇO", titulo="Procon de CG faz plantão no Natal Iluminado",
                                   resumo="Fatos.", legenda="a\n\nb\n\nc", pontos=[], linha_fina="x"), ensure_ascii=False)
        return gerar(prompt, system)
    monkeypatch.setattr(editor, "generate", fake)
    main.cmd_run(argparse.Namespace(dry_run=False, count=None, pauta="Procon Natal Iluminado",
                                    foto=str(foto), refazer=True))
    assert ambiente == ["SERVIÇO"] and usados == [str(foto)]


def test_madrugada_nao_posta_mas_pauta_pedida_sim(monkeypatch, capsys):
    import argparse
    import config
    import main
    monkeypatch.setattr(config, "POST_MODE", "auto")
    monkeypatch.setattr(config, "HORA_INICIO", 25)  # qualquer hora conta como madrugada
    monkeypatch.setattr(config, "IG_USER_ID", "1")
    monkeypatch.setattr(config, "IG_ACCESS_TOKEN", "x")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "x")
    main.cmd_run(argparse.Namespace(dry_run=False, count=None))
    assert "madrugada" in capsys.readouterr().out


def test_sem_video_de_parceiro_sai_noticia(ambiente, monkeypatch):
    """Regra 6: sem vídeo de parceiro (nenhum publicado ou na fila), a rodada publica notícia."""
    monkeypatch.setattr(config, "CANDIDATOS", 1)
    monkeypatch.setattr(config, "BRASIL_A_CADA", 0)
    (config.STATE_DIR / "parceiro.json").write_text(json.dumps({"vistos": {}, "tentativas": {}, "refazer": {}}))
    main.cmd_run(argparse.Namespace(dry_run=False, count=None))
    assert len(ambiente) == 1


def test_noticia_cede_a_vaga_quando_ha_video_esperando(ambiente, monkeypatch):
    """Notícia e vídeo de parceiro alternam: com vídeo esperando vaga e o último post sendo notícia,
    a rodada de notícias não publica e deixa o aviso para o vigia chamar o parceiro."""
    monkeypatch.setattr(config, "CANDIDATOS", 1)
    monkeypatch.setattr(config, "BRASIL_A_CADA", 0)
    db.record("velha", set(), "notícia antiga", "", "published")
    con = db._conn()
    con.execute("UPDATE posts SET ts = ts - 3600")
    con.commit()
    estado = config.STATE_DIR / "parceiro.json"
    estado.write_text(json.dumps({"vistos": {"v": {"ts": time.time() - 7200, "status": "publicado"}},
                                  "aguardando": time.time() - 60}))
    sem_count = argparse.Namespace(dry_run=False, count=None)
    main.cmd_run(sem_count)
    assert len(ambiente) == 0 and (config.OUT_DIR / "vez_do_parceiro").exists()
    # o vídeo saiu (último post agora é do parceiro): a próxima vaga volta para a notícia
    estado.write_text(json.dumps({"vistos": {"v": {"ts": time.time() - 1000, "status": "publicado"}},
                                  "aguardando": time.time() - 60}))
    (config.OUT_DIR / "vez_do_parceiro").unlink()
    main.cmd_run(sem_count)
    assert len(ambiente) == 1


def test_mix_nao_faz_rajada_da_mesma_categoria(ambiente, monkeypatch):
    """Mundo muito atrasado não sai 4 vezes seguidas: depois de 2 seguidas, intercala outra categoria."""
    import parceiro
    agora = time.time()
    base = ["cg"] * 6 + ["jp"] * 4 + ["brasil"] * 6
    ev = [(agora - 3000 + i, c) for i, c in enumerate(base)] + [(agora - 100, "mundo"), (agora - 50, "mundo")]
    monkeypatch.setattr(db, "categorias_recentes", lambda n=20: ev)
    monkeypatch.setattr(parceiro, "categorias_recentes", lambda n=20, caminho=None: [])
    monkeypatch.setattr(config, "MIX", {"cg": .3, "jp": .2, "brasil": .3, "mundo": .2})
    ordem = main._ordem_do_mix()
    assert ordem[0] != "mundo" and ordem[1] == "mundo"


def test_aprovar_da_fila_segue_mix_e_stories(monkeypatch):
    """Notícia aprovada da fila (modo review) segue o mesmo caminho da automática: mix e Stories."""
    import argparse
    import db
    import main
    import publish
    (config.QUEUE_PENDING / "a.jpg").write_bytes(b"x")
    (config.QUEUE_PENDING / "n1.json").write_text(json.dumps({
        "fp": "fp1", "titulo": "Feira em CG", "images": ["a.jpg"], "categoria": "cg", "stems": []}),
        encoding="utf-8")
    db.record("fp1", set(), "Feira em CG", "", "pending")
    monkeypatch.setattr(main, "_publish", lambda card, imgs: "IG1")
    stories = []
    monkeypatch.setattr(publish, "story_se_paraiba", lambda cat, v: stories.append(cat) or "ST1")
    main.cmd_approve(argparse.Namespace(all=True, id=""))
    assert stories == ["cg"]
    assert [c for _, c in db.categorias_recentes(5)] == ["cg"]


def test_regra_12_uma_fonte_basta_menos_policia():
    """Regra 12 (23/11/2026): 1 veículo da lista basta; crime/acusação de fonte pequena pede 2."""
    um = sources.Cluster([item("Feira de artesanato abre neste sábado em Campina Grande", fonte="Se Liga PB")])
    assert main._confirmada(um)
    crime = sources.Cluster([item("Suspeito é preso em flagrante em Campina Grande", fonte="Se Liga PB")])
    assert crime.policial and not main._confirmada(crime)
    dois = sources.Cluster([item("Suspeito é preso em flagrante em Campina Grande", fonte="Se Liga PB"),
                            item("Suspeito é preso em flagrante em CG", fonte="Paraíba Já")])
    assert main._confirmada(dois)
    grande = sources.Cluster([item("Suspeito é preso em flagrante em Campina Grande", fonte="g1 Paraíba")])
    assert main._confirmada(grande)
