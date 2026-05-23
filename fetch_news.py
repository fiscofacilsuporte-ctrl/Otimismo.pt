import os, requests, json, feedparser, re
from datetime import datetime
from dateutil import parser
from urllib.parse import quote
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
import random

# ── PALAVRAS-CHAVE ──────────────────────────────────────────────────────────
POSITIVE_KEYWORDS = ['sucesso', 'vitória', 'triunfo', 'conquista', 'avanço', 'progresso', 'inovação', 'melhoria', 'desenvolvimento', 'crescimento', 'esperança', 'inspirador', 'incrível', 'fantástico', 'maravilhoso', 'extraordinário', 'positivo', 'bom', 'excelente', 'ótimo', 'magnífico', 'solidariedade', 'ajuda', 'humanitário', 'voluntário', 'caridade', 'descoberta', 'pesquisa', 'científico', 'estudo', 'investigação', 'preservação', 'conservação', 'sustentável', 'renovável', 'ambiental', 'saúde', 'bem-estar', 'cura', 'tratamento', 'vacinação', 'educação', 'aprendizado', 'conhecimento', 'paz', 'acordo', 'cooperação', 'união', 'comunidade', 'recorde', 'melhor', 'primeira vez', 'novo', 'inédito', 'resgate', 'salvação', 'proteção', 'segurança', 'prêmio', 'reconhecimento', 'homenagem', 'celebração', 'oportunidade', 'chance', 'possibilidade', 'potencial', 'liberdade', 'direitos', 'justiça', 'igualdade', 'inclusão', 'generosidade', 'gentileza',
                      # English keywords for English sources
                      'success', 'victory', 'triumph', 'advance', 'progress', 'innovation', 'improvement', 'development', 'growth', 'hope', 'inspiring', 'incredible', 'fantastic', 'wonderful', 'extraordinary', 'positive', 'good', 'excellent', 'great', 'solidarity', 'help', 'humanitarian', 'volunteer', 'charity', 'discovery', 'research', 'scientific', 'conservation', 'sustainable', 'renewable', 'health', 'healing', 'treatment', 'education', 'learning', 'knowledge', 'peace', 'cooperation', 'community', 'record', 'best', 'first time', 'new', 'rescue', 'protection', 'safety', 'award', 'recognition', 'celebration', 'opportunity', 'potential', 'freedom', 'rights', 'justice', 'equality', 'inclusion', 'generosity', 'kindness', 'breakthrough', 'solution', 'clean', 'green', 'save', 'recover', 'thrive', 'flourish', 'restore', 'empower', 'transform', 'uplift', 'joy', 'happy', 'happiness', 'smile', 'love', 'care']
NEGATIVE_KEYWORDS = ['morte', 'crime', 'guerra', 'crise', 'bloqueio', 'erro', 'falha', 'opinião', 'colunista', 'death', 'war', 'crisis', 'murder', 'attack', 'violence', 'violência', 'acidente', 'desastre', 'catástrofe', 'tragédia', 'doença', 'epidemia', 'pandemia', 'corrupção', 'fraude', 'escândalo', 'roubo', 'assalto', 'pobreza', 'miséria', 'fome', 'desemprego', 'recessão', 'depressão', 'ansiedade', 'suicídio', 'automutilação', 'conflito', 'disputa', 'tensão', 'ameaça', 'perigo', 'perda', 'luto', 'sofrimento', 'dor', 'angústia', 'fechamento', 'encerramento', 'cancelamento', 'suspensão', 'adiamento', 'assassinato', 'tiroteio', 'vítima', 'ferido', 'ataque', 'terrorismo', 'mortalidade', 'letalidade']
BLACKLIST_KEYWORDS = ['hantavírus', 'ebola', 'ébola', 'dengue', 'malária', 'surto', 'contágio', 'infecção', 'infectado', 'morto', 'falecido', 'homicídio', 'violação', 'guerra', 'bombardeio', 'míssil', 'exército', 'combate', 'inflação', 'dívida', 'falência', 'corte', 'greve', 'protesto', 'manifestação', 'preso', 'detido', 'tribunal', 'julgamento', 'pena', 'prisão']

# Fontes em inglês que precisam de tradução
ENGLISH_SOURCES = {'Good News Network', 'Positive News', 'Reasons to be Cheerful', 'The Guardian', 'Google News'}

# ── TRADUÇÃO ────────────────────────────────────────────────────────────────
_translator = GoogleTranslator(source='auto', target='pt')

