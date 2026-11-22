"""Publica no Instagram pela API oficial da Meta (Content Publishing).

Fluxo: sobe o JPEG para um link público -> cria o "container" -> espera processar -> publica.
Para carrossel: um container por lâmina -> container do carrossel -> publica.
Exige conta Comercial ou de Criador.
"""
import base64
import re
import mimetypes
import time
import uuid
from pathlib import Path

import requests

from config import (GRAPH_HOST, GRAPH_VERSION, IG_ACCESS_TOKEN, IG_USER_ID, IMGBB_API_KEY,
                    PORTAL_HANDLE, S3_ACCESS_KEY, S3_BUCKET, S3_ENDPOINT, S3_PUBLIC_BASE_URL,
                    S3_SECRET_KEY)

BASE = f"https://{GRAPH_HOST}/{GRAPH_VERSION}"
_LINK = re.compile(r"https?://\S+|www\.\S+", re.I)
_MENCAO = re.compile(r"(?<![\w@])@[\w.]+")


def _ig() -> requests.Session:
    """Sessão da API: o token vai no cabeçalho (nunca na URL, que pode aparecer em logs)."""
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {IG_ACCESS_TOKEN}"
    return s


def _sem_segredos(texto: str) -> str:
    """Tira qualquer chave das mensagens de erro antes de irem para o log."""
    for seg in (IG_ACCESS_TOKEN, IMGBB_API_KEY, S3_SECRET_KEY, S3_ACCESS_KEY):
        if seg:
            texto = texto.replace(seg, "***")
    return re.sub(r"(access_token|key)=[^&\s]+", r"\1=***", texto)


# ------------------------------------------------------------ hospedagem da imagem
def host_image(path: Path) -> str:
    """Envia a imagem para um endereço público e devolve o link."""
    path = Path(path)
    if IMGBB_API_KEY:
        r = requests.post(
            "https://api.imgbb.com/1/upload",
            data={"key": IMGBB_API_KEY, "image": base64.b64encode(path.read_bytes()).decode(),
                  "name": path.stem, "expiration": 60 * 60 * 24 * 7},  # apaga sozinho em 7 dias
            timeout=60,
        )
        if r.status_code >= 400:
            raise RuntimeError(_sem_segredos(f"ImgBB {r.status_code}: {r.text[:200]}"))
        return r.json()["data"]["url"]
    if all([S3_ENDPOINT, S3_BUCKET, S3_ACCESS_KEY, S3_SECRET_KEY, S3_PUBLIC_BASE_URL]):
        import boto3

        s3 = boto3.client("s3", endpoint_url=S3_ENDPOINT, aws_access_key_id=S3_ACCESS_KEY,
                          aws_secret_access_key=S3_SECRET_KEY)
        key = f"cards/{time.strftime('%Y%m%d')}/{uuid.uuid4().hex[:10]}{path.suffix}"
        s3.upload_file(str(path), S3_BUCKET, key,
                       ExtraArgs={"ContentType": mimetypes.guess_type(str(path))[0] or "image/jpeg"})
        return f"{S3_PUBLIC_BASE_URL.rstrip('/')}/{key}"
    raise RuntimeError("Configure IMGBB_API_KEY (ou os S3_*) para hospedar as imagens")


# ------------------------------------------------------------ API do Instagram
def _check(r: requests.Response) -> dict:
    if r.status_code >= 400:
        raise RuntimeError(_sem_segredos(f"Instagram API {r.status_code}: {r.text[:400]}"))
    return r.json()


def _need_creds():
    if not (IG_USER_ID and IG_ACCESS_TOKEN):
        raise RuntimeError("IG_USER_ID / IG_ACCESS_TOKEN não configurados")


def _wait_ready(cid: str):
    for _ in range(30):
        st = _check(_ig().get(f"{BASE}/{cid}", params={"fields": "status_code"}, timeout=30)).get("status_code")
        if st == "FINISHED":
            return
        if st in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"container {cid} com status {st}")
        time.sleep(3)
    raise RuntimeError("o Instagram não terminou de processar a imagem a tempo")


def _container(**fields) -> str:
    return _check(_ig().post(f"{BASE}/{IG_USER_ID}/media", data=fields, timeout=60))["id"]


def _publish(cid: str) -> str:
    return _check(_ig().post(f"{BASE}/{IG_USER_ID}/media_publish",
                                data={"creation_id": cid},
                                timeout=60))["id"]


