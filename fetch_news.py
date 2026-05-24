#!/usr/bin/env python3
"""fetch_news.py — otimismo.pt | tradução EN→PT + og:image + máx 3 por fonte"""

import json, time, re, hashlib, ssl
from datetime import datetime, timezone
from urllib.request import urlopen, Request
from xml.etree import ElementTree as ET

try:
    import requests
    from bs4 import BeautifulSoup
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from deep_translator import GoogleTranslator
    _translator = GoogleTranslator(source='auto', target='pt')
    HAS_TRANSLATOR = True
except ImportError:
    HAS_TRANSLATOR = False
    print("⚠️  deep_translator não disponível — tradução desativada")

OUTPUT_FILE    = "noticias.json"
MAX_NEWS       = 30
MIN_SCORE      = 0.60
FETCH_TIMEOUT  = 12
MAX_PER_SOURCE = 3

FEEDS = [
    ("https://feeds.feedburner.com/PublicoCienciaETecnologia", "Público",                "ciencia",    False),
    ("https://www.publico.pt/api/rss/ambiente",                "Público",                "ambiente",   False),
    ("https://www.publico.pt/api/rss/economia",                "Público",                "economia",   False),
    ("https://observador.pt/tag/tecnologia/feed/",             "Observador",             "tecnologia", False),
    ("https://observador.pt/tag/ciencia/feed/",                "Observador",             "ciencia",    False),
    ("https://observador.pt/tag/saude/feed/",                  "Observador",             "saude",      False),
    ("https://observador.pt/seccao/desporto/feed/",            "Observador",             "desporto",   False),
    ("https://www.jornaldenegocios.pt/rss",                    "Jornal de Negócios",     "economia",   False),
    ("https://www.tsf.pt/rss/",                                "TSF",                    "sociedade",  False),
    ("https://www.rtp.pt/noticias/rss/desporto",               "RTP",                    "desporto",   False),
    ("https://eco.pt/feed/",                                   "ECO",                    "ambiente",   False),
    ("https://www.dn.pt/rss/",                                 "Diário de Notícias",     "sociedade",  False),
    ("https://shifter.sapo.pt/feed/",                          "Shifter",                "tecnologia", False),
    ("https://www.goodnewsnetwork.org/feed/",                  "Good News Network",      "sociedade",  True),
    ("https://www.positive.news/feed/",                        "Positive News",          "sociedade",  True),
    ("http://feeds.bbci.co.uk/news/science_and_environment/rss.xml", "BBC News",         "ciencia",    True),
    ("http://feeds.bbci.co.uk/news/health/rss.xml",            "BBC News",               "saude",      True),
    ("https://feeds.reuters.com/reuters/scienceNews",          "Reuters",                "ciencia",    True),
    ("https://www.sciencedaily.com/rss/top/science.xml",       "ScienceDaily",           "ciencia",    True),
    ("https://reasonstobecheerful.world/feed/",                "Reasons to be Cheerful", "sociedade",  True),
]

