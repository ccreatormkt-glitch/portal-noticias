"""Registro (SQLite) de tudo que o bot já viu e publicou, para nunca repetir notícia."""
import json
import sqlite3
import time

from config import DB_PATH, DEDUPE_HOURS, LOG_PATH


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.execute("""CREATE TABLE IF NOT EXISTS posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, fp TEXT, stems TEXT,
        headline TEXT, source TEXT, status TEXT, ig_id TEXT, note TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS meta (
        fp TEXT PRIMARY KEY, chapeu TEXT, gatilho TEXT, potencial INTEGER, formato TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS metricas (
        ig_id TEXT PRIMARY KEY, ts REAL, reach INTEGER, saved INTEGER, shares INTEGER,
        likes INTEGER, comments INTEGER, score REAL)""")
    return c


def save_meta(fp, card):
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO meta VALUES (?,?,?,?,?)",
                  (fp, card.get("chapeu"), card.get("gatilho"), card.get("potencial"), card.get("formato")))


def published_without_metrics(min_h=24, max_h=24 * 7):
    now = time.time()
    with _conn() as c:
        return [r[0] for r in c.execute(
            "SELECT DISTINCT p.ig_id FROM posts p LEFT JOIN metricas m ON m.ig_id = p.ig_id "
            "WHERE p.status='published' AND p.ig_id != '' AND m.ig_id IS NULL AND p.ts BETWEEN ? AND ?",
            (now - max_h * 3600, now - min_h * 3600))]


def save_metrics(ig_id, m: dict):
    reach = max(1, m.get("reach", 0))
    score = (m.get("shares", 0) * 3 + m.get("saved", 0) * 2 + m.get("comments", 0)
             + m.get("likes", 0) * 0.5) / reach * 1000
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO metricas VALUES (?,?,?,?,?,?,?,?)",
                  (ig_id, time.time(), m.get("reach", 0), m.get("saved", 0), m.get("shares", 0),
                   m.get("likes", 0), m.get("comments", 0), score))
    return score


def desempenho(campo="chapeu") -> dict:
    """Média do score de engajamento por editoria (ou por gatilho), dos últimos 30 dias."""
    since = time.time() - 30 * 86400
    with _conn() as c:
        rows = c.execute(
            f"SELECT mt.{campo}, AVG(m.score), COUNT(*) FROM metricas m "
            "JOIN posts p ON p.ig_id = m.ig_id JOIN meta mt ON mt.fp = p.fp "
            f"WHERE m.ts > ? GROUP BY mt.{campo}", (since,)).fetchall()
    return {k: (avg, n) for k, avg, n in rows if k}


def _jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


FALHAS = ("falha_publicacao", "falha_video")
MAX_TENTATIVAS = 3


def seen(fp: str, stems: set) -> bool:
    """True se a notícia (ou uma quase igual) já foi tratada. Falhas de publicação não contam,
    para a notícia ser tentada de novo — até MAX_TENTATIVAS vezes."""
    cutoff = time.time() - DEDUPE_HOURS * 3600
    with _conn() as c:
        rows = c.execute("SELECT fp, stems, status FROM posts WHERE ts > ?", (cutoff,)).fetchall()
    falhas = sum(1 for f, _, st in rows if f == fp and st in FALHAS)
    if falhas >= MAX_TENTATIVAS:
        return True
    return any((old_fp == fp or _jaccard(stems, set(old.split())) >= 0.45) and st not in FALHAS
               for old_fp, old, st in rows)


def manchete_repetida(titulo: str) -> str:
    """Compara uma manchete com as que já saíram nos últimos dias (o mesmo fato vindo de outro
    portal, com outras palavras). Devolve a manchete parecida, ou ''."""
    from sources import mesma_historia
    cutoff = time.time() - DEDUPE_HOURS * 3600
    with _conn() as c:
        rows = c.execute("SELECT headline FROM posts WHERE ts > ? AND status IN ('published','gerado','na_fila')",
                         (cutoff,)).fetchall()
    for (h,) in rows:
        if h and mesma_historia(titulo, h):
            return h
    return ""


def record(fp, stems, headline, source, status, ig_id="", note=""):
    with _conn() as c:
        c.execute("INSERT INTO posts (ts, fp, stems, headline, source, status, ig_id, note) "
                  "VALUES (?,?,?,?,?,?,?,?)",
                  (time.time(), fp, " ".join(sorted(stems)), headline, source, status, ig_id, note))
    log({"event": status, "headline": headline, "source": source, "ig_id": ig_id, "note": note})


def update_status(fp, status, ig_id="", note=""):
    with _conn() as c:
        c.execute("UPDATE posts SET status=?, ig_id=?, note=? "
                  "WHERE id = (SELECT MAX(id) FROM posts WHERE fp=?)", (status, ig_id, note, fp))
        row = c.execute("SELECT headline, source FROM posts WHERE fp=?", (fp,)).fetchone()
    log({"event": status, "headline": row[0] if row else "", "source": row[1] if row else "",
         "ig_id": ig_id, "note": note})


def published_today() -> int:
    since = time.time() - 24 * 3600
    with _conn() as c:
        return c.execute("SELECT COUNT(*) FROM posts WHERE status='published' AND ts > ?",
                         (since,)).fetchone()[0]


def log(entry: dict):
    entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), **entry}
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def historico(n=20) -> list:
    with _conn() as c:
        return c.execute("SELECT ts, ig_id, headline, source, note FROM posts WHERE status='published' "
                         "ORDER BY ts DESC LIMIT ?", (n,)).fetchall()
