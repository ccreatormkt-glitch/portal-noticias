import datetime as dt
import json

import pytest

import boletim

HOJE = dt.date(2026, 11, 19)


class Resp:
    def __init__(self, d):
        self.d = d

    def raise_for_status(self):
        pass

    def json(self):
        return self.d


def periodo(resumo, tmin, tmax):
    return {"resumo": resumo, "temp_min": tmin, "temp_max": tmax}


def test_previsao_com_periodos(monkeypatch):
    dados = {"2504009": {"19/11/2026": {"manha": periodo("Poucas nuvens", 19, 27),
                                        "tarde": periodo("Parcialmente nublado", 22, 31),
                                        "noite": periodo("Céu claro", 20, 25)}}}
    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **k: Resp(dados))
    p = boletim.previsao("2504009", HOJE)
    assert p == {"resumo": "Parcialmente nublado", "min": 19, "max": 31}


def test_previsao_dia_sem_periodos(monkeypatch):
    dados = {"2507507": {"19/11/2026": periodo("Chuva fraca", 24, 30)}}
    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **k: Resp(dados))
    assert boletim.previsao("2507507", HOJE) == {"resumo": "Chuva fraca", "min": 24, "max": 30}


@pytest.mark.parametrize("resumo,icone", [("Pancadas de chuva", "water_drop"), ("Trovoadas", "thunderstorm"),
                                          ("Nublado", "cloud"), ("Céu claro", "wb_sunny")])
def test_icone(resumo, icone):
    assert boletim.icone_tempo(resumo) == icone


def test_roteiro_e_legenda():
    tempos = {"Campina Grande": {"resumo": "Poucas nuvens", "min": 20, "max": 31}}
    falas = boletim.roteiro(HOJE, tempos, ["Título A"])
    assert falas[0][1].startswith("Bom dia, Paraíba! Hoje é quinta-feira, 19 de novembro")
    assert "mínima de 20 e máxima de 31 graus" in falas[1][1]
    txt = boletim.legenda(HOJE, tempos, ["Título A"])
    assert "INMET" in txt and "• Título A" in txt and "voz gerada por IA" in txt