POSITIVE_PT = [
    "recorde","conquista","vitória","primeiro","pioneiro","sucesso","inovação",
    "descoberta","cura","avanço","melhoria","crescimento","renovável","sustentável",
    "positivo","esperança","histórico","prémio","galardão","campeão","celebração",
    "progresso","transformação","revolução","recuperação","protegido","salvo",
    "tratamento","vacina","solução","investimento","criação","emprego","lançamento",
    "aprovado","aprovação","medalha","ouro","prata","bronze","parceria","acordo",
    "colaboração","doação","voluntário","solidariedade","energia limpa","biodiversidade",
    "preservação","restauração","conservação","habitat","espécie","investigação",
]
POSITIVE_EN = [
    "record","breakthrough","discover","cure","advance","improvement","growth",
    "renewable","sustainable","positive","hope","historic","prize","award",
    "champion","celebrate","progress","transform","recovery","protected","save",
    "treatment","vaccine","solution","investment","create","launch","approve",
    "medal","gold","silver","bronze","partnership","agreement","collaborate",
    "donate","volunteer","solidarity","clean energy","biodiversity","preserve",
    "restore","conservation","habitat","species","research","study","nature",
    "science","first","pioneer","success","innovate","revive","green","solar",
    "wind","electric","zero emission","carbon neutral","thriving","flourish",
]
NEGATIVE_KW = [
    "morte","morto","assassin","homicídio","acidente","crise","colapso","falência",
    "desastre","tragédia","conflito","guerra","ataque","terrorismo","corrupção",
    "escândalo","fraud","crime","roubo","violência","abuso","vitima","vítima",
    "dead","death","kill","murder","crash","disaster","collapse","bankrupt",
    "tragedy","conflict","war","attack","terrorism","corruption","scandal",
    "fraud","crime","robbery","violence","abuse","victim","crisis","fail",
]
CATEGORY_KEYWORDS = {
    "ciencia":    ["ciência","científ","investigação","descoberta","estudo","pesquisa",
                   "nature","science","research","discover","study","laboratory"],
    "tecnologia": ["tecnologia","tech","digital","inteligência artificial","ia","ai",
                   "robot","startup","software","hardware","app","internet","5g","drone"],
    "ambiente":   ["ambiente","clima","carbono","energia","renovável","solar","vento",
                   "oceano","floresta","biodiversidade","espécie","ecosystem","climate",
                   "renewable","green","sustainable","nature","wildlife","ocean","forest"],
    "saude":      ["saúde","saude","médico","hospital","vacina","doença","cura","tratamento",
                   "cancer","vírus","medicina","health","vaccine","cure","treatment","medical"],
    "economia":   ["economia","económic","pib","emprego","investimento","mercado","empresa",
                   "exportação","crescimento","economic","gdp","employment","investment","market"],
    "desporto":   ["desporto","futebol","basquete","natação","atletismo","olimp","campeão",
                   "sport","football","soccer","basketball","swimming","champion","gold medal"],
    "cultura":    ["cultura","arte","música","cinema","teatro","literatura","museu","festival",
                   "culture","art","music","film","theater","literature","museum","festival"],
    "sociedade":  ["sociedade","comunidade","educação","escola","família","voluntário","solidar",
                   "society","community","education","school","family","volunteer","solidar"],
}

def translate_to_pt(text):
    if not HAS_TRANSLATOR or not text or not text.strip():
        return text
    try:
        result = _translator.translate(text[:4500])
        return result if result else text
    except Exception as e:
        print(f"  [tradução] erro: {e}")
        return text

def fetch_og_image(url):
    if not HAS_REQUESTS or not url or 'news.google.com' in url:
        return None
    try:
        resp = requests.get(url, timeout=6, headers={'User-Agent': 'Mozilla/5.0'})
        if not resp.ok:
            return None
        soup = BeautifulSoup(resp.text, 'html.parser')
        for attr in [('property','og:image'), ('name','twitter:image'),
                     ('property','twitter:image'), ('name','og:image')]:
            tag = soup.find('meta', attrs={attr[0]: attr[1]})
            if tag and tag.get('content'):
                return tag['content']
    except Exception:
        pass
    return None

def find_image(item, article_url):
    ns = {"media": "http://search.yahoo.com/mrss/"}
    for tag in ["media:thumbnail", "media:content"]:
        el = item.find(tag, ns)
        if el is not None:
            url = el.get("url")
            if url:
                return url
    enc = item.find("enclosure")
    if enc is not None and "image" in enc.get("type", ""):
        return enc.get("url")
    desc = item.findtext("description") or ""
    m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', desc)
    if m:
        src = m.group(1)
        if src.startswith('http'):
            return src
    return fetch_og_image(article_url)

def make_id(url): return hashlib.md5(url.encode()).hexdigest()[:8]
def strip_html(t): return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', t or '')).strip()

