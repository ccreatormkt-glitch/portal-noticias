"""PB Minuto — bot de notícias automáticas para o Instagram.

  python main.py demo                 gera cards de exemplo (não precisa de chave nenhuma)
  python main.py run [--dry-run]      coleta -> escreve -> desenha -> publica (ou fila)
  python main.py approve [--all|ID]   publica cards que estão na fila (modo review)
  python main.py list                 mostra a fila
  python main.py check-feeds          testa quais fontes estão respondendo
  python main.py check                testa as chaves (IA, Instagram, hospedagem)
  python main.py insights             lê as métricas dos posts e mostra o que mais engaja
  python main.py boletim [--dry-run]  Reels "Bom dia, Paraíba" (tempo do INMET + destaques)
  python main.py errata ID "texto"    correção pública: comenta "⚠️ CORREÇÃO" no post
  python main.py historico            últimos posts com as fontes de cada notícia
"""
import argparse
import os
import socket
import json
import shutil
import sys
import subprocess
import time
from pathlib import Path

import config
import db
import render

socket.setdefaulttimeout(40)  # nenhuma conexão fica pendurada para sempre


def source_line(names) -> str:
    names = [n for n in names if n]
    if not names:
        return ""
    shown = ", ".join(names[:2])
    return shown + (f" e +{len(names) - 2}" if len(names) > 2 else "")


# ------------------------------------------------------------------------- demo
DEMO = [
    {"chapeu": "EMPREGO", "cidade": "Campina Grande", "formato": "servico",
     "linha_fina": "Atendimento é por ordem de chegada, de segunda a sexta.",
     "titulo": "Campina Grande oferta mais de 1.800 vagas de emprego nesta semana",
     "resumo": "As oportunidades são para diversas áreas e níveis de escolaridade. "
               "Os interessados devem procurar o Sine municipal com documento e carteira de trabalho.",
     "pontos": ["Mais de 1.800 vagas abertas", "Atendimento no Sine de Campina Grande",
                "Levar RG, CPF e carteira de trabalho"],
     "legenda": "💼 Tem vaga em Campina Grande!\n\nO Sine municipal divulgou mais de 1.800 "
                "oportunidades para várias áreas.\n\nVocê está procurando emprego? Marca quem precisa ver.",
     "hashtags": ["campinagrande", "paraiba", "emprego", "vagas", "sine"]},
    {"chapeu": "TRÂNSITO", "cidade": "João Pessoa",
     "titulo": "Em JP, trecho da Epitácio Pessoa terá desvio a partir de segunda",
     "resumo": "A mudança vale durante obras de drenagem. Motoristas devem usar vias alternativas.",
     "pontos": [], "legenda": "🚧 Atenção, motorista!", "hashtags": ["joaopessoa"]},
    {"chapeu": "POLÍCIA", "cidade": "Campina Grande", "formato": "o_que_se_sabe",
     "linha_fina": "Homem de 27 anos é investigado por ao menos 5 roubos no Catolé.",
     "titulo": "Suspeito de assaltar ônibus em Campina Grande é preso, diz polícia",
     "resumo": "Segundo a polícia, o homem de 27 anos é investigado por pelo menos cinco roubos "
               "a coletivos no bairro do Catolé. Ele foi encaminhado à central de flagrantes.",
     "pontos": ["Homem de 27 anos foi preso", "Investigado por cinco roubos a ônibus",
                "Caso segue com a Polícia Civil"],
     "legenda": "🚔 Preso em CG.", "hashtags": ["campinagrande"]},
]


def cmd_demo(_):
    for i, card in enumerate(DEMO, 1):
        paths = render.render_post(card, config.OUT_DIR / f"demo_{i}",
                                   "", carousel=config.CAROUSEL)
        for p in paths:
            print("gerado", p)


# -------------------------------------------------------------------------- run
def _publish(card, paths) -> str:
    """Publica a notícia. No formato reels (padrão) é sempre vídeo, com a capa do portal
    como capa do Reels; se o vídeo não existir, levanta erro (não troca por imagem)."""
    import publish

    if config.FORMATO == "reels":
        if not card.get("_video"):
            raise RuntimeError("vídeo não foi gerado")
        card["_reels"] = True
        cover_url = None  # sem hospedagem de imagem, a capa é o próprio quadro do vídeo (a arte é a mesma)
        if card.get("_capa_reels") and config.IMGBB_API_KEY:
            try:
                cover_url = publish.host_image(Path(card["_capa_reels"]))
            except Exception as e:
                print(f"[reels] sem link para a capa ({str(e)[:120]}); usando um quadro do vídeo")
        return publish.post_reel(Path(card["_video"]), publish.build_caption(card), cover_url=cover_url,
                                 capa=card.get("_capa_reels"))
    return publish.post([Path(p) for p in paths], publish.build_caption(card))


