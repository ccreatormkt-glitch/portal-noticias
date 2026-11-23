"""Marca d'água nas fotos dos parceiros (posts de imagem): acha e apaga a marca do PARCEIRO que
autorizou o uso; marca de OUTRO veículo (TV, jornal, "Foto: fulano") não é apagada: a foto não é
usada e o robô volta para a ilustração.

Como funciona:
  1. OCR (RapidOCR, ONNX na CPU) lê os textos da foto.
  2. Texto com o nome do parceiro (em qualquer lugar) = marca do parceiro -> apaga.
     Texto com cara de marca/crédito de outro veículo (@, www, .com, "foto:", TV, perto da borda)
     = marca de terceiro -> devolve None (a foto não é usada).
     Texto comum no meio da cena (placa, faixa, camisa) fica como está.
  3. Apaga com o Big LaMa (preenchimento por IA, TorchScript na CPU, baixado do GitHub na 1ª vez e
     guardado no cache do Actions). A máscara pega só os traços da marca (não o retângulo todo) e
     só a janela em volta dela é trocada; o resto da foto fica intacto.
     Sem o LaMa, a foto não é usada (PARCEIRO_MARCA_SEM_LAMA=opencv usa o inpaint do OpenCV).
  4. Confere: lê a foto de novo; se o nome do parceiro ainda aparece, devolve None.
"""
import re
import unicodedata
from pathlib import Path

from PIL import Image, ImageFilter

import config

# Nomes que aparecem na marca de cada parceiro (sem acento, minúsculo, sem espaço). "perfil:nome,nome; ..."
MARCAS_PADRAO = ("bombaparaiba_:bombaparaiba,bomba; noticiacertapb:noticiacerta,noticiacertapb; "
                 "jornaldapb:jornaldapb; destaques.dodia:destaquesdodia,destaquesdo; "
                 "portalresumopb:resumopb,portalresumo; blognewspb:blognewspb,blognews; "
                 "paraibabussines_:paraibabussines,paraibabusiness")
# Sinais de marca/crédito de outro veículo
TERCEIRO = re.compile(r"(@\w|www|\.com|\.br|foto|fotos|credito|reproducao|divulgacao|©|copyright|"
                      r"\btv\b|g1|globo|record|sbt|band|cabobranco|tvcorreio|arapuan|clickpb|wscom|"
                      r"paraibaonline|portalcorreio|maispb|polemicaparaiba|jornaldaparaiba|portalt5|"
                      r"blogdo|shutterstock|getty|istock|alamy|freepik)")
BORDA = 0.16               # texto a até 16% da borda conta como marca, se tiver cara de marca
LAMA_URL = config.env("LAMA_URL", "https://github.com/enesmsahin/simple-lama-inpainting/releases/download/v0.1.0/big-lama.pt")
LAMA_CACHE = config.env("LAMA_CACHE", "~/.cache/lama/big-lama.pt")
# Sem o LaMa: "ilustracao" (padrão) = não usa a foto (o OpenCV deixa borrão); "opencv" = usa mesmo assim
SEM_LAMA = config.env("PARCEIRO_MARCA_SEM_LAMA", "ilustracao").lower()
_ocr = None
_lama = None


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9@.©]", "", t)


def nomes_do_parceiro(usuario: str) -> list:
    usuario = (usuario or "").lstrip("@").lower()
    tabela = {}
    for item in config.env("PARCEIRO_MARCAS", MARCAS_PADRAO).split(";"):
        if ":" in item:
            perfil, nomes = item.split(":", 1)
            tabela[perfil.strip().lstrip("@").lower()] = [_norm(n) for n in nomes.split(",") if _norm(n)]
    base = _norm(usuario.rstrip("_")).replace(".", "")
    return sorted({base, *tabela.get(usuario, [])} - {""}, key=len, reverse=True)