def translate_to_pt(text):
    """Traduz texto para português. Retorna o original em caso de erro."""
    if not text or not text.strip():
        return text
    try:
        # GoogleTranslator tem limite de ~5000 chars; truncamos se necessário
        chunk = text[:4500]
        result = _translator.translate(chunk)
        return result if result else text
    except Exception as e:
        print(f"  [tradução] erro: {e}")
        return text

def maybe_translate(title, summary, source_name):
    """Traduz título e sumário se a fonte for inglesa."""
    if source_name in ENGLISH_SOURCES:
        title_pt   = translate_to_pt(title)
        summary_pt = translate_to_pt(summary)
        return title_pt, summary_pt
    return title, summary

# ── EXTRAÇÃO DE IMAGEM ──────────────────────────────────────────────────────
def extract_image(entry):
    """Tenta obter imagem do RSS. Se não encontrar, vai buscar og:image à página."""
    # 1. media:content
    if hasattr(entry, 'media_content') and entry.media_content:
        return entry.media_content[0].get('url')
    # 2. media:thumbnail
    if hasattr(entry, 'media_thumbnail') and entry.media_thumbnail:
        return entry.media_thumbnail[0].get('url')
    # 3. enclosures
    if hasattr(entry, 'enclosures') and entry.enclosures:
        for enc in entry.enclosures:
            if enc.get('type', '').startswith('image'):
                return enc.get('href') or enc.get('url')
    # 4. links com type image
    if hasattr(entry, 'links'):
        for link in entry.links:
            if 'image' in link.get('type', ''):
                return link.get('href')
    # 5. <img> dentro do conteúdo HTML do feed
    content = ''
    if hasattr(entry, 'summary'):
        content += entry.summary
    if hasattr(entry, 'content') and entry.content:
        content += entry.content[0].value
    if content:
        soup = BeautifulSoup(content, 'html.parser')
        img = soup.find('img')
        if img and img.get('src'):
            return img['src']
    # 6. Fallback: og:image da página do artigo
    try:
        url = entry.link
        # Evitar URLs do Google News (redirect — og:image não funciona)
        if 'news.google.com' not in url:
            resp = requests.get(url, timeout=6, headers={'User-Agent': 'Mozilla/5.0'})
            if resp.ok:
                page_soup = BeautifulSoup(resp.text, 'html.parser')
                og = page_soup.find('meta', property='og:image') or \
                     page_soup.find('meta', attrs={'name': 'og:image'}) or \
                     page_soup.find('meta', attrs={'name': 'twitter:image'}) or \
                     page_soup.find('meta', property='twitter:image')
                if og and og.get('content'):
                    return og['content']
    except Exception:
        pass
    return None

# ── ANÁLISE DE SENTIMENTO ───────────────────────────────────────────────────
def calculate_sentiment_score(title, summary, is_trusted_source=False):
    text = (title + ' ' + (summary or '')).lower()
    for black in BLACKLIST_KEYWORDS:
        if black in text:
            return -1.0
    pos = sum(1 for kw in POSITIVE_KEYWORDS if kw in text)
    neg = sum(1 for kw in NEGATIVE_KEYWORDS if kw in text)
    base_score = 0.6 if is_trusted_source else 0.5
    if neg > 0:
        return (pos / (pos + (neg * 3))) if pos + neg > 0 else 0.0
    return max(base_score, pos / (pos + neg) if pos + neg > 0 else base_score)

# ── RSS GENÉRICO ────────────────────────────────────────────────────────────
def fetch_rss_articles(rss_url, category, source_name=None, is_trusted=False):
    articles = []
    try:
        feed = feedparser.parse(rss_url)
        src  = source_name or (feed.feed.title if hasattr(feed.feed, 'title') else 'Fonte')
        for entry in feed.entries:
            title   = entry.title
            summary = entry.summary if hasattr(entry, 'summary') else title
            score   = calculate_sentiment_score(title, summary, is_trusted)
            if score >= 0.5:
                # Traduzir se necessário
                title_pt, summary_pt = maybe_translate(title, summary, src)
                articles.append({
                    'title':   title_pt,
                    'summary': BeautifulSoup(summary_pt, "html.parser").get_text()[:300] + "...",
                    'url':     entry.link,
                    'img':     extract_image(entry),
                    'source':  src,
                    'cat':     category,
                    'date':    parser.parse(entry.published).isoformat() if hasattr(entry, 'published') else datetime.now().isoformat(),
                    'score':   score
                })
    except Exception as e:
        print(f"[RSS] Erro em {rss_url}: {e}")
    return articles