def _gerar_video(card, bg, stamp):
    """Gera o Reels e a capa 9:16. Devolve (video, capa) ou (None, None) se falhar."""
    if config.FORMATO != "reels":
        return None, None
    try:
        import video
        destino_capa = config.OUT_DIR / f"{stamp}_capa_reels.jpg"
        if config.ESTILO_VIDEO == "audiograma":  # capa: foto cheia + degradê vermelho + manchete
            import audiograma
            capa = audiograma.capa(card, destino_capa, bg)
        else:
            capa = render.render_cover_reels(card, destino_capa, bg)
        out = video.montar(card, bg, config.OUT_DIR / f"{stamp}.mp4")
        print(f"[reels] vídeo pronto: {out.name}")
        return str(out), str(capa)
    except Exception as e:
        print(f"[reels] não deu para gerar o vídeo ({str(e)[:200]})")
        card["_erro_video"] = str(e)[:200]
        return None, None


CACHE = config.STATE_DIR / "candidatos.json"
CACHE_HORAS = 4


def _bonus_desempenho(card) -> float:
    """Editorias/gatilhos que engajam mais que a média ganham até +1,5 ponto; os fracos perdem."""
    total = 0.0
    for campo in ("chapeu", "gatilho"):
        stats = db.desempenho(campo)
        com_amostra = {k: v for k, v in stats.items() if v[1] >= 3}
        if not com_amostra:
            continue
        media = sum(v[0] for v in com_amostra.values()) / len(com_amostra)
        if card.get(campo) in com_amostra and media > 0:
            rel = com_amostra[card[campo]][0] / media - 1
            total += max(-0.75, min(0.75, rel))
    return total


def _nota(card, cluster_score) -> float:
    return card.get("potencial", 3) * 2 + _bonus_desempenho(card) + cluster_score / 10


def _cache_load() -> list:
    try:
        itens = json.loads(CACHE.read_text(encoding="utf-8"))
    except Exception:
        return []
    return [c for c in itens if time.time() - c.get("_ts", 0) < CACHE_HORAS * 3600]


def _cache_save(itens):
    CACHE.write_text(json.dumps(itens, ensure_ascii=False, indent=1), encoding="utf-8")


_IG_LEGENDAS = {}
_PAUTA = {}


def _repetida_pela_ia(card) -> str:
    """A IA compara com tudo que saiu nas últimas 48h (pega o mesmo fato escrito de outro jeito)."""
    import editor
    recentes = db.titulos_publicados(48) + [l.strip().split("\n")[0] for l in _IG_LEGENDAS.get("lista", [])]
    try:
        igual = editor.mesma_noticia(card, recentes)
    except Exception as e:
        print(f"[run] conferência de repetição pela IA indisponível ({str(e)[:80]}); vale o banco")
        return ""
    return f"mesmo fato já postado (IA): {igual[:60]}" if igual else ""


def _legendas_ig(atualizar=False) -> list:
    """Legendas dos últimos posts do Instagram (uma consulta por rodada; atualiza antes de publicar)."""
    if atualizar or "lista" not in _IG_LEGENDAS:
        try:
            import publish
            _IG_LEGENDAS["lista"] = publish.legendas_recentes()
        except Exception as e:
            print(f"[run] não consegui ler os últimos posts do Instagram ({str(e)[:80]}); sigo pelo banco")
            _IG_LEGENDAS["lista"] = []
    return _IG_LEGENDAS["lista"]


