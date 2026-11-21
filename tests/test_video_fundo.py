"""Fundo do Reels com trecho de vídeo do Pixabay: busca, filtro, montagem e reserva para a foto."""
import subprocess
from pathlib import Path

import requests
from PIL import Image

import audiograma
import config
import illustrate


class _Resp:
    def __init__(self, dados=None, conteudo=b"", status=200):
        self._d, self.content, self.status_code = dados, conteudo, status
        self.headers = {"content-type": "image/jpeg"}

    def json(self):
        return self._d

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


def _hit(i, tags, large=(3840, 2160), medium=(1920, 1080), seg=12):
    v = lambda wh, nome: {"url": f"https://cdn/{i}_{nome}.mp4" if wh else "", "width": wh[0] if wh else 0,  # noqa: E731
                          "height": wh[1] if wh else 0, "size": 9_000_000 if wh else 0,
                          "thumbnail": f"https://cdn/{i}_{nome}.jpg"}
    return {"id": i, "tags": tags, "duration": seg, "user": "fulano",
            "videos": {"large": v(large, "large"), "medium": v(medium, "medium")}}


def test_busca_escolhe_versao_alta_o_bastante_e_prefere_vertical(monkeypatch):
    monkeypatch.setattr(config, "PIXABAY_API_KEY", "x")
    hits = [_hit(1, "rain, street", large=(3840, 2160), medium=(1920, 1080)),   # deitado: só o 4K serve
            _hit(2, "rain, road", large=None, medium=(1080, 1920)),             # vertical: o medium basta
            _hit(3, "rain, car", large=None, medium=(1920, 1080))]              # baixo demais: fora
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp({"hits": hits}))
    cands = illustrate._busca_pixabay_videos("rain")
    assert [c["id"] for c in cands] == ["pixabay-video:2", "pixabay-video:1"]
    assert cands[0]["grande"].endswith("2_medium.mp4") and cands[1]["grande"].endswith("1_large.mp4")


def test_filtro_tira_gente_curto_e_ja_usado(monkeypatch):
    cands = [{"id": "pixabay-video:1", "texto": "woman walking city", "seg": 12, "miniatura": "m"},
             {"id": "pixabay-video:2", "texto": "rain street", "seg": 3, "miniatura": "m"},
             {"id": "pixabay-video:3", "texto": "rain street", "seg": 12, "miniatura": "m"},
             {"id": "pixabay-video:4", "texto": "storm clouds", "seg": 15, "miniatura": "m"}]
    illustrate._marcar("pixabay-video:3")
    assert [c["id"] for c in illustrate._filtrar_videos(cands)] == ["pixabay-video:4"]


def test_sem_video_bom_cai_na_foto_como_antes(monkeypatch):
    monkeypatch.setattr(illustrate, "video_banco", lambda card, base: None)
    monkeypatch.setattr(illustrate, "foto_banco", lambda card, base: (Path("/tmp/x_banco.jpg"), "Foto: a / Pixabay"))
    card = {"titulo": "t", "chapeu": "CLIMA"}
    assert illustrate.imagem_de_fundo(card, Path("/tmp/x")) == Path("/tmp/x_banco.jpg")
    assert "_video_fundo" not in card


def test_com_video_o_quadro_dele_vira_a_capa(monkeypatch, tmp_path):
    mp4, jpg = tmp_path / "f.mp4", tmp_path / "f.jpg"
    monkeypatch.setattr(illustrate, "video_banco", lambda card, base: (mp4, jpg, "Vídeo: fulano / Pixabay"))
    card = {"titulo": "t", "chapeu": "CLIMA"}
    assert illustrate.imagem_de_fundo(card, tmp_path / "x") == jpg
    assert card["_video_fundo"] == str(mp4) and card["_ilustrativa"] and "Vídeo" in card["_credito"]


def test_desligado_por_variavel(monkeypatch):
    monkeypatch.setattr(config, "PIXABAY_API_KEY", "x")
    monkeypatch.setattr(config, "VIDEO_FUNDO", False)
    assert illustrate.video_banco({"titulo": "t"}, Path("/tmp/x")) is None


def test_montagem_com_video_de_fundo_em_movimento(tmp_path):
    """O vídeo sai no tamanho certo, com o trecho repetindo quando a narração é mais longa."""
    clipe = tmp_path / "clipe.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "testsrc2=size=1280x720:rate=30:duration=1.5", "-pix_fmt", "yuv420p", str(clipe)], check=True)
    audio = tmp_path / "a.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=200:duration=3",
                    "-ar", "24000", str(audio)], check=True)
    card = {"titulo": "Chuva forte alaga ruas do centro", "linha_fina": "", "chapeu": "CLIMA",
            "cidade": "João Pessoa", "destaques": [], "resumo": "Chuva forte.", "pontos": [],
            "_credito": "Vídeo: fulano / Pixabay", "_ilustrativa": True, "_video_fundo": str(clipe)}
    out = audiograma.montar(card, None, audio, 3.0, tmp_path / "r.mp4", tmp_path)
    info = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                           "stream=width,height:format=duration", "-of", "csv=p=0", str(out)],
                          capture_output=True, text=True).stdout.split()
    assert info[0] == f"{audiograma.VW},{audiograma.VH}"
    assert abs(float(info[1]) - 3.0) < 0.2
    # a camada de cima é transparente no meio (o vídeo aparece) e opaca na barra do topo
    camada = Image.open(tmp_path / "camada.png")
    assert camada.mode == "RGBA"
    assert camada.getpixel((audiograma.VW // 2, audiograma.VH // 2))[3] < 40
    assert camada.getpixel((5, 5))[3] == 255
