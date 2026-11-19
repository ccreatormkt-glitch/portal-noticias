"""Coleta manchetes de Campina Grande, João Pessoa e Paraíba e agrupa por assunto.

Fontes: buscas do Google News (edição Brasil) + RSS direto dos portais e órgãos
públicos. Para incluir ou tirar uma fonte, edite FEEDS. Rode
`python main.py check-feeds` para ver quais estão respondendo.
"""
import hashlib
import html
import re
import time
import unicodedata
from dataclasses import dataclass, field
from urllib.parse import quote_plus

import feedparser
import requests

from config import MAX_STORY_AGE_HOURS

UA = "Mozilla/5.0 (compatible; PortalNoticiasBot/1.0; resumo de manchetes)"


def gnews(query: str) -> str:
    return ("https://news.google.com/rss/search?q=" + quote_plus(query + " when:1d")
            + "&hl=pt-BR&gl=BR&ceid=BR:pt-419")


# nome -> url. Falha em uma fonte nunca derruba a execução, e o robots.txt de cada site
# é respeitado na hora (site que pede para robôs não entrarem é pulado automaticamente).
# Lista do Arthur (19/11/2026). Fora de propósito: WSCom e Portal T5 (robots.txt proíbe robôs).
# TVs e rádios entram pelos portais delas (g1 = TV Cabo Branco/TV Paraíba, Portal Correio = TV Correio).
FEEDS = {
    # buscas no Google Notícias (cobrem também quem não tem RSS)
    "gn_campina": gnews('"Campina Grande"'),
    "gn_joaopessoa": gnews('"João Pessoa"'),
    "gn_paraiba": gnews("Paraíba"),
    "gn_sertao": gnews("Patos OR Sousa OR Cajazeiras Paraíba"),
    # sites da lista sem RSS público (verificado em 19/11/2026): entram pela busca filtrada por site
    "gn_blogs_cg": gnews("site:blogdomarciorangel.com.br OR site:blogdorenatodiniz.com.br OR site:paraibao.com.br"),
    "gn_sertao_sites": gnews("site:patosonline.com OR site:portalpatos.com OR site:pabhlonoticias.com "
                             "OR site:portalczn.com.br OR site:sertaodaparaiba.com.br"),
    "gn_oficiais": gnews("site:pm.pb.gov.br OR site:paraiba.pb.gov.br OR site:auniao.pb.gov.br "
                         "OR (PRF Paraíba)"),
    "gn_tv": gnews('"TV Tambaú" OR "TV Arapuan" OR "CBN João Pessoa" OR "CBN Campina Grande"'),
    # 1. portais estaduais e Grande João Pessoa
    "g1_pb": "https://g1.globo.com/rss/g1/pb/paraiba/",
    # Brasil: 1 a cada 3 posts (e reserva quando não houver nada novo da Paraíba). Do G1 só entram
    # as editorias nacionais (política, economia, saúde...); as manchetes principais do Google
    # Notícias Brasil servem para medir a relevância (o mesmo fato em vários veículos).
    "g1_brasil": "https://g1.globo.com/rss/g1/",
    "gn_brasil_top": "https://news.google.com/rss?hl=pt-BR&gl=BR&ceid=BR:pt-419",
    "portalcorreio": "https://portalcorreio.com.br/feed/",
    "clickpb": "https://www.clickpb.com.br/feed/",
    "jornaldaparaiba": "https://jornaldaparaiba.com.br/feed",
    "maispb": "https://www.maispb.com.br/feed",
    "pbagora": "https://www.pbagora.com.br/rss",  # verificado: /feed/ é a página inicial
    "polemicaparaiba": "https://www.polemicaparaiba.com.br/feed/",
    "fonte83": "https://fonte83.com.br/feed/",
    "correioparaibano": "https://correioparaibano.com/feed/",
    "rotapb": "https://rotapb.com.br/feed/",
    # 2. Campina Grande e Agreste
    "paraibaonline": "https://paraibaonline.com.br/feed/",
    "seligapb": "https://seligapb.com.br/feed/",
    "pagina1pb": "https://pagina1pb.com.br/feed/",
    # 3. Sertão
    "diariodosertao": "https://www.diariodosertao.com.br/feed/",
    # 4. canais oficiais e segurança pública
    "gn_prefeituras": gnews("site:campinagrande.pb.gov.br OR site:joaopessoa.pb.gov.br"),
    # 6. agregador
}