def _candidatos(clusters, quantos, mode) -> list:
    """Escreve até `quantos` posts válidos (reaproveitando os do cache) para escolher o melhor."""
    import editor
    import sources

    cards = [c for c in _cache_load() if not db.seen(c["fp"], set(c["stems"]))]
    ja = {c["fp"] for c in cards}
    tentativas = fails = 0
    prazo = time.monotonic() + 7 * 60  # rodada a cada 10 min: escrever rápido e publicar
    # mix de publicações (CG 30%, JP 20%, Brasil 30%, Mundo 20%): a categoria mais atrasada vem primeiro;
    # se ela não tiver notícia nova confirmada, passa para a próxima (o perfil nunca fica parado)
    ordem = _ordem_do_mix()
    cats = {}
    grupos = {k: [] for k in ordem}
    for c in clusters:
        cat, prio = sources.categoria(c)
        if cat is None:
            continue
        cats[id(c)] = (cat, prio)
        for k in (("cg", "jp") if cat == "pb" else (cat,)):   # notícia do estado todo completa CG ou JP
            if k in grupos:
                grupos[k].append(c)
    for k, lista in grupos.items():
        # cidade antes da região; mais veículos primeiro; no Brasil/Mundo, as manchetes principais
        lista.sort(key=lambda c: (cats[id(c)][1], any(i.feed == "gn_brasil_top" for i in c.items),
                                  c.n_sources, c.score), reverse=True)
    if _PAUTA.get("ativa"):  # pauta pedida: os grupos já são só do assunto (locais ou não)
        fila = [(sources.categoria(c)[0] or "brasil", c) for c in sorted(clusters, key=lambda c: c.n_sources, reverse=True)]
    else:
        fila, ja_na_fila = [], set()
        for k in ordem:
            for c in grupos[k]:
                if id(c) not in ja_na_fila:
                    fila.append((k, c))
                    ja_na_fila.add(id(c))
    vez_brasil = True   # compatibilidade: Brasil e Mundo agora entram pelo mix
    for bucket, c in fila:
        if len(cards) >= quantos or tentativas >= quantos + 3:
            break
        if time.monotonic() > prazo and cards:
            print("[run] tempo de escrita esgotado; seguindo com os candidatos que já tenho")
            break
        confirmed = c.n_sources >= config.MIN_SOURCES or (config.TRUSTED_SINGLE_SOURCE and c.trusted)
        # na pauta pedida, uma tentativa anterior descartada (ex.: texto parecido) pode ser refeita;
        # o que já foi PUBLICADO continua barrado pelo banco de notícias postadas
        visto = (False if _PAUTA.get("refazer") else
                 db.ja_postado(c.fingerprint, c.stems) if _PAUTA.get("ativa") else db.seen(c.fingerprint, c.stems))
        if not confirmed or c.fingerprint in ja or visto:
            continue
        repetida = "" if _PAUTA.get("refazer") else db.manchete_repetida(c.rep.title) or next(
            (k["titulo"] for k in cards if sources.mesma_historia(c.rep.title, k["titulo"])
             or sources.mesma_historia(c.rep.title, k.get("titulo_fonte", ""))), "")
        if repetida:
            print(f"[run] mesmo fato de outro portal, pulando: {c.rep.title[:60]}")
            continue
        tentativas += 1
        t0 = time.monotonic()
        print(f"[run] escrevendo ({c.n_sources} fontes): {c.rep.title[:70]}")
        try:
            card = editor.make_card(c)
            print(f"[run]   pronto em {time.monotonic() - t0:.0f}s")
        except Exception as e:
            fails += 1
            print(f"[run] IA falhou ({str(e)[:120]}); pulando: {c.rep.title[:60]}")
            if fails >= 3:
                print("[run] 3 falhas seguidas: a IA parece fora do ar. Tento na próxima execução.")
                break
            continue
        fails = 0
        texto_card = " ".join([card.get("titulo", ""), card.get("resumo", ""), card.get("legenda", "")])
        if not card.get("skip") and sources.TEMA_PROIBIDO.search(texto_card):
            card["skip"], card["motivo"] = True, "tema proibido (filtro fixo)"
        if card.get("skip"):
            db.record(c.fingerprint, c.stems, c.rep.title, "", "pulado", note=card.get("motivo", ""))
            print(f"[run] pulado ({card.get('motivo', '')[:60]}): {c.rep.title[:60]}")
            continue
        parecida = "" if _PAUTA.get("refazer") else db.manchete_repetida(card["titulo"]) or next(
            (k["titulo"] for k in cards if sources.mesma_historia(card["titulo"], k["titulo"])), "")
        if parecida:
            db.record(c.fingerprint, c.stems, c.rep.title, "", "pulado", note="repetida: " + parecida[:80])
            print(f"[run] pulado (já publicamos algo igual: {parecida[:60]})")
            continue
        # banco de notícias já postadas (+ legendas do próprio Instagram)
        motivo = "" if _PAUTA.get("refazer") else db.ja_publicada(
            {**card, "fp": c.fingerprint, "titulo_fonte": c.rep.title, "links": [i.link for i in c.items[:4]]},
            _legendas_ig() if mode == "auto" else ())
        if not motivo and not _PAUTA.get("refazer"):
            motivo = _repetida_pela_ia(card)
        if motivo:
            db.record(c.fingerprint, c.stems, c.rep.title, "", "pulado", note=motivo[:120])
            print(f"[run] pulado ({motivo})")
            continue
        if config.HUMANIZAR:  # skill STE80 Humanizer: tira cara de texto de IA (legenda e narração)
            card = editor.humanizar(card, c)
        if bucket == "pb":
            bucket = "cg"
        card.update(fp=c.fingerprint, stems=sorted(c.stems), source_line=source_line(c.sources),
                    titulo_fonte=c.rep.title, regiao=bucket, categoria=bucket,
                    **({} if c.is_local else {"cidade": "Mundo" if bucket == "mundo" else "Brasil"}),
                    links=[i.link for i in c.items[:4]], cluster_score=c.score, _ts=time.time())
        cards.append(card)
    for card in cards:
        card["_nota"] = round(_nota(card, card.get("cluster_score", 0)), 2)
        card.setdefault("categoria", _categoria_do_cache(card))
    # a categoria mais atrasada no mix ganha; dentro dela, a melhor nota
    rank = {k: i for i, k in enumerate(ordem)}
    cards.sort(key=lambda x: (rank.get(x["categoria"], len(rank)), -x["_nota"]))
    return cards


def _categoria_do_cache(card: dict) -> str:
    """Categoria de um candidato guardado antes do mix existir."""
    import sources
    if card.get("regiao") in ("cg", "jp", "brasil", "mundo"):
        return card["regiao"]
    if card.get("regiao") == "brasil" or card.get("cidade") == "Brasil":
        return "brasil"
    cat = sources.categoria_texto(" ".join([card.get("titulo", ""), card.get("titulo_fonte", ""),
                                            card.get("cidade", "")]))[0]
    return "cg" if cat == "pb" else cat


