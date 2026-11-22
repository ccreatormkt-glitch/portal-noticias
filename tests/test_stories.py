"""Regra dos Stories (22/11/2026): só posts da Paraíba vão também para os Stories, e cada Story conta
como uma publicação no limite de 24h (o ritmo dobra depois de um post com Story)."""
import time

import config
import db
import parceiro
import publish


def test_so_post_da_paraiba_vai_para_os_stories(monkeypatch):
    feitos = []
    monkeypatch.setattr(config, "STORIES", "paraiba")
    monkeypatch.setattr(publish, "quota_left", lambda: 10)
    monkeypatch.setattr(publish, "post_story", lambda v: feitos.append(v) or "S1")
    assert publish.story_se_paraiba("brasil", "v.mp4") == ""
    assert publish.story_se_paraiba("mundo", "v.mp4") == ""
    assert publish.story_se_paraiba("cg", "v.mp4") == "S1"
    assert publish.story_se_paraiba("jp", "v.mp4") == "S1"
    assert publish.story_se_paraiba("pb", "v.mp4") == "S1"
    assert len(feitos) == 3


def test_story_nao_sai_sem_vaga_e_nao_derruba_o_post(monkeypatch):
    monkeypatch.setattr(config, "STORIES", "paraiba")
    monkeypatch.setattr(publish, "quota_left", lambda: 0)
    assert publish.story_se_paraiba("cg", "v.mp4") == ""

    def quebra(v):
        raise RuntimeError("erro da Meta")
    monkeypatch.setattr(publish, "quota_left", lambda: 5)
    monkeypatch.setattr(publish, "post_story", quebra)
    assert publish.story_se_paraiba("cg", "v.mp4") == ""


def test_post_com_story_dobra_a_espera(monkeypatch):
    agora = time.time()
    monkeypatch.setattr(parceiro, "ultimo_evento", lambda caminho=None: (0.0, 1))
    monkeypatch.setattr(db, "ultimo_evento", lambda: (agora - 60, 1))
    so_feed = parceiro.espera_ritmo()
    monkeypatch.setattr(db, "ultimo_evento", lambda: (agora - 60, 2))
    com_story = parceiro.espera_ritmo()
    assert abs(com_story - (so_feed + config.INTERVALO_POSTS)) < 5


def test_story_de_parceiro_conta_no_limite_de_24h(tmp_path):
    import json
    arq = tmp_path / "parceiro.json"
    arq.write_text(json.dumps({"vistos": {
        "a": {"ts": time.time() - 60, "status": "publicado", "story": "S9"},
        "b": {"ts": time.time() - 120, "status": "publicado"}}}))
    assert parceiro.publicados_24h(arq) == 3
    assert parceiro.ultimo_evento(arq)[1] == 2
