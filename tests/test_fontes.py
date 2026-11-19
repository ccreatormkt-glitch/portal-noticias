from conftest import item

import sources


def test_fold_e_stems_ignoram_acentos_e_palavras_vazias():
    assert sources.fold("João Pessoa É ótimo") == "joao pessoa e otimo"
    s = sources.stems_of("Prefeitura de Campina Grande abre vagas para cursos")
    assert "prefei" in s and "campin" in s and "de" not in s and "para" not in s


def test_filtro_bloqueia_itens_que_nao_sao_noticia():
    for t in ["ClickFM - AO VIVO", "Assista: entrevista", "Coluna do Fulano", "Horóscopo do dia",
              "Informe publicitário: loja X", "Vídeo: acidente na BR"]:
        assert sources.BLOQUEAR.search(t), t
    for t in ["Prefeitura abre 500 vagas", "Chuva alaga ruas de JP", "PM prende suspeito em CG"]:
        assert not sources.BLOQUEAR.search(t), t


def test_agrupa_mesma_noticia_de_veiculos_diferentes():
    itens = [
        item("Campina Grande abre inscrições para cursos gratuitos de qualificação", "ParaibaOnline"),
        item("Prefeitura de Campina Grande abre inscrições para cursos gratuitos", "Jornal da Paraíba"),
        item("Chuva forte provoca alagamentos em bairros de João Pessoa", "g1 Paraíba"),
    ]
    cl = sources.cluster_items(itens)
    assert len(cl) == 2
    principal = cl[0]
    assert principal.n_sources == 2 and principal.is_local and principal.trusted


def test_nacional_perde_para_local_e_velha_e_descartada():
    itens = [
        item("Governo federal anuncia novo programa em Brasília para estados", "CNN"),
        item("Chuva forte provoca alagamentos em bairros de João Pessoa", "g1 Paraíba"),
        item("Feira antiga de artesanato acontece em Campina Grande", "ParaibaOnline", idade_min=60 * 30),
    ]
    cl = sources.cluster_items(itens)
    assert [c.rep.title for c in cl][0].startswith("Chuva")
    assert all("Feira antiga" not in c.rep.title for c in cl)
    nacional = [c for c in cl if "Brasília" in c.rep.title][0]
    assert not nacional.is_local


def test_fontes_conhecidas_e_sem_sites_que_proibem_robos():
    urls = " ".join(sources.FEEDS.values())
    assert "pbagora.com.br/rss" in urls
    assert "wscom" not in urls and "portalt5" not in urls


def test_temas_proibidos_nunca_entram():
    import sources
    for t in ["PF investiga homem por divulgar pornografia infantil em Patos",
              "Operação contra abuso sexual infantojuvenil na Paraíba",
              "Jovem é suspeito de estupro em Campina Grande",
              "Homem é preso em Patos, suspeito de aliciar adolescente"]:
        assert sources.TEMA_PROIBIDO.search(t)
    assert not sources.TEMA_PROIBIDO.search("Câmara de João Pessoa elege novo presidente")