def _ordem_do_mix() -> list:
    """Categorias da mais atrasada para a mais adiantada em relação à meta (config.MIX), contando
    notícias e vídeos de parceiro dos últimos config.MIX_JANELA posts. 'pb' (estado todo) vale meio
    para Campina Grande e meio para João Pessoa."""
    import parceiro
    ev = sorted(db.categorias_recentes(config.MIX_JANELA) + parceiro.categorias_recentes(config.MIX_JANELA))
    ev = ev[-config.MIX_JANELA:]
    cont = {k: 0.0 for k in config.MIX}
    for _, cat in ev:
        if cat == "pb":
            cont["cg"] = cont.get("cg", 0) + 0.5
            cont["jp"] = cont.get("jp", 0) + 0.5
        elif cat in cont:
            cont[cat] += 1
    n = len(ev)
    falta = {k: config.MIX[k] * (n + 1) - cont[k] for k in config.MIX}
    ordem = sorted(config.MIX, key=lambda k: (falta[k], config.MIX[k]), reverse=True)
    print("[run] mix (últimos %d): " % n + ", ".join(f"{k} {cont[k]:.0f}/{config.MIX[k]:.0%}" for k in config.MIX)
          + f" -> vez de {ordem[0]}")
    return ordem


def cmd_mesclar(args):
    """Junta o histórico desta rodada (cópia local do banco) ao do repositório, quando duas rodadas
    gravaram ao mesmo tempo. Nada se perde: só entram as linhas que o banco atual ainda não tem."""
    import sqlite3
    db._conn().close()  # garante as tabelas no banco atual
    c = sqlite3.connect(db.DB_PATH)
    c.execute("ATTACH DATABASE ? AS outro", (args.banco,))
    novos = c.execute("""INSERT INTO posts (ts, fp, stems, headline, source, status, ig_id, note)
        SELECT o.ts, o.fp, o.stems, o.headline, o.source, o.status, o.ig_id, o.note FROM outro.posts o
        WHERE NOT EXISTS (SELECT 1 FROM posts p WHERE p.fp = o.fp AND p.ts = o.ts)""").rowcount
    for tabela in ("meta", "regiao", "metricas", "publicadas"):
        try:
            c.execute(f"INSERT OR IGNORE INTO {tabela} SELECT * FROM outro.{tabela}")
        except sqlite3.OperationalError:
            pass
    c.commit()
    c.close()
    db.exportar_csv()  # a planilha do banco de notícias postadas volta completa
    print(f"[histórico] {novos} registro(s) desta rodada juntados ao histórico do repositório")


