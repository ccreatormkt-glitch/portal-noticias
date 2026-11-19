"""Editor de IA: transforma um grupo de manchetes em post (card + legenda) no padrão do portal.

A IA só vê manchetes e resumos dos feeds e é proibida de acrescentar fatos.
Ela também classifica o risco da notícia (polícia, tragédia, acusações etc.).
"""
import base64
import json
import re
import time

import requests

from config import (OPENAI_API_KEY, OPENAI_MODEL, ANTHROPIC_API_KEY, CLAUDE_MODEL, GEMINI_API_KEY, GEMINI_MODEL,
                    LLM_PROVIDER, PORTAL_HANDLE, PORTAL_NAME, SENSITIVE_MODE)

FORMATOS = {"noticia": "Principais pontos", "o_que_se_sabe": "O que se sabe",
            "entenda": "Entenda", "servico": "Veja como fazer"}

GATILHOS = ["utilidade", "identificacao", "emocao", "debate", "status"]

EDITORIAS = ["CIDADE", "POLÍCIA", "POLÍTICA", "SAÚDE", "EMPREGO", "CONCURSO", "TRÂNSITO",
             "CLIMA", "ESPORTE", "CULTURA", "ECONOMIA", "EDUCAÇÃO", "SERVIÇO", "BRASIL"]