# nome amigável usado no crédito interno quando o item vem de RSS direto
FEED_SOURCE_NAME = {
    "g1_pb": "g1 Paraíba", "g1_brasil": "g1", "paraibaonline": "ParaibaOnline", "portalcorreio": "Portal Correio",
    "clickpb": "ClickPB", "pbagora": "PB Agora", "jornaldaparaiba": "Jornal da Paraíba",
    "maispb": "MaisPB", "polemicaparaiba": "Polêmica Paraíba", "fonte83": "Fonte 83",
    "correioparaibano": "Correio Paraibano", "rotapb": "RotaPB", "marciorangel": "Blog do Márcio Rangel",
    "seligapb": "Se Liga PB", "pagina1pb": "Página 1 PB", "renatodiniz": "Blog do Renato Diniz", "portalpatos": "Portal Patos", "pabhlo": "Pabhlo Rhuan Notícias",
    "diariodosertao": "Diário do Sertão", "portalczn": "Portal CZN", "sertaodaparaiba": "Portal Sertão da Paraíba", "prf_pb": "PRF Paraíba", "governo_pb": "Governo da Paraíba", "pref_cg": "Prefeitura de Campina Grande",
    "pref_jp": "Prefeitura de João Pessoa", "paraibao": "Paraibão",
}

# veículos grandes ou oficiais: uma notícia só deles já é aceita
TRUSTED = ["g1", "jornal da paraiba", "portal correio", "clickpb", "paraibaonline",
           "paraiba online", "maispb", "pb agora", "tv cabo branco", "tv paraiba",
           "prefeitura", "governo da paraiba", "agencia brasil", "cbn", "camara municipal",
           "policia civil", "policia militar", "tribunal", "ministerio publico", "detran",
           "prf", "a uniao", "diario do sertao"]

# palavras que indicam notícia local (dão prioridade)
LOCAL_TERMS = [
    # cidades, apelidos e gentílicos
    "campina grande", "joao pessoa", "paraiba", "paraibano", "paraibana", "pessoense", "campinense",
    "jampa", "rainha da borborema", " cg ", " jp ", " pb ", "(pb)", "-pb",
    # região metropolitana e vizinhas
    "cabedelo", "bayeux", "santa rita", "conde", "lucena", "queimadas", "lagoa seca", "puxinana",
    "massaranduba", "boa vista", "fagundes", "esperanca", "areia", "guarabira", "patos", "sousa",
    "cajazeiras", "monteiro", "borborema", "brejo", "cariri", "sertao", "curimatau",
    # bairros e lugares muito citados
    "mangabeira", "manaira", "tambau", "cabo branco", "bancarios", "valentina", "cristo redentor",
    "jose americo", "torre", "epitacio", "altiplano", "bessa", "catole", "malvinas", "bodocongo",
    "liberdade", "jose pinheiro", "prata", "acude velho", "parque do povo", "alto branco",
    # instituições locais
    "uepb", "ufcg", "ufpb", "ifpb", "alpb", "tjpb", "mppb", "detran-pb", "cagepa", "energisa",
    "sttp", "semob", "treze", "campinense clube", "botafogo-pb",
]

# temas que o portal NUNCA publica (filtro fixo, independe da IA): crimes sexuais, abuso
# de crianças e adolescentes, suicídio e automutilação
TEMA_PROIBIDO = re.compile(
    r"estupr|abuso sexual|abusad[ao] sexual|assedio sexual|assédio sexual|importuna[cç][aã]o sexual|"
    r"pornografia|pedofil|explora[cç][aã]o sexual|infantojuvenil|alicia|crime sexual|"
    r"suic[ií]d|automutila|se matou|tirou a pr[oó]pria vida",
    re.IGNORECASE)

# itens que não são notícia (programação, publicidade, colunas de opinião, passatempos)
BLOQUEAR = re.compile(
    r"\bao vivo\b|publieditorial|publicidade|patrocinad|especial publicit|informe publicit|"
    r"hor[oó]scopo|\bcoluna\b|\bopini[aã]o\b|\bpodcast\b|\bassista\b|\bpromo[cç][aã]o\b|"
    r"cupom|\bsorteio\b|^\s*v[ií]deo\s*:|\bao vivo\b|clickfm|cbn\s",
    re.IGNORECASE)