def quota_left() -> int:
    """Quantos posts ainda cabem no limite de 24h da API (ou -1 se não deu para consultar)."""
    _need_creds()
    try:
        data = _check(_ig().get(f"{BASE}/{IG_USER_ID}/content_publishing_limit",
                                   params={"fields": "config,quota_usage"}, timeout=30))["data"][0]
        return int(data["config"]["quota_total"]) - int(data.get("quota_usage", 0))
    except Exception as e:
        print(f"[instagram] não consegui ler o limite diário: {_sem_segredos(str(e))}")
        return -1


def hashtags_minusculas(texto: str) -> str:
    """Regra do PB Minuto (REGRAS.md): toda hashtag em letras minúsculas (#JoaoPessoa -> #joaopessoa)."""
    return re.sub(r"#([\wÀ-ÿ]+)", lambda m: "#" + m.group(1).lower(), texto or "")


def post(image_paths: list, caption: str) -> str:
    """Publica 1 imagem ou um carrossel (2 a 10 imagens). Devolve o id do post."""
    _need_creds()
    caption = hashtags_minusculas(caption)
    urls = [host_image(p) for p in image_paths]
    if len(urls) == 1:
        cid = _container(image_url=urls[0], caption=caption)
    else:
        children = []
        for u in urls:
            c = _container(image_url=u, is_carousel_item="true")
            _wait_ready(c)
            children.append(c)
        cid = _container(media_type="CAROUSEL", children=",".join(children), caption=caption)
    _wait_ready(cid)
    return _publish(cid)


def _esperar_processar(cid: str) -> str:
    """Espera a Meta processar o vídeo e publica. Erro no processamento levanta RuntimeError."""
    for _ in range(60):  # vídeo demora mais para processar (até ~5 min)
        st = _check(_ig().get(f"{BASE}/{cid}", params={"fields": "status_code,status"}, timeout=30))
        if st.get("status_code") == "FINISHED":
            return _publish(cid)
        if st.get("status_code") in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Reels com erro no processamento: {st.get('status', '')}")
        time.sleep(5)
    raise RuntimeError("o Instagram não terminou de processar o vídeo a tempo")


def _enviar_direto(video_path: Path, caption: str, extra: dict) -> str:
    """Envia o arquivo direto para a Meta (upload "resumable") e publica."""
    dados = Path(video_path).read_bytes()
    cid = _container(media_type="REELS", upload_type="resumable", caption=caption, share_to_feed="true", **extra)
    r = requests.post(f"https://rupload.facebook.com/ig-api-upload/{GRAPH_VERSION}/{cid}",
                      headers={"Authorization": f"OAuth {IG_ACCESS_TOKEN}", "offset": "0",
                               "file_size": str(len(dados))},
                      data=dados, timeout=300)
    if r.status_code >= 400:
        print(f"[reels] envio direto recusado ({len(dados) // 1024} KB): {_sem_segredos(r.text[:160])}")
        _check(r)
    return _esperar_processar(cid)


def post_reel(video_path: Path, caption: str, cover_url: str = None, thumb_ms: int = 1500, capa=None) -> str:
    """Publica um Reels. 1º caminho: link público temporário do vídeo (ramo "midia" do
    repositório) que a Meta baixa — é o que tem funcionado. 2º caminho (fora do GitHub ou se o
    link falhar): envia o arquivo direto para a Meta. Aparece também no feed."""
    _need_creds()
    caption = hashtags_minusculas(caption)
    if GRAPH_HOST != "graph.facebook.com":
        raise RuntimeError("upload direto de vídeo só existe no login pelo Facebook (graph.facebook.com)")
    video_path = Path(video_path)
    extra = {"cover_url": cover_url} if cover_url else {"thumb_offset": str(thumb_ms)}
    capas = []
    try:
        import hospedar
        if capa and Path(capa).exists() and not cover_url:  # a capa sobe junto, no mesmo link
            todos = hospedar.publicar_arquivos([video_path, capa])
            links, capas = todos[video_path.name], todos[Path(capa).name]
        else:
            links = hospedar.links_publicos(video_path)
    except Exception as e:
        links = []
        if "GitHub Actions" not in str(e):
            print(f"[reels] sem link público para o vídeo ({str(e)[:160]})")
    for i, url in enumerate(links):
        tentativas = ([{"cover_url": capas[i]}] if capas else []) + [extra]  # com a capa; se falhar, sem
        for ext in tentativas:
            try:
                cid = _container(media_type="REELS", video_url=url, caption=caption, share_to_feed="true", **ext)
                media_id = _esperar_processar(cid)
                print(f"[reels] enviado por link público ({url.split('/')[2]}"
                      f"{', com capa' if 'cover_url' in ext else ''})")
                return media_id
            except Exception as e:
                if "OAuthException" in str(e):  # token/permissão: não é instabilidade, avisa de verdade
                    raise
                print(f"[reels] link público {url.split('/')[2]} não deu certo: {_sem_segredos(str(e)[:160])}")
    try:
        return _enviar_direto(video_path, caption, extra)
    except RuntimeError as e:
        if "OAuthException" not in str(e) and ("ProcessingFailedError" in str(e) or links):
            raise RuntimeError(f"ProcessingFailedError: envio por link e direto falharam ({str(e)[:200]})")
        raise