def cmd_run(args):
    import illustrate
    import sources

    mode = "dry" if args.dry_run else config.POST_MODE
    if mode == "dry":  # teste não mexe no histórico real
        import tempfile
        tmp = Path(tempfile.mkdtemp())
        db.DB_PATH, db.LOG_PATH = tmp / "teste.db", tmp / "teste.jsonl"
        if config.DB_PATH.exists():
            shutil.copy(config.DB_PATH, db.DB_PATH)
    limit = args.count or config.POSTS_PER_RUN

    faltando = [n for n, v in (("OPENAI_API_KEY ou GEMINI_API_KEY", config.OPENAI_API_KEY or config.GEMINI_API_KEY or config.ANTHROPIC_API_KEY),
                               ("IG_USER_ID", config.IG_USER_ID), ("IG_ACCESS_TOKEN", config.IG_ACCESS_TOKEN))
                if not v and (mode == "auto" or n.startswith("OPENAI"))]
    if faltando:  # ainda não configurado: sai sem erro (sem e-mail de falha a cada hora)
        print("[run] aguardando configuração. Falta: " + ", ".join(faltando) + " (veja SETUP.md)")
        return

    pauta_pedida = (getattr(args, "pauta", None) or os.environ.get("PAUTA") or "").strip()
    if mode == "auto" and not pauta_pedida and not args.count:
        import datetime as _dt
        from zoneinfo import ZoneInfo
        hora = _dt.datetime.now(ZoneInfo(config.TIMEZONE)).hour
        if hora < config.HORA_INICIO:  # madrugada: a sequência só espera (pauta pedida posta a qualquer hora)
            print(f"[run] madrugada ({hora}h): sem postagem até as {config.HORA_INICIO}h.")
            return

    if mode == "auto":
        import parceiro
        done_today = db.published_today() + parceiro.publicados_24h()  # notícias + vídeos de parceiro
        if done_today >= config.MAX_POSTS_PER_DAY:
            print(f"[run] limite diário atingido ({done_today}/{config.MAX_POSTS_PER_DAY}). Nada a fazer.")
            return
        import publish
        if publish.quota_left() == 0:
            print("[run] limite de publicações da API do Instagram atingido. Tentando na próxima.")
            return
        # ritmo único do perfil: 1 post a cada ~15 min (notícias + parceiros), o dia todo, sem rajadas
        # que enchem o limite de 24h do Instagram e deixam horas sem post
        pauta_pedida = (getattr(args, "pauta", None) or os.environ.get("PAUTA") or "").strip()
        if not args.count and not pauta_pedida:
            ultimo = max(db.ultimo_publicado(), parceiro.ultimo_publicado())
            espera = config.INTERVALO_POSTS - (time.time() - ultimo)
            if espera > 0:
                print(f"[run] ritmo: último post há {(time.time() - ultimo) / 60:.0f} min; "
                      f"o próximo sai em ~{espera / 60:.0f} min (1 a cada ~{config.INTERVALO_POSTS / 60:.0f} min)")
                return
            if parceiro.vez_do_video():   # notícia e vídeo de parceiro alternam quando os dois têm o que postar
                print("[run] vez do vídeo de parceiro (há vídeo esperando e o último post foi notícia)")
                config.OUT_DIR.mkdir(parents=True, exist_ok=True)
                (config.OUT_DIR / "vez_do_parceiro").write_text("1")   # o vigia chama o parceiro agora
                return
            limit = 1
        restante = publish.quota_left()
        limit = min(limit, config.MAX_POSTS_PER_DAY - done_today, restante if restante > 0 else limit)

    pauta = (getattr(args, "pauta", None) or os.environ.get("PAUTA") or "").strip()
    clusters = sources.build_clusters(pauta) if pauta else sources.build_clusters()
    if pauta:
        print(f"[run] pauta pedida: \"{pauta}\" ({len(clusters)} grupo(s) de notícia sobre o assunto)")
        limit = 1
        _PAUTA["ativa"] = True
        # refazer = o Arthur pediu para postar de novo (ex.: com a foto certa): não barra por repetição
        _PAUTA["refazer"] = (getattr(args, "refazer", False) or os.environ.get("REFAZER", "").lower() == "true")
        foto = (getattr(args, "foto", None) or os.environ.get("FOTO") or "").strip()
        if foto and Path(foto).exists():
            _PAUTA["foto"] = foto
            _PAUTA["credito"] = (os.environ.get("CREDITO") or "").strip()
            print(f"[run] foto escolhida pelo Arthur: {foto}")
        if _PAUTA["refazer"]:
            print("[run] refazendo um post a pedido: sem bloqueio de repetição")
    print(f"[run] {len(clusters)} assuntos encontrados, modo={mode}")
    cards = _candidatos(clusters, max(config.CANDIDATOS, limit), mode)
    for c in cards:
        print(f"  candidato {c['_nota']:5.2f} | pot {c['potencial']} | {c['gatilho']:<13} | {c['titulo'][:70]}")

    escolhidos, sobra = cards[:limit], cards[limit:]
    if mode != "dry":
        _cache_save(sobra)  # os não usados ficam para a próxima hora (sem gastar IA de novo)

    made = pub_fail = 0
    for card in escolhidos:
        fp = card["fp"]
        stamp = time.strftime("%Y%m%d_%H%M%S") + f"_{fp[:6]}"
        if _PAUTA.get("foto"):  # foto escolhida pelo Arthur
            bg = Path(_PAUTA["foto"])
            card["_credito"], card["_ilustrativa"] = _PAUTA.get("credito", ""), False
        else:
            bg = illustrate.imagem_de_fundo(card, config.OUT_DIR / stamp)
        paths = render.render_post(card, config.OUT_DIR / stamp, "", bg, config.CAROUSEL)
        t0 = time.monotonic()
        print(f"[run] montando o vídeo: {card['titulo'][:70]}")
        card["_video"], card["_capa_reels"] = _gerar_video(card, bg, stamp)
        print(f"[run]   vídeo {'pronto' if card['_video'] else 'FALHOU'} em {time.monotonic() - t0:.0f}s")
        db.record(fp, set(card["stems"]), card["titulo"], card["source_line"], "gerado")
        db.save_meta(fp, card)
        card["images"] = [p.name for p in paths]

        if mode == "dry":
            extras = [card.get("_video"), card.get("_capa_reels")]
            print(f"[teste] {card['chapeu']} | {card['titulo']}\n        "
                  + ", ".join(str(p) for p in list(paths) + [e for e in extras if e]))
            (config.OUT_DIR / f"{stamp}.json").write_text(json.dumps(card, ensure_ascii=False, indent=2),
                                                          encoding="utf-8")
        elif mode == "review":
            for p in paths:
                shutil.copy(p, config.QUEUE_PENDING / p.name)
            for k in ("_video", "_capa_reels"):
                if card.get(k):
                    shutil.copy(card[k], config.QUEUE_PENDING / Path(card[k]).name)
                    card[k] = Path(card[k]).name
            (config.QUEUE_PENDING / f"{stamp}.json").write_text(
                json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")
            db.update_status(fp, "na_fila")
            print(f"[fila] {stamp}  {card['titulo']}")
        elif "voz padrão indisponível" in card.get("_erro_video", ""):
            # sem a voz padrão não sai spot com outra voz: a notícia volta na próxima rodada
            db.update_status(fp, "falha_publicacao", note=card["_erro_video"])
            print("[run] voz padrão ocupada: a notícia volta na próxima rodada")
            continue
        else:
            # última conferência, logo antes de soltar (outra rodada pode ter postado o mesmo fato)
            motivo = "" if _PAUTA.get("refazer") else db.ja_publicada(card, _legendas_ig(atualizar=True))
            if motivo:
                db.update_status(fp, "pulado", note=motivo[:120])
                print(f"[run] não publicado ({motivo})")
                continue
            try:
                mid = _publish(card, paths)
            except Exception as e:
                db.update_status(fp, "falha_publicacao", note=str(e)[:300])
                print(f"[run] falha ao publicar: {e}")
                if "ProcessingFailedError" in str(e):
                    print("[run] instabilidade do servidor de upload da Meta: a notícia volta na próxima rodada")
                else:
                    pub_fail += 1  # erro de verdade (token, permissão...): rodada vermelha + e-mail
                continue
            db.update_status(fp, "published", ig_id=mid)
            db.marcar_regiao(fp, card.get("categoria") or card.get("regiao", "paraiba"))
            db.registrar_publicada(card, mid)  # entra no banco de notícias já postadas
            print(f"[publicado] {mid}  {card['titulo']}")
        made += 1
    print(f"[run] fim: {made} post(s) {'gerados' if mode != 'auto' else 'publicados'}")
    if pub_fail:  # faz a execução ficar vermelha no GitHub, que manda e-mail de alerta
        sys.exit(f"{pub_fail} falha(s) de publicação — veja o log acima (token vencido?)")


def cmd_insights(_):
    """Lê alcance/salvamentos/compartilhamentos dos posts com 24h a 7 dias e mostra o ranking."""
    import publish

    for ig_id in db.published_without_metrics():
        m = publish.media_insights(ig_id)
        if m:
            print(f"[métricas] {ig_id}: {m} -> score {db.save_metrics(ig_id, m):.1f}")
    for campo in ("chapeu", "gatilho"):
        stats = sorted(db.desempenho(campo).items(), key=lambda kv: kv[1][0], reverse=True)
        print(f"\nDesempenho por {campo} (score = engajamento por mil pessoas alcançadas):")
        for k, (avg, n) in stats:
            print(f"  {k:<14} {avg:7.1f}  ({n} posts)")


# ------------------------------------------------------------------ fila/review
def _pending():
    return sorted(config.QUEUE_PENDING.glob("*.json"))


def cmd_list(_):
    items = _pending()
    for p in items:
        card = json.loads(p.read_text(encoding="utf-8"))
        print(p.stem, "|", card["chapeu"], "|", card["titulo"])
    if not items:
        print("fila vazia")


def cmd_approve(args):
    todo = [p for p in _pending() if args.all or p.stem == args.id]
    if not todo:
        print("nada para aprovar (use --all ou um ID do `list`)")
        return
    for p in todo:
        card = json.loads(p.read_text(encoding="utf-8"))
        imgs = [config.QUEUE_PENDING / n for n in card["images"]]
        for k in ("_video", "_capa_reels"):
            if card.get(k):
                card[k] = str(config.QUEUE_PENDING / card[k])
                imgs.append(Path(card[k]))
        try:
            mid = _publish(card, imgs)
        except Exception as e:
            db.update_status(card["fp"], "falha_publicacao", note=str(e)[:300])
            print(f"[aprovar] falhou {p.stem}: {e}")
            continue
        db.update_status(card["fp"], "published", ig_id=mid)
        for f in imgs + [p]:
            shutil.move(str(f), config.QUEUE_PUBLISHED / f.name)
        print(f"[publicado] {mid}  {card['titulo']}")


# ---------------------------------------------------------------------- checks
def cmd_check_feeds(_):
    import sources

    items = sources.fetch_items(verbose=True)
    clusters = sources.cluster_items(items)
    ok = [c for c in clusters if c.is_local and (c.n_sources >= config.MIN_SOURCES or c.trusted)]
    print(f"\n{len(items)} manchetes, {len(clusters)} assuntos, {len(ok)} aptos para post. Top 10:")
    for c in ok[:10]:
        print(f"  {c.score:5.1f} | {c.n_sources} fonte(s) | {c.rep.title[:80]}")


def cmd_testar_fontes(args):
    """Testa sites candidatos a fonte: acha o RSS, confere robots.txt, frequência e se é notícia local."""
    import re
    from concurrent.futures import ThreadPoolExecutor
    import sources

    sites = [s for s in re.split(r"[\s,;]+", " ".join(args.sites)) if s]
    with ThreadPoolExecutor(max_workers=8) as ex:
        res = list(ex.map(sources.testar_site, sites))
    res.sort(key=lambda r: (not r["feed"], -(r["em_24h"] or 0)))
    print(f"{'site':34} {'24h':>4} {'últ.h':>6} {'local':>5}  feed / motivo")
    for r in res:
        ult = "" if r["ult_horas"] is None else f"{r['ult_horas']:.1f}"
        info = r["feed"] or r["erro"]
        print(f"{r['site'][:34]:34} {r['em_24h']:>4} {ult:>6} {r['locais']:>5.2f}  {info}")
    Path("out").mkdir(exist_ok=True)
    Path("out/testar_fontes.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))


def cmd_apagar(args):
    """Acha posts do perfil pelo começo da legenda (ou pelo ID) e, só com --confirmar, apaga.
    Sem --confirmar apenas lista o que seria apagado. Apagar não tem volta."""
    import publish
    from sources import fold   # sem acento e em minúsculas: "João" casa com "joao"
    texto = fold(" ".join((args.texto or "").split()))
    alvos = []
    for p in publish.posts_recentes():
        legenda = fold(" ".join((p.get("caption") or "").split()))
        if (args.id and p["id"] == args.id) or (texto and texto in legenda):
            alvos.append(p)
    if args.id and not alvos:
        alvos = [{"id": args.id, "caption": "(fora dos 60 posts mais recentes)", "timestamp": "", "permalink": ""}]
    print(f"[apagar] {len(alvos)} post(s) encontrado(s):")
    for p in alvos:
        print(f"  {p['id']} | {p.get('timestamp', '')} | {p.get('permalink', '')} | "
              f"{' '.join((p.get('caption') or '').split())[:120]}")
    if not args.confirmar:
        print("[apagar] só consulta: nada foi apagado")
        return
    if len(alvos) != 1:
        raise SystemExit("[apagar] para apagar, a busca tem que achar exatamente 1 post (use o ID)")
    res = publish.apagar(alvos[0]["id"])
    print(f"[apagar] apagado {alvos[0]['id']}: {res}")
    db.log({"evento": "apagado", "ig_id": alvos[0]["id"], "permalink": alvos[0].get("permalink", "")})


def cmd_check(_):
    import editor
    import publish

    print("IA:", config.LLM_PROVIDER)
    try:
        txt = editor.generate('Material recebido:\n- Teste de conexão [Teste]\nResponda {"skip": true, "motivo": "teste"}')
        print("  ok:", txt[:80].replace("\n", " "))
    except Exception as e:
        print("  ERRO:", e)
    print("Instagram:")
    try:
        print("  ok:", publish.account_info(), "| posts restantes no limite de 24h:", publish.quota_left())
    except Exception as e:
        print("  ERRO:", e)
    print("Hospedagem de imagem:")
    try:
        demo = render.render_cover(DEMO[0], config.OUT_DIR / "check.jpg", "Teste")
        print("  ok:", publish.host_image(demo))
    except Exception as e:
        print("  ERRO:", e)


def cmd_teste_upload(args):
    """Diagnóstico do Reels: envia um vídeo curto e um longo (arte parada), SEM publicar."""
    import subprocess
    import tempfile
    import publish
    import video
    pasta = Path(tempfile.mkdtemp())
    card = {"titulo": "Teste de envio do PB Minuto", "chapeu": "SERVIÇO", "cidade": "Campina Grande"}
    for seg in (6, 70):
        som = pasta / f"som_{seg}.m4a"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"sine=f=220:d={seg}",
                        "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2", str(som)], check=True)
        mp4 = video.montar(card, None, pasta / f"teste_{seg}.mp4", audio=som, total=float(seg))
        print(f"[teste-upload] {seg}s ({mp4.stat().st_size // 1024} KB): {publish.testar_upload(mp4)}")