STOP = set("""a o as os um uma uns umas de da do das dos em na no nas nos para pra por pelo pela
pelos pelas com sem sob sobre ao aos e ou que se sua seu suas seus ja mais menos apos ate
entre como quando onde nesta neste nessa nesse desta deste esta este essa esse isso isto
diz dizem veja confira video foto fotos hoje ontem amanha sera serao tem foi sao ser vai
apos durante contra""".split())


def fold(text: str) -> str:
    t = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def stems_of(text: str) -> set:
    toks = re.findall(r"[a-z0-9]+", fold(text))
    return {t[:6] for t in toks if len(t) > 2 and t not in STOP}


def strip_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    return " ".join(html.unescape(s).split())


@dataclass
class Item:
    title: str
    source: str
    link: str
    published: float
    feed: str
    rank: int
    summary: str = ""


@dataclass
class Cluster:
    items: list = field(default_factory=list)
    stems: set = field(default_factory=set)
    score: float = 0.0

    @property
    def sources(self):
        seen, out = set(), []
        for it in self.items:
            key = fold(it.source)
            if it.source and key not in seen:
                seen.add(key)
                out.append(it.source)
        return out

    @property
    def n_sources(self):
        return len(self.sources)

    @property
    def trusted(self):
        return any(t in fold(s) for s in self.sources for t in TRUSTED)

    @property
    def is_local(self):
        text = " " + fold(" ".join(i.title + " " + i.summary for i in self.items)) + " "
        return any(t in text for t in LOCAL_TERMS)

    @property
    def rep(self):
        return self.items[0]

    @property
    def fingerprint(self):
        return hashlib.sha1(" ".join(sorted(self.stems)[:12]).encode()).hexdigest()[:16]


_robots = {}


def _robots_ok(url: str) -> bool:
    """Respeita o robots.txt do site do feed (Google Notícias não precisa)."""
    from urllib.parse import urlsplit
    from urllib.robotparser import RobotFileParser

    if "news.google.com" in url:
        return True
    base = "{0.scheme}://{0.netloc}".format(urlsplit(url))
    if base not in _robots:
        rp = RobotFileParser()
        try:
            r = requests.get(base + "/robots.txt", headers={"User-Agent": UA}, timeout=(5, 8))
            rp.parse(r.text.splitlines() if r.status_code == 200 else [])
        except requests.RequestException:
            rp.parse([])
        _robots[base] = rp
    return _robots[base].can_fetch("PortalNoticiasBot", url)


def _get(url):
    if not _robots_ok(url):
        raise PermissionError("robots.txt pede para robôs não acessarem")
    r = requests.get(url, headers={"User-Agent": UA}, timeout=(6, 15))
    r.raise_for_status()
    feed = feedparser.parse(r.content)
    if not feed.entries:
        raise ValueError("sem notícias (não é um feed RSS)")
    return feed


def _ler(name, url):
    try:
        return name, _get(url), None
    except Exception as e:  # uma fonte ruim não para o resto
        return name, None, f"{type(e).__name__}: {str(e)[:60]}"


def fetch_items(verbose=False) -> list:
    from concurrent.futures import ThreadPoolExecutor

    items = []
    diretos = [(k, v) for k, v in FEEDS.items() if not k.startswith("gn_")]
    with ThreadPoolExecutor(max_workers=8) as ex:
        resultados = list(ex.map(lambda kv: _ler(*kv), diretos))
    # Google Notícias: uma busca por vez, com pausa (muitas juntas dão "429 Too Many Requests")
    for k, v in FEEDS.items():
        if k.startswith("gn_"):
            r = _ler(k, v)
            if r[2] and "429" in r[2]:
                time.sleep(8)
                r = _ler(k, v)
            resultados.append(r)
            time.sleep(1.5)
    for name, feed, erro in resultados:
        if erro:
            print(f"[fontes] {name} ignorada ({erro})")
            continue
        n = 0
        for rank, e in enumerate(feed.entries[:40]):
            title = strip_html(e.get("title", ""))
            src = (e.get("source") or {}).get("title", "") or FEED_SOURCE_NAME.get(name, "")
            if name.startswith("gn_"):
                if title.endswith(f" - {src}"):
                    title = title[: -len(src) - 3]
                elif " - " in title and not src:
                    title, src = title.rsplit(" - ", 1)
            ts_struct = e.get("published_parsed") or e.get("updated_parsed")
            ts = time.mktime(ts_struct) if ts_struct else time.time()
            summary = "" if name.startswith("gn_") else strip_html(e.get("summary", ""))[:500]
            if title and not BLOQUEAR.search(title) and not TEMA_PROIBIDO.search(title + " " + summary):
                items.append(Item(title, src.strip(), e.get("link", ""), ts, name, rank, summary))
                n += 1
        if verbose:
            print(f"[fontes] {name}: {n} itens")
    return items