def _ler(img: Image.Image) -> list:
    """[(caixa x0,y0,x1,y1, texto)] dos textos da foto."""
    global _ocr
    import numpy as np
    if _ocr is None:
        from rapidocr_onnxruntime import RapidOCR
        _ocr = RapidOCR()
    res, _ = _ocr(np.asarray(img.convert("RGB"))[:, :, ::-1])
    out = []
    for pts, texto, conf in res or []:
        if float(conf) < 0.5:
            continue
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        out.append(((int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))), texto))
    return out


def classificar(textos: list, W: int, H: int, usuario: str) -> tuple:
    """(caixas do parceiro, caixas de outro veículo)."""
    nomes = nomes_do_parceiro(usuario)
    parceiro, terceiro = [], []
    for caixa, texto in textos:
        n = _norm(texto)
        sem_ponto = n.replace(".", "")
        x0, y0, x1, y1 = caixa
        perto_da_borda = (x0 < W * BORDA or y0 < H * BORDA or x1 > W * (1 - BORDA) or y1 > H * (1 - BORDA))
        # nome completo vale em qualquer lugar; apelido curto ("bomba") só perto da borda
        if any(x in sem_ponto for x in nomes if len(x) >= 8 or perto_da_borda):
            parceiro.append(caixa)
            continue
        if perto_da_borda and TERCEIRO.search(n):
            terceiro.append(caixa)
    return parceiro, terceiro