# ── GOOGLE NEWS ─────────────────────────────────────────────────────────────
def fetch_google_news(query, category):
    articles = []
    try:
        url  = f"https://news.google.com/rss/search?q={quote(query)}&hl=pt-PT&gl=PT&ceid=PT:pt"
        feed = feedparser.parse(url)
        for entry in feed.entries[:15]:
            title   = entry.title
            summary = entry.summary if hasattr(entry, 'summary') else title
            score   = calculate_sentiment_score(title, summary)
            if score >= 0.55:
                articles.append({
                    'title':   title,
                    'summary': BeautifulSoup(summary, "html.parser").get_text()[:250] + "...",
                    'url':     entry.link,
                    'img':     None,  # Google News redirects — og:image não funciona
                    'source':  'Google News',
                    'cat':     category,
                    'date':    parser.parse(entry.published).isoformat() if hasattr(entry, 'published') else datetime.now().isoformat(),
                    'score':   score
                })
    except Exception as e:
        print(f"[Google News] Erro: {e}")
    return articles

# ── PRINCIPAL ────────────────────────────────────────────────────────────────
def fetch_positive_news():
    all_articles = []

    trusted_feeds = [
        {"url": "https://razoesparaacreditar.com/feed/",              "cat": "sociedade", "name": "Razões para Acreditar"},
        {"url": "https://www.goodnewsnetwork.org/feed/",              "cat": "sociedade", "name": "Good News Network"},
        {"url": "https://www.positive.news/feed/",                    "cat": "sociedade", "name": "Positive News"},
        {"url": "https://www.sicnoticias.pt/rss/boas-noticias",       "cat": "sociedade", "name": "SIC Notícias"},
        {"url": "https://reasonstobecheerful.world/feed/",            "cat": "sociedade", "name": "Reasons to be Cheerful"}
    ]
    general_feeds = [
        {"url": "https://news.un.org/pt/news/topic/health/feed/rss.xml",                    "cat": "saude",    "name": "ONU News"},
        {"url": "https://news.un.org/pt/news/topic/culture-and-education/feed/rss.xml",     "cat": "cultura",  "name": "ONU News"},
        {"url": "https://news.un.org/pt/news/topic/economic-development/feed/rss.xml",      "cat": "economia", "name": "ONU News"},
        {"url": "https://lifestyle.sapo.pt/rss/saude",                                      "cat": "saude",    "name": "SAPO Lifestyle"},
        {"url": "https://p3.publico.pt/rss",                                                "cat": "cultura",  "name": "Público P3"},
        {"url": "https://www.theguardian.com/world/series/the-upside/rss",                  "cat": "sociedade","name": "The Guardian"}
    ]

    for f in trusted_feeds:
        print(f"[trusted] {f['name']} ...")
        all_articles.extend(fetch_rss_articles(f["url"], f["cat"], f.get("name"), True))
    for f in general_feeds:
        print(f"[general] {f['name']} ...")
        all_articles.extend(fetch_rss_articles(f["url"], f["cat"], f.get("name"), False))

    queries = [
        {"query": "inovação tecnológica portugal",       "cat": "tecnologia"},
        {"query": "sustentabilidade ambiental sucesso",  "cat": "ambiente"},
        {"query": "ciência descoberta fantástica",       "cat": "ciencia"},
        {"query": "desporto vitória inspiradora portugal","cat": "desporto"},
        {"query": "economia crescimento positivo portugal","cat": "economia"}
    ]
    for q in queries:
        all_articles.extend(fetch_google_news(q["query"], q["cat"]))

    # Deduplicar
    seen, unique = set(), []
    for a in all_articles:
        if a['url'] not in seen:
            seen.add(a['url'])
            unique.append(a)

    # Diversificar por fonte (máx 3 por fonte)
    random.shuffle(unique)
    source_counts, diversified = {}, []
    for a in unique:
        src = a['source']
        if source_counts.get(src, 0) < 3:
            diversified.append(a)
            source_counts[src] = source_counts.get(src, 0) + 1

    # Top 24 por score
    final = sorted(diversified, key=lambda x: x['score'], reverse=True)[:24]

    if final:
        with open("noticias.json", "w", encoding="utf-8") as f:
            json.dump({"last_update": datetime.now().strftime("%d/%m/%Y %H:%M"), "news": final}, f, ensure_ascii=False, indent=2)
        imgs_ok = sum(1 for a in final if a['img'])
        print(f"✅ {len(final)} notícias guardadas | {imgs_ok} com imagem | {len(final)-imgs_ok} sem imagem")
    else:
        print("⚠️  Nenhuma notícia passou os filtros.")

if __name__ == "__main__":
    fetch_positive_news()