STORY_MAX_S = 59   # Stories por API aceitam vídeo de até 60 s


def _video_para_story(video_path: Path) -> Path:
    """O mesmo vídeo do Reels, cortado em 59 s se for mais longo (vídeo de parceiro pode passar)."""
    import subprocess
    try:
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                                    "csv=p=0", str(video_path)], capture_output=True, text=True,
                                   timeout=60).stdout.strip() or 0)
    except Exception:
        dur = 0
    if dur and dur <= STORY_MAX_S:
        return Path(video_path)
    saida = Path(video_path).with_name(Path(video_path).stem + "_story.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video_path), "-t", str(STORY_MAX_S),
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", str(saida)],
                   check=True, capture_output=True, timeout=600)
    return saida


def post_story(video_path: Path) -> str:
    """Publica o vídeo também nos Stories (some em 24h). Conta no limite de 100 publicações/24h.
    Mesmo caminho do Reels: link público temporário; se falhar, envio direto."""
    _need_creds()
    video_path = _video_para_story(Path(video_path))
    try:
        import hospedar
        links = hospedar.links_publicos(video_path)
    except Exception as e:
        links = []
        if "GitHub Actions" not in str(e):
            print(f"[story] sem link público para o vídeo ({str(e)[:160]})")
    for url in links:
        try:
            media_id = _esperar_processar(_container(media_type="STORIES", video_url=url))
            print(f"[story] publicado nos Stories ({url.split('/')[2]})")
            return media_id
        except Exception as e:
            if "OAuthException" in str(e):
                raise
            print(f"[story] link público {url.split('/')[2]} não deu certo: {_sem_segredos(str(e)[:160])}")
    dados = video_path.read_bytes()
    cid = _container(media_type="STORIES", upload_type="resumable")
    r = requests.post(f"https://rupload.facebook.com/ig-api-upload/{GRAPH_VERSION}/{cid}",
                      headers={"Authorization": f"OAuth {IG_ACCESS_TOKEN}", "offset": "0",
                               "file_size": str(len(dados))}, data=dados, timeout=300)
    _check(r)
    return _esperar_processar(cid)


def story_se_paraiba(categoria: str, video_path) -> str:
    """Regra dos Stories: post da Paraíba (cg, jp, pb) vai também para os Stories; Brasil e Mundo não.
    Falha no Story não derruba o post do feed. Devolve o id do Story ou ''."""
    from config import STORIES
    if not video_path or STORIES == "nenhum" or (STORIES == "paraiba" and categoria not in ("cg", "jp", "pb")):
        return ""
    try:
        if quota_left() == 0:
            print("[story] limite de 24h do Instagram cheio: este post fica só no feed")
            return ""
        return post_story(Path(video_path))
    except Exception as e:
        print(f"[story] não deu para publicar nos Stories: {_sem_segredos(str(e)[:200])}")
        return ""


def testar_upload(video_path: Path) -> str:
    """Diagnóstico: cria um contêiner de Reels e envia o vídeo, SEM publicar. Devolve o resultado."""
    _need_creds()
    dados = Path(video_path).read_bytes()
    cid = _container(media_type="REELS", upload_type="resumable", caption="teste", thumb_offset="1000")
    r = requests.post(f"https://rupload.facebook.com/ig-api-upload/{GRAPH_VERSION}/{cid}",
                      headers={"Authorization": f"OAuth {IG_ACCESS_TOKEN}", "offset": "0",
                               "file_size": str(len(dados))}, data=dados, timeout=300)
    out = f"upload HTTP {r.status_code}: {_sem_segredos(r.text[:200])}"
    if r.status_code < 400:
        for _ in range(24):
            st = _check(_ig().get(f"{BASE}/{cid}", params={"fields": "status_code,status"}, timeout=30))
            if st.get("status_code") in ("FINISHED", "ERROR", "EXPIRED"):
                break
            time.sleep(5)
        out += f" | processamento: {st.get('status_code')} {st.get('status', '')}"
    return out