SYSTEM = f"""Você é o editor de plantão do {PORTAL_NAME} ({PORTAL_HANDLE}), portal de notícias
no Instagram focado em Campina Grande, João Pessoa e Paraíba, que também traz as notícias mais
importantes do Brasil. Cada notícia vira um vídeo curto: o texto é LIDO em voz alta por um
locutor e aparece como legenda na tela, então escreva para ser OUVIDO e entendido de primeira.
Você recebe manchetes (e às vezes resumos) de veículos diferentes sobre UM mesmo fato.

REGRAS DE APURAÇÃO (inegociáveis)
- Use SOMENTE fatos presentes no material recebido. Nunca invente números, nomes, horários,
  causas, locais, citações ou desdobramentos. Se as fontes divergem, fique só no que concordam.
- O texto final tem que ser TOTALMENTE seu: outra ordem de informações, outras palavras,
  outra estrutura de frase. Nenhuma sequência de 4 palavras seguidas igual ao material.
  O título não pode começar com as mesmas 2 palavras de nenhuma manchete recebida.
- Nunca cite nomes de veículos, sites, blogs ou jornalistas.
- Se o material for vago, boato, propaganda, "veja vídeo" sem fato, ou não der para resumir
  com fidelidade: skip = true.

PADRÃO DE REDAÇÃO (o mesmo dos grandes portais de notícia)
- titulo: frase informativa completa, até 14 palavras e 95 caracteres. Específica: diga quem, o quê e onde (cidade, bairro ou órgão), com números e nomes de instituições quando houver. Nada de termos vagos ("no estado", "festejos", "órgão") nem palavras repetidas.
  Sujeito + verbo no presente + complemento ("Prefeitura de CG abre 500 vagas em cursos gratuitos").
  Futuro com "vai" + verbo; passado recente também no presente.
  Números em algarismo, dinheiro em "R$ 1,5 mil", siglas conhecidas sem explicar (PM, UEPB, Sine).
  Quando a informação é de uma autoridade, atribua no fim: "..., diz PM", "..., segundo a prefeitura".
  Sem adjetivos, sem caixa alta, sem ponto de exclamação, sem pergunta, sem ponto final.
  O título é a primeira frase que o público ouve: o fato mais forte logo no começo.
- Para o ouvido: frases curtas na ordem direta (sujeito, verbo, complemento), uma ideia por
  frase, sem parênteses, sem travessões, sem siglas pouco conhecidas, sem números longos
  (arredonde: "cerca de 1,2 mil" em vez de "1.187").
- SEM REDUNDÂNCIA: o título, a linha_fina, cada frase do resumo e cada ponto são narrados em
  sequência, então cada um traz um dado NOVO. Nunca repita a mesma informação com outras palavras
  (ex.: título "Prefeitura abre 300 vagas" e resumo "A prefeitura oferece 300 oportunidades" = errado).
- linha_fina: 1 frase de até 15 palavras que acrescenta um dado NOVO ao título (não repete).
- resumo: lide com 2 frases curtas (25 a 38 palavras no total) respondendo o quê, quem, onde, quando e como.
  Todo o texto é narrado no vídeo, que tem no máximo 58 segundos: seja enxuto.
- formato: escolha UM:
  "noticia" (fato simples), "o_que_se_sabe" (caso em andamento, polícia, acidente),
  "entenda" (assunto que precisa de contexto: lei, obra, aumento, polêmica),
  "servico" (vagas, inscrições, vacinação, mudanças no trânsito, prazos: o leitor precisa agir).
- pontos: 2 ou 3 tópicos curtos (até 10 palavras), adequados ao formato:
  o_que_se_sabe = fatos confirmados; entenda = contexto em ordem lógica;
  servico = passo a passo / quem pode / onde / até quando; noticia = principais dados.
  Lista vazia se não houver fatos suficientes.
- chapeu: editoria em MAIÚSCULAS, uma destas: {", ".join(EDITORIAS)}. É o tópico fixo que
  aparece no vídeo: escolha pelo ASSUNTO (notícia nacional de política = POLÍTICA, de saúde =
  SAÚDE). Use BRASIL só quando nenhuma outra servir.
- destaques: 2 ou 3 trechos de 1 a 3 palavras COPIADOS EXATAMENTE do titulo, linha_fina, resumo
  ou pontos, com a informação que mais importa (número, valor, prazo, lugar, órgão).
  Eles aparecem em outra fonte na legenda. Ex.: ["339 vagas", "até sexta", "Areia"].
- legenda: o post é SÓ a imagem da capa, então a legenda é onde o leitor se informa.
  3 blocos separados por linha em branco:
  1) o título reescrito de outro jeito, começando com 1 emoji da editoria;
  2) o lide completo em 3 a 4 frases (o quê, quem, onde, quando, como), linguagem simples,
     como quem conversa com o vizinho; os "pontos" serão listados pelo sistema logo depois;
  3) chamada final conforme o gatilho:
     utilidade -> "Salve este post e mande para quem precisa saber.";
     identificacao -> pergunta curta sobre a experiência do leitor ("Já passou por isso no seu bairro?");
     emocao -> convite para marcar alguém ("Marca alguém de CG que vai gostar de ver isso.");
     debate -> pergunta neutra pedindo opinião ("O que você acha da decisão?");
     status -> "Manda para aquele amigo que sempre quer saber primeiro."
  NÃO coloque hashtags, fontes ou "siga" na legenda: o sistema acrescenta.
- cidade: "Campina Grande", "João Pessoa", "Paraíba" ou "Brasil".
- hashtags: 5 a 7, sem '#', locais primeiro (ex.: campinagrande, joaopessoa, paraiba, pb).
- foto_busca: 2 a 4 palavras EM INGLÊS para buscar uma foto genérica do tema num banco de imagens,
  SÓ de objetos e cenas sem pessoas, sem fachadas, letreiros ou marcas que identifiquem outro
  lugar (ex.: "shopping bags", "empty office desk", "flooded street rain", "school classroom empty").
  Nunca nomes de pessoas ou lugares específicos.
- foto_local: lugar REAL e conhecido da cidade da notícia que tenha a ver com o fato, para buscar
  foto do próprio lugar SEM letreiros nem marcas (praças, parques, prédios públicos, ruas, orla,
  paisagens). Ex.: "Câmara Municipal de João Pessoa", "Parque do Povo Campina Grande",
  "Açude Velho Campina Grande", "Busto de Tamandaré João Pessoa". Nunca shopping, loja, banco,
  hotel ou fachada comercial (têm letreiro). "" se não houver.
- imagem_prompt: 1 frase em inglês descrevendo uma ILUSTRAÇÃO da cena da notícia (ambiente,
  objetos, luz, enquadramento), sem pessoas reconhecíveis, sem texto, letreiros, números ou
  logotipos, e que NÃO pareça foto do acontecimento (ex.: "empty city council chamber with
  wooden desks, warm afternoon light, wide angle").

POTENCIAL DE COMPARTILHAMENTO (o que faz notícia local viralizar)
- gatilho: o principal motivo para alguém enviar o post a outra pessoa, um destes:
  "utilidade" (o leitor precisa agir: vaga, prazo, interdição, vacina, golpe circulando),
  "identificacao" (todo mundo da cidade vive isso: trânsito, chuva, preço, bairro, São João),
  "emocao" (surpresa, orgulho local, solidariedade, conquista de alguém da cidade),
  "debate" (decisão pública que divide opiniões, sem tomar partido),
  "status" (quem compartilha parece bem informado: obra nova, empresa chegando, ranking).
- potencial: nota de 1 a 5 de quanto essa notícia tende a ser compartilhada por quem mora
  em CG/JP. 5 = afeta muita gente hoje ou mexe com o orgulho local; 1 = interessa a poucos.
  Seja honesto: nota alta para notícia sem impacto local estraga o portal.
- O título NUNCA promete o que o texto não entrega. Viralizar com ética: utilidade e clareza,
  não sensacionalismo.

TEMAS SENSÍVEIS
- risco = "skip" quando houver: suicídio; crime sexual; criança ou adolescente identificável;
  acusação não confirmada contra pessoa identificada; boato de saúde; ataque político
  em período eleitoral; conteúdo sem confirmação oficial sobre mortes.
- risco = "cuidado" para polícia, acidentes, mortes e tragédias confirmadas. Nesses casos:
  não cite nomes de vítimas nem de suspeitos (use "um homem de 32 anos", "o suspeito"),
  atribua à autoridade ("segundo a PM"), nada de detalhes chocantes, tom sóbrio.
- risco = "ok" para o resto.

Responda APENAS com um objeto JSON com as chaves:
skip (bool), motivo (string), risco ("ok"|"cuidado"|"skip"), formato, chapeu, titulo,
linha_fina, resumo, pontos (lista), destaques (lista), legenda, cidade, hashtags (lista), foto_busca,
foto_local, imagem_prompt, gatilho, potencial (número 1-5).
"""