def cmd_modelos(args):
    """Lista os modelos do Gemini que a chave pode usar (só nomes; a chave não aparece)."""
    import requests
    r = requests.get("https://generativelanguage.googleapis.com/v1beta/models",
                     headers={"x-goog-api-key": config.GEMINI_API_KEY}, params={"pageSize": 200}, timeout=30)
    if r.status_code != 200:
        print(f"[modelos] erro {r.status_code}")
        return
    for mdl in r.json().get("models", []):
        if "generateContent" in mdl.get("supportedGenerationMethods", []):
            print("  ", mdl["name"].split("/")[-1])


def cmd_errata(args):
    """Correção pública: comenta '⚠️ Correção' no post e registra no histórico."""
    import datetime as dt
    from zoneinfo import ZoneInfo

    import publish

    if not str(args.post_id).strip().isdigit():
        raise SystemExit("ID do post inválido: use só os números (veja em: python main.py historico)")
    if not args.texto.strip():
        raise SystemExit("Escreva o texto da correção")
    agora = dt.datetime.now(ZoneInfo(config.TIMEZONE)).strftime("%d/%m às %Hh%M")
    texto = f"⚠️ CORREÇÃO ({agora}): {args.texto.strip()}"
    cid = publish.comentar(args.post_id, texto)
    db.log({"event": "errata", "ig_id": args.post_id, "note": texto, "comment_id": cid})
    print(f"[errata] publicada no post {args.post_id}: {texto}")