def detect_category(title, summary, default_cat):
    text = (title + " " + summary).lower()
    best, best_n = default_cat, 0
    for cat, kws in CATEGORY_KEYWORDS.items():
        n = sum(1 for kw in kws if kw in text)
        if n > best_n:
            best_n, best = n, cat
    return best

def score_article(title, summary, is_english):
    text = (title + " " + summary).lower()
    pos_kw = POSITIVE_EN if is_english else POSITIVE_PT
    pos = sum(1 for kw in pos_kw if kw in text)
    neg = sum(1 for kw in NEGATIVE_KW if kw in text)
    base = 0.40 - (neg * 0.05) if neg > 0 else 0.70
    return round(min(base + min(pos * 0.03, 0.28), 0.99), 2)

def fetch_feed(url, source, default_cat, is_english):
    articles = []
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = Request(url, headers={"User-Agent": "otimismo.pt-bot/1.0"})
        with urlopen(req, timeout=FETCH_TIMEOUT, context=ctx) as r:
            raw = r.read()
        root = ET.fromstring(raw)
    except Exception as e:
        print(f"  ⚠️  Erro: {source} — {e}")
        return articles

    items = root.findall(".//item")
    if not items:
        items = root.findall(".//{http://www.w3.org/2005/Atom}entry")

    for item in items[:10]:
        title = strip_html(
            item.findtext("title") or
            item.findtext("{http://www.w3.org/2005/Atom}title") or ""
        )
        if not title:
            continue
        link = item.findtext("link") or ""
        if not link:
            el = item.find("{http://www.w3.org/2005/Atom}link")
            if el is not None:
                link = el.get("href", "")
        if not link:
            continue
        summary = strip_html(
            item.findtext("description") or
            item.findtext("{http://www.w3.org/2005/Atom}summary") or
            item.findtext("{http://www.w3.org/2005/Atom}content") or ""
        )[:300]
        pub_date = (
            item.findtext("pubDate") or
            item.findtext("{http://www.w3.org/2005/Atom}published") or
            item.findtext("{http://www.w3.org/2005/Atom}updated") or
            datetime.now(timezone.utc).isoformat()
        )
        img = find_image(item, link)
        s   = score_article(title, summary, is_english)
        cat = detect_category(title, summary, default_cat)

        if s >= MIN_SCORE:
            if is_english:
                title   = translate_to_pt(title)
                summary = translate_to_pt(summary)
            articles.append({
                "id":      make_id(link),
                "cat":     cat,
                "title":   title[:200],
                "summary": summary,
                "source":  source,
                "date":    pub_date,
                "url":     link,
                "img":     img,
                "score":   s,
            })

    imgs_ok = sum(1 for a in articles if a['img'])
    print(f"  ✅  {source}: {len(articles)} artigos ({imgs_ok} com imagem)")
    return articles

def main():
    print("🚀 A iniciar fetch de notícias positivas...")
    all_articles, seen_urls = [], set()

    for feed_url, source, default_cat, is_english in FEEDS:
        print(f"\n📡 {source}...")
        articles = fetch_feed(feed_url, source, default_cat, is_english)
        for a in articles:
            if a["url"] not in seen_urls:
                seen_urls.add(a["url"])
                all_articles.append(a)
        time.sleep(0.5)

    all_articles.sort(key=lambda x: x["score"], reverse=True)
    source_counts, diversified = {}, []
    for a in all_articles:
        src = a["source"]
        if source_counts.get(src, 0) < MAX_PER_SOURCE:
            diversified.append(a)
            source_counts[src] = source_counts.get(src, 0) + 1

    final = diversified[:MAX_NEWS]
    output = {
        "last_update": datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC"),
        "total":       len(final),
        "news":        final,
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    imgs_total = sum(1 for a in final if a['img'])
    print(f"\n✨ {len(final)} notícias | {imgs_total} com imagem | {len(final)-imgs_total} sem imagem")
    if final:
        print(f"   Score médio: {sum(a['score'] for a in final)/len(final):.2f}")

if __name__ == "__main__":
    main()