def comentar(media_id: str, texto: str) -> str:
    """Comenta no próprio post (usado para correções públicas)."""
    _need_creds()
    return _check(_ig().post(f"{BASE}/{media_id}/comments",
                                data={"message": texto[:2200]},
                                timeout=30))["id"]


def legendas_recentes(limite: int = 60) -> list:
    """Legendas dos últimos posts do perfil (para não repetir notícia mesmo se o histórico falhar)."""
    _need_creds()
    dados = _check(_ig().get(f"{BASE}/{IG_USER_ID}/media", params={"fields": "caption,timestamp", "limit": limite},
                             timeout=30)).get("data", [])
    return [d.get("caption", "") for d in dados if d.get("caption")]


def account_info() -> dict:
    _need_creds()
    return _check(_ig().get(f"{BASE}/{IG_USER_ID}", params={
        "fields": "username,name,followers_count,media_count"},
        timeout=30))


def media_insights(media_id: str) -> dict:
    """Alcance, salvamentos, compartilhamentos, curtidas e comentários de um post."""
    _need_creds()
    for metrics in ("reach,saved,shares,likes,comments,views", "reach,saved,shares,likes,comments",
                    "reach,saved,likes,comments", "reach"):
        try:
            data = _check(_ig().get(f"{BASE}/{media_id}/insights",
                                       params={"metric": metrics},
                                       timeout=30))["data"]
            return {d["name"]: d["values"][0]["value"] for d in data}
        except Exception:
            continue
    return {}


# ------------------------------------------------------------ legenda
ROTULO_LISTA = {"noticia": "📌 Principais pontos", "o_que_se_sabe": "📌 O que se sabe",
                "entenda": "📌 Entenda", "servico": "📌 Veja como fazer"}


def build_caption(card: dict, source_line: str = "") -> str:
    """Legenda completa (o post é só a capa): abertura, contexto, tópicos, chamada, hashtags."""
    card = dict(card)

    def limpar(t):  # o texto vem de IA lendo notícias: sem links nem @ de terceiros
        return re.sub(r"[ \t]{2,}", " ", _MENCAO.sub("", _LINK.sub("", str(t)))).strip()

    card["legenda"] = limpar(card.get("legenda", ""))
    card["pontos"] = [limpar(x) for x in card.get("pontos", []) if limpar(x)]
    if card.get("resumo"):
        card["resumo"] = limpar(card["resumo"])
    blocos = [b.strip() for b in card["legenda"].strip().split("\n\n") if b.strip()]
    abertura = blocos[0] if blocos else card["titulo"]
    contexto = blocos[1:-1] if len(blocos) >= 3 else blocos[1:]
    chamada = blocos[-1] if len(blocos) >= 3 else ""
    if not contexto and card.get("resumo"):
        contexto = [card["resumo"]]
    partes = [abertura, *contexto]
    pontos = card.get("pontos", [])
    if pontos:
        partes.append(ROTULO_LISTA.get(card.get("formato"), "📌 Principais pontos") + ":\n"
                      + "\n".join(f"• {p}" for p in pontos))
    if chamada:
        partes.append(chamada)
    partes.append(f"👉 Siga {PORTAL_HANDLE} para acompanhar Campina Grande, João Pessoa e toda a Paraíba.")
    if card.get("_credito_legenda"):  # foto do Pexels: crédito e link pedidos pela API
        partes.append(card["_credito_legenda"])
    tags = []
    for t in card.get("hashtags", []):  # limpeza defensiva: sem '#' duplo nem espaços
        t = re.sub(r"[^\wÀ-ÿ]", "", str(t)).lower()   # regra: hashtag sempre em minúsculas
        if t and t not in tags:
            tags.append(t)
    if tags:
        partes.append(" ".join(f"#{t}" for t in tags[:7]))
    return "\n\n".join(partes)[:2200]


def posts_recentes(limite: int = 60) -> list:
    """Últimos posts do perfil: [{id, caption, timestamp, permalink, media_product_type}]."""
    _need_creds()
    r = _ig().get(f"{BASE}/{IG_USER_ID}/media", params={
        "fields": "id,caption,timestamp,permalink,media_product_type", "limit": limite}, timeout=40)
    return _check(r).get("data", [])


def apagar(media_id: str) -> dict:
    """Apaga um post do perfil (IG Media Deleting API da Meta, dez/2025). Não tem volta."""
    _need_creds()
    return _check(_ig().delete(f"{BASE}/{media_id}", timeout=40))