def cmd_historico(args):
    """Últimos posts publicados, com as fontes de onde cada notícia veio."""
    import datetime as dt
    from zoneinfo import ZoneInfo

    for ts, ig, titulo, fonte, _ in db.historico(args.n):
        quando = dt.datetime.fromtimestamp(ts, ZoneInfo(config.TIMEZONE)).strftime("%d/%m %Hh%M")
        print(f"{quando} | {ig} | {titulo}\n            fontes: {fonte or '-'}")


def cmd_boletim(args):
    import boletim
    if not args.dry_run and not (config.IG_USER_ID and config.IG_ACCESS_TOKEN):
        print("[boletim] aguardando configuração do Instagram (veja SETUP.md)")
        return
    boletim.rodar(dry=args.dry_run)


def cmd_parceiro(args):
    import parceiro
    if args.modo != "dry" and not (config.IG_USER_ID and config.IG_ACCESS_TOKEN):
        print("[parceiro] aguardando configuração do Instagram (veja SETUP.md)")
        return
    parceiro.rodada(args.modo, args.limite)


def cmd_parceiro_fila(_):
    import json as _json

    import parceiro
    itens = sorted(parceiro.FILA.glob("*.json"))
    for p in itens:
        card = _json.loads(p.read_text(encoding="utf-8"))
        print(p.stem, "|", card["chapeu"], "|", card["titulo"], "|", card["_origem"].get("permalink", ""))
    if not itens:
        print("fila do parceiro vazia")