def _extract_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start: end + 1])


def _gemini(prompt: str, system: str) -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY não configurada")
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "responseMimeType": "application/json"},
    }
    last = "nenhuma tentativa"
    prazo = time.monotonic() + 240  # no máximo 4 min por chamada
    for model in [m.strip() for m in GEMINI_MODEL.split(",") if m.strip()]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        for attempt in range(3):
            if time.monotonic() > prazo:
                raise RuntimeError(f"Gemini sem resposta a tempo ({last})")
            try:
                r = requests.post(url, json=body, headers={"x-goog-api-key": GEMINI_API_KEY},
                                  timeout=(10, 90))
            except requests.RequestException as e:
                last = f"{model}: {type(e).__name__}"
                time.sleep(5)
                continue
            if r.status_code == 429:  # limite do plano grátis: espera pouco e passa ao próximo modelo
                last = f"{model}: limite de uso (429)"
                espera = min(float(r.headers.get("Retry-After", 5) or 5), 15)
                time.sleep(espera)
                if "quota" in r.text.lower() or attempt >= 1:
                    break
                continue
            if r.status_code in (500, 502, 503, 504):  # sobrecarregado: espera e tenta de novo
                last = f"{model}: HTTP {r.status_code}"
                time.sleep(8 * (attempt + 1))
                continue
            if r.status_code == 404:  # modelo aposentado: tenta o próximo da lista
                last = f"{model}: indisponível"
                break
            if r.status_code >= 400:
                raise RuntimeError(f"Gemini {r.status_code}: {r.text[:300]}")
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
    raise RuntimeError(f"Gemini indisponível ({last})")


def _claude(prompt: str, system: str) -> str:
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY não configurada")
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={"model": CLAUDE_MODEL, "max_tokens": 1500, "system": system,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=90,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"Claude {r.status_code}: {r.text[:300]}")
    return r.json()["content"][0]["text"]


_SEM_SALDO = {"openai": False}


