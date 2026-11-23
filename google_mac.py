"""Roda no Mac do Arthur (runner do GitHub "pbminuto-mac"): faz a busca no Google Imagens com o Chrome
e a internet dele (quase sem captcha) e devolve o print da foto ao robô pelo ramo "google-fotos".

Uso pelo workflow google-mac.yml:  python google_mac.py            (lê o pedido em $PEDIDO)
Uma vez, no Terminal do Mac:       python google_mac.py --entrar   (abre o Chrome do robô para
                                   entrar na conta Google e aceitar os cookies)
Teste manual:                      python google_mac.py --testar "manchete da notícia"
"""
import base64
import json
import os
import sys
import tempfile
import time
from pathlib import Path

PERFIL_PADRAO = "~/.pbminuto-chrome"
PEDIDO_VALIDADE = 300                        # pedido mais velho que isso já foi abandonado pelo robô


def _gravar_no_ramo(nome: str, dados: bytes):
    import illustrate
    r = illustrate._gh("GET", f"contents/{nome}", params={"ref": illustrate.RAMO_GOOGLE})
    sha = r.json().get("sha") if r.status_code == 200 else None
    corpo = {"message": f"google: {nome}", "branch": illustrate.RAMO_GOOGLE,
             "content": base64.b64encode(dados).decode(), **({"sha": sha} if sha else {})}
    r = illustrate._gh("PUT", f"contents/{nome}", json=corpo)
    if r.status_code == 404 or (r.status_code == 422 and "branch" in r.text.lower()):
        _criar_ramo()
        r = illustrate._gh("PUT", f"contents/{nome}", json=corpo)
    r.raise_for_status()


def _criar_ramo():
    """Cria o ramo google-fotos a partir do main (só da primeira vez)."""
    import illustrate
    main = illustrate._gh("GET", "git/ref/heads/main").json()["object"]["sha"]
    illustrate._gh("POST", "git/refs", json={"ref": f"refs/heads/{illustrate.RAMO_GOOGLE}", "sha": main})


def atender(pedido: dict) -> dict:
    """Faz a busca e devolve {"site", "foto_id"} ou {"erro"}; a foto fica em <pasta>/<id>_google.jpg."""
    import config
    import illustrate
    pasta = Path(tempfile.mkdtemp(prefix="pbminuto-google-"))
    config.STATE_DIR = pasta                       # fotos já usadas: a lista que o robô mandou
    (pasta / "fotos_usadas.txt").write_text("\n".join(pedido.get("usadas", [])) + "\n")
    card = dict(pedido.get("card") or {})
    try:
        achou = illustrate.print_google_aqui(card, pasta / pedido["id"])
    except Exception as e:
        return {"erro": f"{type(e).__name__}: {str(e)[:200]}"}
    if not achou:
        return {"erro": "nenhuma foto aprovada (ou o Google pediu captcha): veja o registro"}
    arquivo, credito = achou
    return {"site": credito.split("/", 1)[-1].strip(), "foto_id": card.get("_google_id", ""),
            "arquivo": str(arquivo)}


def _preparar_ambiente():
    """Antes de importar config: Chrome de verdade, perfil próprio do robô e navegador local."""
    os.environ.setdefault("GOOGLE_PERFIL", PERFIL_PADRAO)
    os.environ.setdefault("GOOGLE_CHROME", "true")
    os.environ["GOOGLE_VIA"] = "aqui"


def main():
    _preparar_ambiente()
    if "--entrar" in sys.argv:
        from playwright.sync_api import sync_playwright
        perfil = Path(os.environ["GOOGLE_PERFIL"]).expanduser()
        perfil.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as pw:
            ctx = pw.chromium.launch_persistent_context(str(perfil), channel="chrome", headless=False,
                                                        locale="pt-BR")
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto("https://accounts.google.com/")
            input("Entre na conta Google na janela do Chrome, aceite os cookies e aperte Enter aqui... ")
            ctx.close()
        print(f"Pronto: perfil do robô salvo em {perfil}")
        return
    if "--testar" in sys.argv:
        titulo = " ".join(sys.argv[sys.argv.index("--testar") + 1:]) or "Praia de Tambaú João Pessoa"
        res = atender({"id": "teste", "card": {"titulo": titulo, "cidade": "João Pessoa"}})
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return
    pedido = json.loads(base64.b64decode(os.environ["PEDIDO"]).decode())
    if time.time() - float(pedido.get("t", 0)) > PEDIDO_VALIDADE:
        print(f"[google] pedido {pedido.get('id')} velho demais: o robô já seguiu sem ele")
        return
    pid = "".join(c for c in str(pedido["id"]) if c.isalnum() or c == "-")[:40]
    pedido["id"] = pid
    res = atender(pedido)
    if res.get("site"):
        _gravar_no_ramo(f"{pid}.jpg", Path(res.pop("arquivo")).read_bytes())
    _gravar_no_ramo(f"{pid}.json", json.dumps(res, ensure_ascii=False).encode())
    print(f"[google] pedido {pid}: {res}")


if __name__ == "__main__":
    main()