def cluster_items(items: list) -> list:
    now = time.time()
    items = [i for i in items if now - i.published < MAX_STORY_AGE_HOURS * 3600]
    items.sort(key=lambda i: (i.rank, -i.published))

    clusters = []
    for it in items:
        s = stems_of(it.title)
        if len(s) < 3:
            continue
        best, best_sim = None, 0.0
        for c in clusters:
            inter = len(s & c.stems)
            sim = inter / len(s | c.stems)
            if (inter >= 4 or sim >= 0.34) and sim > best_sim:
                best, best_sim = c, sim
        if best:
            best.items.append(it)
            best.stems |= s
        else:
            clusters.append(Cluster(items=[it], stems=set(s)))

    for c in clusters:
        freshest = max(i.published for i in c.items)
        age_h = (now - freshest) / 3600
        fresh = 4 if age_h < 2 else 2 if age_h < 6 else 0
        best_rank = min(i.rank for i in c.items)
        c.score = (c.n_sources * 3 + (5 if c.is_local else -4) + fresh
                   + max(0, 4 - best_rank / 5) + (1 if c.trusted else 0))
    clusters.sort(key=lambda c: c.score, reverse=True)
    return clusters


def build_clusters() -> list:
    return cluster_items(fetch_items())


# nomes muito comuns nas manchetes locais: não servem para dizer que duas notícias são a mesma
NOMES_COMUNS = set("""joao pessoa campina grande paraiba brasil camara prefeitura governo policia
federal civil militar estado municipal estadual justica tribunal ministerio publico nacional
cidade secretaria saude educacao assembleia legislativa senado congresso presidente vereador
deputado prefeito governador operacao copa campeonato natal saiba veja confira entenda
homem mulher jovem idoso crianca suspeito motorista moradores unanimidade apos durante""".split())


def nomes_proprios(texto: str) -> set:
    """Palavras com inicial maiúscula: nomes de pessoas, lugares, eventos (sem os muito comuns)."""
    palavras = re.findall(r"[A-Za-zÀ-ÿ][\wÀ-ÿ'-]*", texto or "")
    out = set()
    for i, p in enumerate(palavras):
        if p[0].isupper() and len(p) >= 4:
            f = fold(p)
            if f not in NOMES_COMUNS:
                out.add(f)
    return out


def mesma_historia(titulo_a: str, titulo_b: str) -> bool:
    """Duas manchetes sobre o mesmo fato, mesmo escritas de jeitos diferentes por portais diferentes
    (ex.: "Corujinha é eleito presidente da CMJP" e "Câmara escolhe João Corujinha para presidir")."""
    sa, sb = stems_of(titulo_a), stems_of(titulo_b)
    jac = len(sa & sb) / len(sa | sb) if sa and sb else 0.0
    if jac >= 0.45:
        return True
    return bool(nomes_proprios(titulo_a) & nomes_proprios(titulo_b)) and jac >= 0.12


# primeira parte do endereço das matérias do G1 que são regionais (sigla do estado)
UFS = set("ac al am ap ba ce df es go ma mg ms mt pa pb pe pi pr rj rn ro rr rs sc se sp to".split())


def g1_nacional(item) -> bool:
    """Matéria do G1 de editoria nacional (política, economia, saúde...), não de outro estado."""
    from urllib.parse import urlsplit
    if item.feed != "g1_brasil":
        return False
    partes = [x for x in urlsplit(item.link or "").path.split("/") if x]
    return bool(partes) and partes[0] not in UFS