def _openai(prompt: str, system: str) -> str:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY não configurada")
    if _SEM_SALDO["openai"]:
        raise RuntimeError("OpenAI sem créditos")
    last = "nenhuma tentativa"
    for model in [m.strip() for m in OPENAI_MODEL.split(",") if m.strip()]:
        for _ in range(2):
            try:
                r = requests.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                    json={"model": model, "reasoning_effort": "low",
                          "response_format": {"type": "json_object"},
                          "messages": [{"role": "system", "content": system},
                                       {"role": "user", "content": prompt}]},
                    timeout=(10, 90))
            except requests.RequestException as e:
                last = f"{model}: {type(e).__name__}"
                time.sleep(3)
                continue
            if r.status_code == 429 and "insufficient_quota" in r.text:
                _SEM_SALDO["openai"] = True
                raise RuntimeError("OpenAI sem créditos (adicione saldo em platform.openai.com > Billing)")
            if r.status_code in (429, 500, 502, 503, 504):
                last = f"{model}: HTTP {r.status_code}"
                time.sleep(5)
                continue
            if r.status_code in (400, 404) and "model" in r.text.lower():
                last = f"{model}: indisponível"
                break
            if r.status_code >= 400:
                raise RuntimeError(f"OpenAI {r.status_code}: {r.text[:300]}")
            return r.json()["choices"][0]["message"]["content"]
    raise RuntimeError(f"OpenAI indisponível ({last})")


def _provedores() -> list:
    """Ordem de tentativa: o escolhido primeiro, os outros configurados de reserva."""
    disp = {"openai": (OPENAI_API_KEY, _openai), "gemini": (GEMINI_API_KEY, _gemini),
            "anthropic": (ANTHROPIC_API_KEY, _claude)}
    ordem = [LLM_PROVIDER] + [p for p in ("openai", "gemini", "anthropic") if p != LLM_PROVIDER]
    return [(p, disp[p][1]) for p in ordem if p in disp and disp[p][0]]


def generate(prompt: str, system: str = None) -> str:
    sysmsg = system or SYSTEM
    erros = []
    for nome, fn in _provedores():
        try:
            return fn(prompt, sysmsg)
        except Exception as e:
            erros.append(f"{nome}: {str(e)[:100]}")
    raise RuntimeError("; ".join(erros) or "nenhuma IA configurada")


# ------------------------------------------------------------ agente reescritor
REESCRITOR = """Você é o revisor de originalidade do portal. Recebe um post em JSON e as
manchetes originais de outros veículos. Reescreva titulo, linha_fina, resumo, pontos e legenda
para que fiquem TOTALMENTE diferentes das manchetes originais: mude a ordem das informações,
troque palavras por sinônimos naturais, mude a estrutura das frases (ex.: voz ativa <-> passiva,
começar pelo dado mais útil ao leitor). Mantenha exatamente os mesmos fatos, sem acrescentar nada,
e as mesmas regras de estilo (título no presente, até 95 caracteres, sem ponto final).
O título precisa continuar ESPECÍFICO e natural: diga quem, o quê e onde (cidade ou órgão), como
um jornalista experiente escreveria. Nunca troque nomes próprios, cargos, números ou lugares por
termos genéricos ("no estado", "órgão", "festejos") e nunca crie expressões redundantes
("festejos festivos"). Prefira mudar a estrutura da frase a trocar palavras exatas.
Trechos que se repetem e precisam mudar: {trechos}
Responda APENAS com o JSON completo do post, com as mesmas chaves."""


def _palavras(t: str) -> list:
    return re.findall(r"[a-zà-ÿ0-9]+", t.lower())


def _ngramas(texto: str, n: int) -> set:
    w = _palavras(texto)
    return {" ".join(w[i:i + n]) for i in range(len(w) - n + 1)}


def trechos_repetidos(card: dict, cluster, tolerancia=2) -> list:
    """O que ainda está copiado da fonte. Regras (pensadas para não barrar nomes próprios):
    - manchete: nenhuma sequência de 5 palavras igual à manchete de outro veículo;
    - resto do texto: no máximo `tolerancia` sequências de 6 palavras iguais às fontes
      (nomes de órgãos e eventos, como "Corpo de Bombeiros Militar da Paraíba", são inevitáveis)."""
    titulos = set()
    for it in cluster.items:
        titulos |= _ngramas(it.title, 5)
    achados = [g for g in _ngramas(card.get("titulo", ""), 5) if g in titulos]
    fontes = set()
    for t in [it.title + " " + it.summary for it in cluster.items] + [getattr(cluster, "corpo", "") or ""]:
        fontes |= _ngramas(t, 6)
    nosso = " ".join([card.get("linha_fina", ""), card.get("resumo", ""),
                      " ".join(card.get("pontos", [])), card.get("legenda", "")])
    corpo = [g for g in _ngramas(nosso, 6) if g in fontes]
    if len(corpo) > tolerancia:
        achados += corpo
    return sorted(set(achados))


