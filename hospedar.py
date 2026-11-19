"""Link público temporário para o vídeo, usado quando o envio direto à Meta falha.

O arquivo vai para o ramo "midia" deste repositório (público), num commit sem histórico:
cada envio substitui o anterior, então o ramo guarda só o último vídeo. A Meta baixa o
vídeo pelo link (jsDelivr ou raw.githubusercontent.com, ambos servem arquivos de repositório
público). Só funciona dentro do GitHub Actions, que já tem permissão de escrita no repositório.
"""
import os
import subprocess
from pathlib import Path

RAMO = "midia"


def _git(*args, entrada=None) -> str:
    env = dict(os.environ, GIT_AUTHOR_NAME="pbminuto-bot", GIT_COMMITTER_NAME="pbminuto-bot",
               GIT_AUTHOR_EMAIL="pbminuto-bot@users.noreply.github.com",
               GIT_COMMITTER_EMAIL="pbminuto-bot@users.noreply.github.com")
    r = subprocess.run(["git", *args], input=entrada, capture_output=True, text=True, env=env, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"git {args[0]}: {r.stderr.strip()[-300:]}")
    return r.stdout.strip()


def links_publicos(arquivo: Path) -> list:
    """Publica o arquivo no ramo "midia" e devolve os links públicos (o mais confiável primeiro)."""
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo or os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("hospedagem pelo GitHub só funciona dentro do GitHub Actions")
    arquivo = Path(arquivo)
    nome = arquivo.name
    blob = _git("hash-object", "-w", str(arquivo))
    arvore = _git("mktree", entrada=f"100644 blob {blob}\t{nome}\n")
    commit = _git("commit-tree", arvore, "-m", f"mídia temporária: {nome}")
    _git("push", "--force", "origin", f"{commit}:refs/heads/{RAMO}")
    return [f"https://cdn.jsdelivr.net/gh/{repo}@{commit}/{nome}",
            f"https://raw.githubusercontent.com/{repo}/{commit}/{nome}"]
