"""Relatório semanal de desempenho do PB Minuto.

Lê só o banco (state/posts.db) e o estado dos parceiros: as métricas são as da API oficial do
Instagram (alcance, visualizações, salvamentos, compartilhamentos, curtidas e comentários), gravadas
pelo comando `insights` 24h a 7 dias depois de cada post. Nada é estimado: o que falta aparece como
lacuna no relatório.

Métrica principal: alcance típico por post (mediana, para um viral não distorcer o grupo) (é o que o mix de categorias quer aumentar).
Apoio: score de engajamento (compartilhamento 3, salvamento 2, comentário 1, curtida 0,5 por mil
pessoas alcançadas) e visualizações.
"""
import json
import statistics
import time
from datetime import datetime, timedelta, timezone

import config
import sources

FUSO = timezone(timedelta(hours=-3))          # horário de Campina Grande / João Pessoa
AMOSTRA_MIN = 5                               # grupos menores que isso não decidem nada
NOMES_CAT = {"cg": "Campina Grande", "jp": "João Pessoa", "brasil": "Brasil", "mundo": "Mundo",
             "pb": "Paraíba (outras)", "": "sem categoria"}
FAIXAS = [(0, 6, "madrugada (0h–6h)"), (6, 12, "manhã (6h–12h)"), (12, 18, "tarde (12h–18h)"),
          (18, 24, "noite (18h–24h)")]


def _vistos() -> dict:
    try:
        return json.loads((config.STATE_DIR / "parceiro.json").read_text(encoding="utf-8")).get("vistos", {})
    except Exception:
        return {}


def parceiros_sem_metricas(min_h=24, max_h=24 * 7) -> list:
    """Ids (no nosso perfil) dos posts de parceiro com 24h a 7 dias e ainda sem métricas."""
    import db
    agora = time.time()
    return [v["nota"] for v in _vistos().values()
            if v.get("status") == "publicado" and v.get("nota", "").isdigit()
            and agora - max_h * 3600 <= v.get("ts", 0) <= agora - min_h * 3600
            and not db.tem_metricas(v["nota"])]


def _linhas(dias: int) -> list:
    """Uma linha por post com métricas: origem, categoria, editoria, hora, variante e números."""
    desde = time.time() - dias * 86400
    import db
    c = db._conn()   # o mesmo banco que o db usa (cria as tabelas se faltarem)
    cols = {r[1] for r in c.execute("PRAGMA table_info(metricas)")}
    views = "m.views" if "views" in cols else "0"
    tem_var = c.execute("SELECT 1 FROM sqlite_master WHERE name='variantes'").fetchone()
    var_sql = "(SELECT variante FROM variantes v WHERE v.ig_id = m.ig_id)" if tem_var else "NULL"
    rows = c.execute(
        f"SELECT m.ig_id, m.reach, {views}, m.saved, m.shares, m.likes, m.comments, m.score, "
        "  (SELECT MIN(p.ts) FROM posts p WHERE p.ig_id = m.ig_id AND p.status='published'), "
        "  (SELECT r.regiao FROM posts p JOIN regiao r ON r.fp = p.fp WHERE p.ig_id = m.ig_id LIMIT 1), "
        "  (SELECT mt.chapeu FROM posts p JOIN meta mt ON mt.fp = p.fp WHERE p.ig_id = m.ig_id LIMIT 1), "
        "  (SELECT pu.chapeu FROM publicadas pu WHERE pu.ig_id = m.ig_id), "
        "  (SELECT pu.ts FROM publicadas pu WHERE pu.ig_id = m.ig_id), "
        "  (SELECT pu.titulo FROM publicadas pu WHERE pu.ig_id = m.ig_id), "
        f"  {var_sql} "
        "FROM metricas m").fetchall()
    c.close()
    parceiro = {v["nota"]: v for v in _vistos().values() if v.get("status") == "publicado" and v.get("nota")}
    out = []
    for (ig, reach, vw, saved, shares, likes, comments, score, ts_post, reg, chap_meta, chap_pub, ts_pub,
         titulo, variante) in rows:
        p = parceiro.get(ig)
        ts = (p or {}).get("ts") or ts_post or ts_pub
        if not ts or ts < desde:
            continue
        if p:
            origem, cat, editoria = "parceiro", p.get("categoria", ""), p.get("editoria", "")
        else:
            origem = "boletim" if titulo and titulo.lower().startswith("bom dia") else "notícia"
            cat, editoria = reg or "", chap_meta or chap_pub or ""
            if cat in ("paraiba", "local", "") and titulo:
                cat = sources.categoria_texto(titulo)[0] or cat
        hora = datetime.fromtimestamp(ts, FUSO).hour
        out.append({"ig": ig, "ts": ts, "origem": origem, "categoria": cat or "", "editoria": editoria or "—",
                    "faixa": next(n for a, b, n in FAIXAS if a <= hora < b), "variante": variante or "",
                    "reach": reach or 0, "views": vw or 0, "saved": saved or 0, "shares": shares or 0,
                    "likes": likes or 0, "comments": comments or 0, "score": score or 0.0, "titulo": titulo or ""})
    return out