def originalizar(card: dict, cluster, tentativas=2) -> dict:
    for _ in range(tentativas):
        rep = trechos_repetidos(card, cluster)
        if not rep:
            card["original"] = True
            return card
        prompt = ("Manchetes originais:\n" + "\n".join(f"- {i.title}" for i in cluster.items[:8])
                  + "\n\nPost atual:\n" + json.dumps(card, ensure_ascii=False))
        novo = _extract_json(generate(prompt, REESCRITOR.format(trechos="; ".join(rep[:12]))))
        for k in ("titulo", "linha_fina", "resumo", "pontos", "legenda"):
            if novo.get(k):
                card[k] = novo[k]
        card = validate(card)
    card["original"] = not trechos_repetidos(card, cluster)
    return card


_robots_cache = {}


def _robots_ok(url: str) -> bool:
    """Respeita o robots.txt do site antes de ler a matéria completa."""
    from urllib.parse import urlsplit
    from urllib.robotparser import RobotFileParser

    base = "{0.scheme}://{0.netloc}".format(urlsplit(url))
    if base not in _robots_cache:
        rp = RobotFileParser()
        try:
            r = requests.get(base + "/robots.txt", timeout=(5, 8),
                             headers={"User-Agent": "PortalNoticiasBot/1.0"})
            rp.parse(r.text.splitlines() if r.status_code == 200 else [])
        except requests.RequestException:
            rp.parse([])
        _robots_cache[base] = rp
    return _robots_cache[base].can_fetch("PortalNoticiasBot", url)


def texto_completo(cluster, limite=1800, tentativas=3) -> str:
    """Lê o corpo de UMA matéria (link direto, não do Google News) com o Trafilatura,
    só para dar mais fatos à IA. O texto nunca é publicado nem copiado.
    Tenta no máximo 3 links, com tempo curto, e guarda o resultado no próprio cluster."""
    if getattr(cluster, "corpo", None) is not None:
        return cluster.corpo
    cluster.corpo = ""
    try:
        import trafilatura
    except ImportError:
        return ""
    feitas = 0
    for it in cluster.items:
        if feitas >= tentativas:
            break
        if not it.link or "news.google.com" in it.link or not _robots_ok(it.link):
            continue
        feitas += 1
        try:
            r = requests.get(it.link, timeout=(5, 12), headers={"User-Agent": "PortalNoticiasBot/1.0"})
            if r.status_code != 200 or len(r.content) > 3_000_000:
                continue
            txt = trafilatura.extract(r.text, include_comments=False, include_tables=False) or ""
            if len(txt) > 300:
                cluster.corpo = " ".join(txt.split())[:limite]
                return cluster.corpo
        except Exception:
            continue
    return ""


def build_prompt(cluster) -> str:
    lines = []
    for it in cluster.items[:8]:
        lines.append(f"- {it.title}  [{it.source}]")
        if it.summary:
            lines.append(f"  resumo: {it.summary[:400]}")
    corpo = texto_completo(cluster)
    if corpo:
        lines.append("\nTrecho da matéria (apenas para apuração, NÃO copie frases):\n" + corpo)
    return "Material recebido:\n" + "\n".join(lines)


def validate(card: dict) -> dict:
    """Confere o que a IA devolveu; lança ValueError se não servir para publicar."""
    if card.get("skip") or card.get("risco") == "skip":
        card["skip"] = True
        return card
    for key in ("titulo", "resumo", "legenda", "chapeu"):
        if not str(card.get(key, "")).strip():
            raise ValueError(f"faltou o campo {key}")
    titulo = " ".join(card["titulo"].split()).rstrip(".!")
    if len(titulo) > 110:
        raise ValueError("título longo demais")
    card["titulo"] = titulo
    card["chapeu"] = card["chapeu"].strip().upper()
    if card["chapeu"] not in EDITORIAS:
        card["chapeu"] = ("CIDADE" if card.get("cidade") in ("Campina Grande", "João Pessoa")
                          else "BRASIL" if card.get("cidade") == "Brasil" else "PARAÍBA")
    card["formato"] = card.get("formato") if card.get("formato") in FORMATOS else "noticia"
    card["linha_fina"] = " ".join(str(card.get("linha_fina", "")).split())
    card["gatilho"] = card.get("gatilho") if card.get("gatilho") in GATILHOS else "utilidade"
    try:
        card["potencial"] = max(1, min(5, int(card.get("potencial", 3))))
    except (TypeError, ValueError):
        card["potencial"] = 3
    card["pontos"] = [" ".join(str(p).split()) for p in card.get("pontos", []) if str(p).strip()][:3]
    # destaques só valem se estiverem mesmo no texto narrado (senão a legenda não acha)
    narrado = " ".join([card["titulo"], card["linha_fina"], str(card.get("resumo", "")), " ".join(card["pontos"])]).lower()
    card["destaques"] = [" ".join(str(d).split()) for d in (card.get("destaques") or [])
                         if str(d).strip() and " ".join(str(d).split()).lower() in narrado][:3]
    tags = []
    for h in card.get("hashtags", []):
        h = re.sub(r"[^\wÀ-ÿ]", "", str(h).lstrip("#"))
        if h and h.lower() not in [t.lower() for t in tags]:
            tags.append(h)
    card["hashtags"] = tags[:7]
    if card.get("risco") not in ("ok", "cuidado"):
        card["risco"] = "cuidado"
    return card