def cmd_parceiro_amostra(args):
    import parceiro
    parceiro.amostra(args.usuario.lstrip("@"))


def cmd_parceiro_refazer(args):
    import parceiro
    ids = [i for i in " ".join(args.ids).replace(",", " ").split() if i]
    print(f"[parceiro] {parceiro.refazer(ids)} vídeo(s) refeito(s)")


def cmd_parceiro_aprovar(args):
    import parceiro
    if not (args.all or args.id):
        raise SystemExit("use --all ou um ID do `parceiro-fila`")
    print(f"[parceiro] {parceiro.aprovar(args.all, args.id or '')} publicado(s)")


def cmd_parceiro_descartar(args):
    import parceiro
    print("descartado" if parceiro.descartar(args.id) else "ID não está na fila")


def cmd_parceiro_testar(_):
    import parceiro
    if not parceiro.testar_download():
        raise SystemExit(1)


def cmd_parceiro_calibrar(_):
    import parceiro
    parceiro.calibrar()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo").set_defaults(fn=cmd_demo)
    r = sub.add_parser("run")
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--count", type=int)
    r.add_argument("--pauta", help='assunto pedido (ex.: "Natal Iluminado"): busca e publica a notícia dele')
    r.add_argument("--foto", help="foto a usar na capa e no vídeo (caminho no repositório)")
    r.add_argument("--refazer", action="store_true", help="posta de novo mesmo se a notícia já saiu")
    m = sub.add_parser("mesclar", help="junta o histórico de uma rodada ao do repositório")
    m.add_argument("banco")
    m.set_defaults(fn=cmd_mesclar)
    r.set_defaults(fn=cmd_run)
    a = sub.add_parser("approve")
    a.add_argument("id", nargs="?")
    a.add_argument("--all", action="store_true")
    a.set_defaults(fn=cmd_approve)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    sub.add_parser("check-feeds").set_defaults(fn=cmd_check_feeds)
    p = sub.add_parser("apagar", help="acha um post pela legenda ou ID; com --confirmar, apaga (sem volta)")
    p.add_argument("--texto", default="")
    p.add_argument("--id", default="")
    p.add_argument("--confirmar", action="store_true")
    p.set_defaults(fn=cmd_apagar)
    p = sub.add_parser("testar-fontes", help="testa sites candidatos a fonte (RSS, robots, frequência)")
    p.add_argument("sites", nargs="+")
    p.set_defaults(fn=cmd_testar_fontes)
    sub.add_parser("modelos").set_defaults(fn=cmd_modelos)
    sub.add_parser("teste-upload").set_defaults(fn=cmd_teste_upload)
    sub.add_parser("check").set_defaults(fn=cmd_check)
    sub.add_parser("insights").set_defaults(fn=cmd_insights)
    e = sub.add_parser("errata")
    e.add_argument("post_id")
    e.add_argument("texto")
    e.set_defaults(fn=cmd_errata)
    h = sub.add_parser("historico")
    h.add_argument("-n", type=int, default=20)
    h.set_defaults(fn=cmd_historico)
    b = sub.add_parser("boletim")
    b.add_argument("--dry-run", action="store_true")
    b.set_defaults(fn=cmd_boletim)
    pc = sub.add_parser("parceiro", help="vídeos do perfil parceiro com a marca do PB Minuto")
    pc.add_argument("--modo", choices=["review", "auto", "dry"], default=None)
    pc.add_argument("--limite", type=int, default=1, help="vídeos por rodada")
    pc.set_defaults(fn=cmd_parceiro)
    sub.add_parser("parceiro-fila").set_defaults(fn=cmd_parceiro_fila)
    pam = sub.add_parser("parceiro-amostra", help="baixa as últimas imagens de um perfil para estudar a moldura")
    pam.add_argument("usuario")
    pam.set_defaults(fn=cmd_parceiro_amostra)
    pr = sub.add_parser("parceiro-refazer", help="refaz vídeos de parceiro já publicados (ids do parceiro)")
    pr.add_argument("ids", nargs="+")
    pr.set_defaults(fn=cmd_parceiro_refazer)
    pa = sub.add_parser("parceiro-aprovar")
    pa.add_argument("id", nargs="?")
    pa.add_argument("--all", action="store_true")
    pa.set_defaults(fn=cmd_parceiro_aprovar)
    pd = sub.add_parser("parceiro-descartar")
    pd.add_argument("id")
    pd.set_defaults(fn=cmd_parceiro_descartar)
    sub.add_parser("parceiro-calibrar").set_defaults(fn=cmd_parceiro_calibrar)
    sub.add_parser("parceiro-testar", help="testa o download do Reel mais recente do parceiro").set_defaults(
        fn=cmd_parceiro_testar)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