def _agrupar(linhas: list, campo: str) -> list:
    grupos = {}
    for l in linhas:
        grupos.setdefault(l[campo], []).append(l)
    res = []
    for k, ls in grupos.items():
        n = len(ls)
        alcance = sum(l["reach"] for l in ls)
        res.append({"chave": k, "n": n, "alcance": statistics.median(l["reach"] for l in ls),
                    "media": alcance / n, "views": sum(l["views"] for l in ls) / n,
                    "tem_views": any(l["views"] for l in ls),
                    "score": sum(l["score"] for l in ls) / n,
                    "salv_mil": sum(l["saved"] for l in ls) / max(1, alcance) * 1000,
                    "comp_mil": sum(l["shares"] for l in ls) / max(1, alcance) * 1000})
    return sorted(res, key=lambda g: g["alcance"], reverse=True)


def _tabela(grupos: list, titulo_col: str, nomes: dict = None) -> str:
    linhas = [f"| {titulo_col} | posts | alcance típico (mediana) | alcance médio | visualizações | salv./mil | comp./mil | score |",
              "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for g in grupos:
        nome = (nomes or {}).get(g["chave"], g["chave"] or "—")
        aviso = " ⚠️" if g["n"] < AMOSTRA_MIN else ""
        vw = f"{g['views']:,.0f}" if g["tem_views"] else "—"
        linhas.append(f"| {nome}{aviso} | {g['n']} | {g['alcance']:,.0f} | {g['media']:,.0f} | {vw} | "
                      f"{g['salv_mil']:.1f} | {g['comp_mil']:.1f} | {g['score']:.1f} |".replace(",", "."))
    return "\n".join(linhas)


def mix_sugerido(grupos_cat: list, mix_atual: dict, passo_max: int = 10) -> dict:
    """Desloca o mix na direção do alcance típico de cada categoria (só quem está 20% ou mais
    acima/abaixo da média das categorias (no máximo `passo_max` pontos
    por semana, múltiplos de 5, soma 100). Categorias com amostra pequena ficam como estão."""
    por = {g["chave"]: g for g in grupos_cat if g["chave"] in mix_atual and g["n"] >= AMOSTRA_MIN}
    if len(por) < 2:
        return dict(mix_atual)
    media = sum(g["alcance"] for g in por.values()) / len(por)
    novo = {}
    for k, atual in mix_atual.items():
        razao = por[k]["alcance"] / media if k in por and media else 1
        if abs(razao - 1) >= 0.2:   # menos de 20% de diferença é ruído: não mexe
            alvo = atual * razao
            alvo = max(atual - passo_max, min(atual + passo_max, alvo))
            novo[k] = max(5, int(round(alvo / 5) * 5))
        else:
            novo[k] = atual
    # acerta a soma para 100: sobra vai para a melhor categoria, falta sai da pior
    ordem = sorted(por, key=lambda x: por[x]["alcance"])
    while sum(novo.values()) != 100:
        if sum(novo.values()) < 100:
            novo[ordem[-1]] += 5
        else:
            k = next((x for x in ordem if novo[x] > 5), ordem[-1])
            novo[k] -= 5
    return novo


def gerar(dias: int = 7) -> str:
    linhas = _linhas(dias)
    hoje = datetime.now(FUSO)
    cab = [f"# PB Minuto — relatório de {(hoje - timedelta(days=dias)):%d/%m} a {hoje:%d/%m/%Y}", "",
           "Fonte: API oficial do Instagram (insights de cada post, lidos 24h a 7 dias depois). "
           f"Grupos com menos de {AMOSTRA_MIN} posts têm ⚠️ e não entram nas recomendações.", ""]
    if not linhas:
        return "\n".join(cab + ["**Sem métricas no período.** O comando `insights` ainda não leu nenhum post "
                                "(token vencido ou posts com menos de 24h)."])
    total = len(linhas)
    alcance = sum(l["reach"] for l in linhas)
    views = sum(l["views"] for l in linhas)
    comp, salv = sum(l["shares"] for l in linhas), sum(l["saved"] for l in linhas)
    top = sorted(linhas, key=lambda l: l["reach"], reverse=True)[:5]
    fundo = sorted(linhas, key=lambda l: l["reach"])[:3]
    g_cat, g_ed = _agrupar(linhas, "categoria"), _agrupar(linhas, "editoria")
    g_hora, g_orig = _agrupar(linhas, "faixa"), _agrupar(linhas, "origem")
    g_var = _agrupar([l for l in linhas if l["variante"]], "variante")
    mix = {k: round(v * 100) for k, v in config.MIX.items()}
    novo = mix_sugerido(g_cat, mix)

    def f(x):
        return f"{x:,.0f}".replace(",", ".")

    corpo = [
        "## Resultado da semana", "",
        f"- **{total} posts medidos**, alcance total de **{f(alcance)}** pessoas "
        f"(típico de **{f(statistics.median(l['reach'] for l in linhas))}** por post; média de {f(alcance / total)}, "
        f"puxada pelos virais)" + (f" e **{f(views)}** visualizações." if views else "."),
        f"- {f(comp)} compartilhamentos e {f(salv)} salvamentos "
        f"({comp / max(1, alcance) * 1000:.1f} e {salv / max(1, alcance) * 1000:.1f} por mil alcançados).", "",
        "### Os 5 que mais alcançaram", "",
        *[f"{i}. {l['titulo'][:90] or l['ig']} — {f(l['reach'])} pessoas ({NOMES_CAT.get(l['categoria'], l['categoria'])}, "
          f"{l['editoria']}, {l['origem']})" for i, l in enumerate(top, 1)], "",
        "### Os 3 que menos alcançaram", "",
        *[f"- {l['titulo'][:90] or l['ig']} — {f(l['reach'])} pessoas ({l['editoria']}, {l['faixa']})" for l in fundo], "",
        "## Por categoria do mix", "", _tabela(g_cat, "categoria", NOMES_CAT), "",
        "## Por editoria", "", _tabela(g_ed, "editoria"), "",
        "## Por horário", "", _tabela(g_hora, "faixa"), "",
        "## Por origem", "", _tabela(g_orig, "origem"), "",
    ]
    if g_var:
        corpo += ["## Teste A/B do gancho (A = fato primeiro · B = efeito no leitor primeiro)", "", _tabela(g_var, "versão"), ""]
    # 3 recomendações, todas tiradas dos números acima
    rec = []
    if novo != mix:
        txt = ", ".join(f"{NOMES_CAT[k]} {mix[k]}% → {novo[k]}%" for k in mix if novo[k] != mix[k])
        rec.append(f"**Mix:** mudar para {txt}. Para aplicar, troque a variável `MIX` para "
                   f"`{','.join(f'{k}:{v}' for k, v in novo.items())}`.")
    else:
        rec.append("**Mix:** manter como está (diferenças pequenas ou amostra insuficiente).")
    ed_ok = [g for g in g_ed if g["n"] >= AMOSTRA_MIN and g["chave"] != "—"]
    if len(ed_ok) >= 2:
        rec.append(f"**Editoria:** {ed_ok[0]['chave']} alcança {f(ed_ok[0]['alcance'])} num post típico e "
                   f"{ed_ok[-1]['chave']} só {f(ed_ok[-1]['alcance'])}. Priorizar {ed_ok[0]['chave']} na fila "
                   f"e rever o gancho de {ed_ok[-1]['chave']}.")
    else:
        rec.append("**Editoria:** amostra pequena por editoria; esperar mais uma semana.")
    var_ok = [g for g in g_var if g["n"] >= AMOSTRA_MIN]
    hora_ok = [g for g in g_hora if g["n"] >= AMOSTRA_MIN]
    if len(var_ok) >= 2:
        a, b = var_ok[0], var_ok[-1]
        dif = (a["alcance"] / max(1, b["alcance"]) - 1) * 100
        rec.append(f"**Teste A/B:** a versão {a['chave']} alcançou {dif:.0f}% mais que a {b['chave']} "
                   f"({a['n']} x {b['n']} posts). " + ("Diferença grande: dá para fixar a vencedora "
                   f"(variável `AB_GANCHO={a['chave']}`; A = fato primeiro, B = efeito no leitor primeiro)." if dif >= 15 else "Diferença pequena: seguir testando."))
    elif len(hora_ok) >= 2:
        rec.append(f"**Horário:** {hora_ok[0]['chave']} rende {f(hora_ok[0]['alcance'])} por post e "
                   f"{hora_ok[-1]['chave']} {f(hora_ok[-1]['alcance'])}. Guardar as notícias mais fortes "
                   f"para {hora_ok[0]['chave']}.")
    else:
        rec.append("**Horário:** amostra pequena por faixa de horário.")
    lacunas = ["- Alcance e visualizações são os do Instagram; Stories não entram (a API não dá "
               "métricas de Story depois de 24h).",
               "- Correlação não é causa: uma notícia forte puxa a média da categoria. Olhar a tendência "
               "de várias semanas antes de mudanças grandes."]
    if not views:
        lacunas.insert(0, "- Visualizações ainda não registradas nos posts deste período (a leitura começou em 23/11).")
    if not any(l["origem"] == "parceiro" for l in linhas):
        lacunas.insert(0, "- Posts de parceiros ainda sem métricas (a leitura começou em 23/11).")
    lacunas.append("- \"Paraíba (outras)\" não tem cota própria: ocupa a vaga de Campina Grande ou João Pessoa "
                   "que estiver mais atrasada no mix.")
    sem_cat = sum(1 for l in linhas if not l["categoria"])
    if sem_cat:
        lacunas.insert(0, f"- {sem_cat} posts antigos sem categoria registrada.")
    return "\n".join(cab + corpo + ["## 3 recomendações", "", *[f"{i}. {r}" for i, r in enumerate(rec, 1)],
                                    "", "## Lacunas e cuidados", "", *lacunas, ""])