def make_card(cluster) -> dict:
    card = validate(_extract_json(generate(build_prompt(cluster))))
    if not card.get("skip"):
        card = originalizar(card, cluster)
        if not card.get("original"):
            card["skip"], card["motivo"] = True, "texto ainda parecido com a fonte"
    if not card.get("skip") and SENSITIVE_MODE == "skip" and card["risco"] == "cuidado":
        card["skip"], card["motivo"] = True, "tema sensível (SENSITIVE_MODE=skip)"
    return card


# ------------------------------------------------------------ leitura da foto original
VER_FOTO = """Você ajuda a escolher uma foto de banco de imagens livre para ilustrar uma notícia.
Descreva a foto recebida (que NÃO será publicada) para achar outra parecida. Responda só JSON:
{"lugar": nome do lugar reconhecível, se houver (ex.: "Parque do Povo, Campina Grande"), senão "",
 "cena_en": 1 frase em inglês descrevendo a cena para recriá-la como ilustração (ambiente, objetos,
            luz), SEM pessoas reconhecíveis, SEM textos, letreiros ou logotipos,
 "busca_lugar": busca curta para o Wikimedia Commons com o nome do lugar, senão "",
 "busca_en": 2 a 5 palavras em inglês descrevendo a cena SEM pessoas identificáveis
            (ex.: "city council chamber", "christmas lights square night"),
 "tem_pessoas_em_destaque": true ou false}"""


def ver_imagem(img: bytes, mime: str, contexto: str) -> dict:
    """Descreve uma imagem com a IA disponível (GPT ou Gemini). A imagem só é lida, nunca publicada."""
    b64 = base64.b64encode(img).decode()
    erros = []
    if OPENAI_API_KEY:
        try:
            r = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                json={"model": OPENAI_MODEL.split(",")[0].strip(), "reasoning_effort": "low",
                      "response_format": {"type": "json_object"},
                      "messages": [{"role": "system", "content": VER_FOTO},
                                   {"role": "user", "content": [
                                       {"type": "text", "text": contexto},
                                       {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}]}]},
                timeout=(10, 60))
            r.raise_for_status()
            return _extract_json(r.json()["choices"][0]["message"]["content"])
        except Exception as e:
            erros.append(f"openai: {type(e).__name__}")
    if GEMINI_API_KEY:
        for model in [m.strip() for m in GEMINI_MODEL.split(",") if m.strip()]:
            try:
                r = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                    headers={"x-goog-api-key": GEMINI_API_KEY},
                    json={"systemInstruction": {"parts": [{"text": VER_FOTO}]},
                          "contents": [{"role": "user", "parts": [
                              {"text": contexto}, {"inline_data": {"mime_type": mime, "data": b64}}]}],
                          "generationConfig": {"responseMimeType": "application/json"}},
                    timeout=(10, 45))
                if r.status_code == 404:
                    continue
                r.raise_for_status()
                return _extract_json(r.json()["candidates"][0]["content"]["parts"][0]["text"])
            except Exception as e:
                erros.append(f"gemini {model}: {type(e).__name__}")
                continue  # tenta o próximo modelo
    raise RuntimeError("; ".join(erros) or "nenhuma IA configurada")