def mascara(img: Image.Image, caixas: list) -> Image.Image:
    """Branco = apagar. Dentro de cada caixa do OCR, pega só os traços da marca (o que destoa do fundo
    em volta: letra, contorno, sombra) e engrossa um pouco; máscara pequena = preenchimento melhor.
    Se os traços não se separam do fundo, vale a caixa inteira (com folga)."""
    import numpy as np
    from PIL import ImageDraw
    W, H = img.size
    cinza = np.asarray(img.convert("L")).astype(np.float32)
    m = np.zeros((H, W), bool)
    for x0, y0, x1, y1 in caixas:
        f = max(6, int((y1 - y0) * 0.35))
        a0, b0, a1, b1 = max(0, x0 - f), max(0, y0 - f), min(W, x1 + f), min(H, y1 + f)
        rec = img.crop((a0, b0, a1, b1)).convert("L")
        fundo = np.asarray(rec.filter(ImageFilter.MedianFilter(_impar(max(9, (y1 - y0) // 2 * 2 + 1)))),
                           np.float32)
        tracos = np.abs(cinza[b0:b1, a0:a1] - fundo) > 22
        if 0.04 < tracos.mean() < 0.7:
            m[b0:b1, a0:a1] |= tracos
        else:
            m[b0:b1, a0:a1] = True
    out = Image.fromarray((m * 255).astype(np.uint8))
    return out.filter(ImageFilter.MaxFilter(11))


def _impar(n: int) -> int:
    return min(n, 51) | 1


def _modelo_lama():
    global _lama
    if _lama is None:
        import torch
        arq = Path(LAMA_CACHE).expanduser()
        if not arq.exists() or arq.stat().st_size < 100_000_000:
            import requests
            arq.parent.mkdir(parents=True, exist_ok=True)
            tmp = arq.with_suffix(".parcial")
            with requests.get(LAMA_URL, stream=True, timeout=300) as r:
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    for bloco in r.iter_content(1 << 20):
                        f.write(bloco)
            tmp.replace(arq)
        torch.set_num_threads(max(1, torch.get_num_threads()))
        _lama = torch.jit.load(str(arq), map_location="cpu").eval()
    return _lama


def _lama_512(img: Image.Image, m: Image.Image) -> Image.Image:
    """Big LaMa (TorchScript, CPU) numa janela de 512x512."""
    import numpy as np
    import torch
    modelo = _modelo_lama()
    a = np.asarray(img.convert("RGB").resize((512, 512), Image.BICUBIC)).astype(np.float32) / 255.0
    k = (np.asarray(m.resize((512, 512), Image.NEAREST)) > 127).astype(np.float32)
    with torch.inference_mode():
        r = modelo(torch.from_numpy(a.transpose(2, 0, 1))[None], torch.from_numpy(k)[None, None])[0]
    r = r.permute(1, 2, 0).numpy()
    if r.max() <= 1.5:
        r = r * 255.0
    return Image.fromarray(np.clip(r, 0, 255).astype(np.uint8))


def _opencv(img: Image.Image, m: Image.Image) -> Image.Image:
    import cv2
    import numpy as np
    a = cv2.inpaint(np.asarray(img.convert("RGB"))[:, :, ::-1].copy(), np.asarray(m), 7, cv2.INPAINT_TELEA)
    return Image.fromarray(a[:, :, ::-1].copy())


def apagar(img: Image.Image, m: Image.Image) -> tuple:
    """Preenche a área branca da máscara. Trabalha num recorte quadrado em volta de cada marca
    (LaMa enxerga em 512x512): a marca some com detalhe e o resto da foto não é tocado."""
    img = img.convert("RGB")
    W, H = img.size
    caixa = m.getbbox()
    if not caixa:
        return img, "nada"
    x0, y0, x1, y1 = caixa
    lado = min(max(W, H), max(512, int(max(x1 - x0, y1 - y0) * 2.2)))
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    bx0 = max(0, min(W - lado, cx - lado // 2)) if W >= lado else 0
    by0 = max(0, min(H - lado, cy - lado // 2)) if H >= lado else 0
    janela = (bx0, by0, min(W, bx0 + lado), min(H, by0 + lado))
    rec, mrec = img.crop(janela), m.crop(janela)
    try:
        cheio = _lama_512(rec, mrec).resize(rec.size, Image.LANCZOS)
        motor = "LaMa"
    except Exception as e:
        if SEM_LAMA != "opencv":
            raise RuntimeError(f"LaMa indisponível: {str(e)[:160]}")
        print(f"[marca] LaMa indisponível ({str(e)[:120]}): uso o OpenCV")
        cheio, motor = _opencv(rec, mrec), "OpenCV"
    suave = mrec.filter(ImageFilter.GaussianBlur(3))     # costura sem degrau
    rec.paste(cheio, (0, 0), suave)
    out = img.copy()
    out.paste(rec, janela[:2])
    return out, motor


def limpar(foto_jpg: Path, usuario: str, out_jpg: Path = None):
    """Foto pronta para usar (Path) ou None quando não dá para usar (marca de outro veículo, ou a
    marca do parceiro continua lá depois de apagar)."""
    out_jpg = Path(out_jpg or Path(foto_jpg).with_name(Path(foto_jpg).stem + "_limpa.jpg"))
    img = Image.open(foto_jpg).convert("RGB")
    W, H = img.size
    try:
        textos = _ler(img)
    except Exception as e:
        print(f"[marca] OCR indisponível ({str(e)[:120]}): sigo sem a foto")
        return None
    parc, terc = classificar(textos, W, H, usuario)
    if terc:
        print(f"[marca] marca de outro veículo na foto ({len(terc)} trecho(s)): não apago; vai a ilustração")
        return None
    for volta in range(3):                      # 2ª/3ª volta pega o que sobrou (ex.: 2 linhas de logo)
        if not parc:
            break
        try:
            img, motor = apagar(img, mascara(img, parc))
        except RuntimeError as e:
            print(f"[marca] {e}: sigo sem a foto")
            return None
        print(f"[marca] apaguei {len(parc)} trecho(s) da marca do parceiro com {motor}")
        parc, terc = classificar(_ler(img), W, H, usuario)
    if parc:
        print("[marca] a marca do parceiro continuou visível: sigo sem a foto")
        return None
    img.save(out_jpg, quality=95)
    return out_jpg
