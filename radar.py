#!/usr/bin/env python3
"""
Radar RSS Chính Trị — Daily news aggregator
Fetches RSS feeds, filters by interest topics, generates mobile-friendly HTML.
"""

import json
import os
import sys
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
import subprocess
import webbrowser
import re
import html as html_lib
import time

BASE_DIR = Path(__file__).parent
CONFIG_FILE = BASE_DIR / "config.json"

# ─── Config ───────────────────────────────────────────────────────────────────

def load_config():
    with open(CONFIG_FILE, encoding="utf-8") as f:
        cfg = json.load(f)
    if "topics" in cfg and "default_topics" not in cfg:
        cfg["default_topics"] = cfg.pop("topics")
    return cfg

# ─── RSS Fetching ──────────────────────────────────────────────────────────────

def fetch_rss(url: str, source_name: str) -> list[dict]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            content = resp.read()
    except Exception as e:
        print(f"  ✗ {source_name}: {e}")
        return []

    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        print(f"  ✗ {source_name} XML parse error: {e}")
        return []

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    articles = []

    # RSS 2.0
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = (item.findtext("description") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()

        desc = re.sub(r"<[^>]+>", "", html_lib.unescape(desc)).strip()
        desc = re.sub(r"\s+", " ", desc)[:300]

        articles.append({
            "title": html_lib.unescape(title),
            "link": link,
            "desc": desc,
            "date": pub_date,
            "source": source_name,
        })

    # Atom feed fallback
    if not articles:
        for entry in root.findall(".//atom:entry", ns):
            title = (entry.findtext("atom:title", namespaces=ns) or "").strip()
            link_el = entry.find("atom:link", ns)
            link = link_el.get("href", "") if link_el is not None else ""
            desc = (entry.findtext("atom:summary", namespaces=ns) or "").strip()
            desc = re.sub(r"<[^>]+>", "", html_lib.unescape(desc)).strip()[:300]
            pub_date = (entry.findtext("atom:updated", namespaces=ns) or "").strip()
            articles.append({
                "title": html_lib.unescape(title),
                "link": link,
                "desc": desc,
                "date": pub_date,
                "source": source_name,
            })

    return articles

def fetch_all(sources: list[dict]) -> list[dict]:
    all_articles = []
    for src in sources:
        print(f"  ↓ {src['name']}...")
        arts = fetch_rss(src["url"], src["name"])
        all_articles.extend(arts)
        time.sleep(0.3)
    return all_articles

# ─── Topic Filtering ───────────────────────────────────────────────────────────

TOPIC_KEYWORDS = {
    # Chính trị quốc tế
    "Iran": ["iran", "tehran", "tehران", "khamenei", "pezeshkian", "hormuz", "persian"],
    "Mỹ": ["mỹ", "hoa kỳ", "trump", "white house", "washington", "biden", "america", "american", "pentagon", "congress", "senate", "republican", "democrat"],
    "Việt Nam": ["việt nam", "vietnam", "hà nội", "hanoi", "bộ chính trị", "đảng cộng sản", "chính phủ việt"],
    "Trung Quốc": ["trung quốc", "china", "chinese", "beijing", "bắc kinh", "tập cận bình", "xi jinping", "cpc", "pla", "huawei", "tencent", "alibaba", "baidu"],
    "Nga": ["russia", "russian", "putin", "moscow", "kremlin", "zelensky", "ukraine", "ukrainian"],
    "Israel": ["israel", "israeli", "gaza", "hamas", "tel aviv", "netanyahu", "palestine", "palestinian", "west bank", "hezbollah"],
    # Kinh tế & Tài chính
    "Kinh tế": ["kinh tế", "economy", "economic", "gdp", "lạm phát", "inflation", "tăng trưởng", "suy thoái", "recession", "thương mại", "xuất khẩu", "nhập khẩu", "export", "import", "ngân hàng trung ương", "central bank", "lãi suất", "interest rate", "tariff", "tax cut", "fiscal", "monetary policy", "jobs report", "unemployment", "consumer spending", "retail sales"],
    "Chứng khoán": ["chứng khoán", "stock", "cổ phiếu", "vn-index", "vnindex", "vn30", "nasdaq", "s&p 500", "dow jones", "wall street", "sàn giao dịch", "ipo", "niêm yết", "thị trường chứng khoán", "bull market", "bear market", "securities", "share price", "market cap", "earnings", "quarterly results"],
    "Đầu tư": ["đầu tư", "invest", "investment", "fdi", "venture capital", "startup", "quỹ đầu tư", "fund", "portfolio", "tài sản", "asset", "bất động sản", "real estate", "trái phiếu", "bond", "etf", "warren buffett", "private equity", "hedge fund", "valuation", "funding round", "series a", "series b"],
    "Tiền tệ": ["tiền tệ", "currency", "tỷ giá", "exchange rate", "forex", "usd", "đô la", "dollar", "euro", "nhân dân tệ", "yuan", "yen", "crypto", "bitcoin", "btc", "ethereum", "tiền điện tử", "cryptocurrency", "blockchain", "stablecoin", "defi", "web3", "token"],
    "Vàng": ["vàng", "gold", "sjc", "giá vàng", "gold price", "bullion", "vàng miếng", "vàng nhẫn", "kim loại quý", "precious metal", "ounce", "troy"],
    "Kim loại & Hàng hóa": ["kim loại", "metal", "bạc", "silver", "nhôm", "aluminum", "thép", "steel", "quặng sắt", "iron ore", "hàng hóa", "commodity", "dầu thô", "crude oil", "opec", "xăng", "petrol", "khí đốt", "natural gas", "than", "coal", "nông sản", "lúa mì", "wheat", "đậu nành", "soybean", "cà phê", "coffee", "cao su", "rubber"],
    # Công nghệ
    "AI": ["artificial intelligence", "trí tuệ nhân tạo", "machine learning", "học máy", "deep learning", "chatgpt", "openai", "google ai", "gemini ai", "anthropic", "neural network", "mạng nơ-ron", "generative ai", "ai chip", "nvidia", "copilot", "midjourney", "stable diffusion", "mô hình ngôn ngữ", "meta ai", "claude ", "llama model"],
    "Công nghệ": ["công nghệ", "technology", "tech company", "software", "hardware", "smartphone", "iphone", "android", "samsung", "apple", "google", "microsoft", "meta ", "amazon", "tesla", "spacex", "cybersecurity", "data breach", "hacking", "privacy", "cloud computing", "semiconductor", "chip", "5g", "6g", "quantum computing", "điện thoại", "laptop", "tablet", "internet", "app ", "streaming", "gaming", "xbox", "playstation", "nintendo", "social media", "tiktok", "instagram", "facebook", "youtube", "twitter", "elon musk", "mark zuckerberg", "tim cook", "satya nadella", "sundar pichai"],
}

TOPIC_REGEX_KEYWORDS = {
    "AI": [r"\bgpt\b", r"\bai\b(?=[\s\-](?:gen|chip|model|agent|tool|system|powered|based|driven|first|native|photo|image|job|risk|concern|fear|boom|spend|cut|lead|start|company|firm|race|safety|regulation|search|assistant|feature|update|lab|research|training|billion|million|worker|replace|threat|ethic|bias|detect|fake|deep))"],
    "Mỹ": [r"\bus\b", r"\busa\b"],
    "Nga": [r"\bnga\b"],
    "Kinh tế": [r"\bfed\b", r"\btrade\b", r"\bgrowth\b"],
    "Công nghệ": [r"\btech\b", r"\bapp\b", r"\bits\b"],
}

ALL_TOPICS = list(TOPIC_KEYWORDS.keys())

REGEX_ONLY_TOPICS = {"AI"}

def topic_matches(topic: str, article: dict) -> bool:
    text = (article["title"] + " " + article["desc"]).lower()
    keywords = TOPIC_KEYWORDS.get(topic, [topic.lower()])
    if topic not in REGEX_ONLY_TOPICS:
        keywords = list(set(keywords + [topic.lower()]))
    if any(kw in text for kw in keywords):
        return True
    for pattern in TOPIC_REGEX_KEYWORDS.get(topic, []):
        if re.search(pattern, text):
            return True
    return False

def filter_by_topics(articles: list[dict], topics: list[str]) -> dict[str, list[dict]]:
    seen_links = set()
    result = {t: [] for t in topics}
    for art in articles:
        if not art["title"] or not art["link"]:
            continue
        link = art["link"]
        for topic in topics:
            if link + topic not in seen_links and topic_matches(topic, art):
                result[topic].append(art)
                seen_links.add(link + topic)
    return result

# ─── HTML Generation ───────────────────────────────────────────────────────────

TOPIC_ICONS = {
    "Iran": "🇮🇷",
    "Mỹ": "🇺🇸",
    "Việt Nam": "🇻🇳",
    "Trung Quốc": "🇨🇳",
    "Nga": "🇷🇺",
    "Israel": "🇮🇱",
    "Kinh tế": "📊",
    "Chứng khoán": "📈",
    "Đầu tư": "💰",
    "Tiền tệ": "💱",
    "Vàng": "🥇",
    "Kim loại & Hàng hóa": "🛢️",
    "AI": "🤖",
    "Công nghệ": "💻",
}

SOURCE_COLORS = {
    "VnExpress": "#1a73e8",
    "Tuổi Trẻ": "#e53935",
    "Dân Trí": "#ff6f00",
    "Thanh Niên": "#2e7d32",
    "BBC": "#b71c1c",
    "Reuters": "#ff6600",
    "Genk": "#e91e63",
    "Tinhte": "#0288d1",
    "TechCrunch": "#0a9e01",
    "The Verge": "#e8503a",
    "Ars Technica": "#ff4e00",
    "Wired": "#000000",
    "MIT Tech": "#a31f34",
    "Hacker News": "#ff6600",
    "The Register": "#d32f2f",
    "ZDNet": "#d32f2f",
    "Engadget": "#5200ff",
}

def get_source_color(source_name: str) -> str:
    for key, color in SOURCE_COLORS.items():
        if key in source_name:
            return color
    return "#555"

DATE_FORMATS = [
    "%a, %d %b %Y %H:%M:%S %z",
    "%a, %d %b %Y %H:%M:%S %Z",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S%z",
]

def parse_date(date_str: str) -> datetime | None:
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None

def format_date(date_str: str) -> str:
    dt = parse_date(date_str)
    if dt:
        return dt.strftime("%d/%m %H:%M")
    return date_str[:16] if date_str else ""

def sort_articles_by_date(articles: list[dict]) -> list[dict]:
    def sort_key(art):
        dt = parse_date(art.get("date", ""))
        if dt is None:
            return 0
        return dt.timestamp() if dt.tzinfo else dt.replace(tzinfo=None).timestamp()
    return sorted(articles, key=sort_key, reverse=True)

def build_article_card(art: dict) -> str:
    title = html_lib.escape(art["title"])
    desc = html_lib.escape(art["desc"])
    link = html_lib.escape(art["link"])
    source = html_lib.escape(art["source"])
    date_str = format_date(art["date"])
    color = get_source_color(art["source"])

    return f"""
    <a class="article-card" href="{link}" target="_blank" rel="noopener">
      <div class="article-meta">
        <span class="article-source" style="color:{color}">{source}</span>
        <span class="article-dot"></span>
        <span class="article-time">{date_str}</span>
      </div>
      <div class="article-title">{title}</div>
      {"<div class='article-desc'>" + desc + "</div>" if desc else ""}
    </a>"""

def build_html(topics_data: dict[str, list[dict]], sources: list[dict], default_topics: list[str]) -> str:
    now = datetime.now()
    date_str = now.strftime("%d/%m/%Y")
    time_str = now.strftime("%H:%M")

    total_sources = len(sources)

    all_topic_names = list(topics_data.keys())
    topic_meta_json = json.dumps(
        {topic: {"icon": TOPIC_ICONS.get(topic, "🌐"), "count": len(arts)}
         for topic, arts in topics_data.items()},
        ensure_ascii=False,
    )
    default_topics_json = json.dumps(default_topics, ensure_ascii=False)

    max_articles = 50

    # Generate ALL topic sections (hidden by default, JS controls visibility)
    sections_html = ""
    for topic, arts in topics_data.items():
        arts = sort_articles_by_date(arts)
        icon = TOPIC_ICONS.get(topic, "🌐")
        topic_id = html_lib.escape(topic)
        cards = "".join(build_article_card(a) for a in arts[:max_articles])
        if not cards:
            cards = '<div class="empty-state"><div class="icon">🔍</div><p>Không tìm thấy bài viết phù hợp</p></div>'
        sections_html += f"""
        <section class="topic-section" data-topic="{topic_id}">
          <div class="section-header">
            <span class="section-title">{icon} {topic}</span>
            <span class="article-count">{len(arts)} bài</span>
          </div>
          {cards}
        </section>"""

    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <title>📡 Radar Chính Trị · {date_str}</title>
  <style>
    :root {{
      --bg: #f0f2f5;
      --surface: #ffffff;
      --surface2: #f4f6f9;
      --text: #0f172a;
      --text2: #64748b;
      --accent: #1d4ed8;
      --border: #e2e8f0;
      --tab-active-bg: #ffffff;
      --shadow: 0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.05);
      --shadow-hover: 0 4px 16px rgba(0,0,0,0.12);
      --header-bg: linear-gradient(135deg, #1d4ed8 0%, #1e40af 100%);
      --radius: 12px;
      --success: #16a34a;
      --danger: #dc2626;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #0b0f1a;
        --surface: #151c2e;
        --surface2: #1a2236;
        --text: #e2e8f0;
        --text2: #94a3b8;
        --accent: #60a5fa;
        --border: #1e293b;
        --tab-active-bg: #0b0f1a;
        --shadow: 0 1px 4px rgba(0,0,0,0.4);
        --shadow-hover: 0 4px 16px rgba(0,0,0,0.5);
        --header-bg: linear-gradient(135deg, #1e3a8a 0%, #1e40af 100%);
        --success: #22c55e;
        --danger: #ef4444;
      }}
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      -webkit-font-smoothing: antialiased;
    }}
    /* ── Header ── */
    header {{
      background: var(--header-bg);
      position: sticky;
      top: 0;
      z-index: 100;
      box-shadow: 0 2px 12px rgba(0,0,0,0.25);
    }}
    .header-top {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 14px 18px 10px;
    }}
    .logo {{
      font-size: 17px;
      font-weight: 700;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 6px;
      letter-spacing: -0.3px;
    }}
    .header-date {{
      font-size: 12px;
      color: rgba(255,255,255,0.75);
      font-weight: 500;
    }}
    /* ── Tabs ── */
    .tabs {{
      display: flex;
      gap: 2px;
      padding: 0 12px;
      overflow-x: auto;
      scrollbar-width: none;
      align-items: flex-end;
    }}
    .tabs::-webkit-scrollbar {{ display: none; }}
    .tab {{
      padding: 9px 16px 11px;
      border: none;
      border-radius: 10px 10px 0 0;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      white-space: nowrap;
      background: rgba(255,255,255,0.12);
      color: rgba(255,255,255,0.75);
      transition: all 0.2s ease;
      display: flex;
      align-items: center;
      gap: 5px;
    }}
    .tab.active {{
      background: var(--tab-active-bg);
      color: var(--accent);
    }}
    .tab-count {{
      background: rgba(255,255,255,0.25);
      border-radius: 10px;
      padding: 1px 6px;
      font-size: 11px;
      font-weight: 700;
    }}
    .tab.active .tab-count {{
      background: var(--accent);
      color: #fff;
    }}
    .tab-close {{
      display: flex;
      align-items: center;
      justify-content: center;
      width: 16px;
      height: 16px;
      border-radius: 50%;
      font-size: 10px;
      line-height: 1;
      background: rgba(255,255,255,0.18);
      color: rgba(255,255,255,0.7);
      margin-left: 2px;
      flex-shrink: 0;
      transition: all 0.15s ease;
    }}
    .tab-close:hover {{
      background: rgba(220,38,38,0.85);
      color: #fff;
      transform: scale(1.15);
    }}
    .tab.active .tab-close {{
      background: var(--border);
      color: var(--text2);
    }}
    .tab.active .tab-close:hover {{
      background: var(--danger);
      color: #fff;
    }}
    .tab-add {{
      padding: 9px 14px 11px;
      font-size: 16px;
      font-weight: 700;
      background: rgba(255,255,255,0.08);
      color: rgba(255,255,255,0.6);
      border-radius: 10px 10px 0 0;
      min-width: 40px;
      justify-content: center;
    }}
    .tab-add:hover {{
      background: rgba(255,255,255,0.2);
      color: #fff;
    }}
    .tab-add.active {{
      background: var(--tab-active-bg);
      color: var(--accent);
    }}
    /* ── Main ── */
    main {{
      max-width: 680px;
      margin: 0 auto;
      padding: 14px 14px 32px;
    }}
    /* ── Stats bar ── */
    .stats-bar {{
      display: flex;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 12px 0;
      margin-bottom: 16px;
      box-shadow: var(--shadow);
    }}
    .stat {{
      flex: 1;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 2px;
      border-right: 1px solid var(--border);
    }}
    .stat:last-child {{ border-right: none; }}
    .stat-value {{
      font-size: 22px;
      font-weight: 800;
      color: var(--accent);
      letter-spacing: -0.5px;
    }}
    .stat-label {{ font-size: 11px; color: var(--text2); font-weight: 500; }}
    /* ── Section ── */
    .topic-section {{ display: none; }}
    .topic-section.active {{ display: block; animation: fadeIn 0.2s ease; }}
    @keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(4px); }} to {{ opacity: 1; transform: translateY(0); }} }}
    .section-header {{
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 14px;
      padding-top: 2px;
    }}
    .section-title {{ font-size: 20px; font-weight: 800; letter-spacing: -0.5px; }}
    .article-count {{
      background: var(--accent);
      color: #fff;
      padding: 2px 9px;
      border-radius: 20px;
      font-size: 11px;
      font-weight: 700;
    }}
    /* ── Article cards ── */
    .article-card {{
      display: block;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 14px 16px;
      margin-bottom: 10px;
      text-decoration: none;
      color: inherit;
      box-shadow: var(--shadow);
      transition: box-shadow 0.2s, transform 0.2s, border-color 0.2s;
      position: relative;
      overflow: hidden;
    }}
    .article-card::before {{
      content: '';
      position: absolute;
      left: 0; top: 0; bottom: 0;
      width: 3px;
      background: var(--source-color, var(--accent));
      border-radius: 0 2px 2px 0;
    }}
    .article-card:active {{
      transform: scale(0.985);
      box-shadow: var(--shadow-hover);
    }}
    @media (hover: hover) {{
      .article-card:hover {{
        box-shadow: var(--shadow-hover);
        border-color: var(--accent);
        transform: translateY(-1px);
      }}
    }}
    .article-meta {{
      display: flex;
      align-items: center;
      gap: 7px;
      margin-bottom: 7px;
      flex-wrap: wrap;
    }}
    .article-source {{
      font-size: 10px;
      font-weight: 800;
      letter-spacing: 0.6px;
      text-transform: uppercase;
    }}
    .article-dot {{ width: 3px; height: 3px; border-radius: 50%; background: var(--text2); flex-shrink: 0; }}
    .article-time {{ font-size: 11px; color: var(--text2); font-weight: 500; }}
    .article-title {{
      font-size: 15px;
      font-weight: 650;
      line-height: 1.45;
      color: var(--text);
      margin-bottom: 5px;
      letter-spacing: -0.1px;
    }}
    .article-desc {{
      font-size: 13px;
      color: var(--text2);
      line-height: 1.55;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }}
    /* ── Empty state ── */
    .empty-state {{
      text-align: center;
      padding: 56px 24px;
      color: var(--text2);
    }}
    .empty-state .icon {{ font-size: 52px; margin-bottom: 14px; }}
    .empty-state p {{ font-size: 15px; }}
    /* ── Interest Topics Panel ── */
    .interest-panel {{
      display: none;
      animation: fadeIn 0.2s ease;
    }}
    .interest-panel.active {{ display: block; }}
    .interest-panel-header {{
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 6px;
      padding-top: 2px;
    }}
    .interest-panel-title {{ font-size: 20px; font-weight: 800; letter-spacing: -0.5px; }}
    .interest-panel-desc {{
      font-size: 13px;
      color: var(--text2);
      margin-bottom: 16px;
      line-height: 1.5;
    }}
    .topic-grid {{
      display: grid;
      grid-template-columns: 1fr;
      gap: 8px;
    }}
    .topic-item {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 14px 16px;
      box-shadow: var(--shadow);
      transition: border-color 0.2s, box-shadow 0.2s;
      cursor: pointer;
    }}
    .topic-item:hover {{
      border-color: var(--accent);
      box-shadow: var(--shadow-hover);
    }}
    .topic-item.selected {{
      border-color: var(--accent);
      background: color-mix(in srgb, var(--accent) 8%, var(--surface));
    }}
    .topic-item-left {{
      display: flex;
      align-items: center;
      gap: 12px;
    }}
    .topic-item-icon {{ font-size: 24px; }}
    .topic-item-info {{ display: flex; flex-direction: column; gap: 2px; }}
    .topic-item-name {{ font-size: 15px; font-weight: 700; }}
    .topic-item-count {{ font-size: 12px; color: var(--text2); }}
    .topic-toggle {{
      width: 44px;
      height: 26px;
      border-radius: 13px;
      background: var(--border);
      position: relative;
      transition: background 0.2s;
      flex-shrink: 0;
    }}
    .topic-toggle::after {{
      content: '';
      position: absolute;
      width: 20px;
      height: 20px;
      border-radius: 50%;
      background: #fff;
      top: 3px;
      left: 3px;
      transition: transform 0.2s;
      box-shadow: 0 1px 3px rgba(0,0,0,0.2);
    }}
    .topic-item.selected .topic-toggle {{
      background: var(--accent);
    }}
    .topic-item.selected .topic-toggle::after {{
      transform: translateX(18px);
    }}
    /* ── Footer ── */
    footer {{
      text-align: center;
      padding: 20px 16px;
      color: var(--text2);
      font-size: 12px;
      line-height: 1.8;
    }}
  </style>
</head>
<body>
  <header>
    <div class="header-top">
      <div class="logo">📡 Radar Chính Trị</div>
      <div class="header-date">{date_str} · {time_str}</div>
    </div>
    <div class="tabs" id="tabs"></div>
  </header>

  <main>
    <div class="stats-bar" id="stats-bar">
      <div class="stat">
        <span class="stat-value" id="stat-articles">0</span>
        <span class="stat-label">bài viết</span>
      </div>
      <div class="stat">
        <span class="stat-value">{total_sources}</span>
        <span class="stat-label">nguồn</span>
      </div>
      <div class="stat">
        <span class="stat-value" id="stat-topics">0</span>
        <span class="stat-label">chủ đề</span>
      </div>
    </div>

    {sections_html}

    <div class="interest-panel" id="interest-panel">
      <div class="interest-panel-header">
        <span class="interest-panel-title">⚙️ Chủ đề quan tâm</span>
      </div>
      <p class="interest-panel-desc">Chọn các chủ đề bạn quan tâm. Mỗi chủ đề sẽ hiển thị như một tab riêng.</p>
      <div class="topic-grid" id="topic-grid"></div>
    </div>
  </main>

  <footer>
    Cập nhật lúc {time_str} · {date_str}<br>
    <small>Radar RSS Chính Trị · {total_sources} nguồn</small>
  </footer>

  <script>
    const TOPIC_META = {topic_meta_json};
    const DEFAULT_TOPICS = {default_topics_json};
    const TAB_KEY = 'radar_tab';
    const ADDED_KEY = 'radar_added';
    const REMOVED_KEY = 'radar_removed';

    let _selectedTopics = null;

    function getSelectedTopics() {{
      if (_selectedTopics) return _selectedTopics;
      let added = [], removed = [];
      try {{ added = JSON.parse(localStorage.getItem(ADDED_KEY) || '[]'); }} catch(e) {{}}
      try {{ removed = JSON.parse(localStorage.getItem(REMOVED_KEY) || '[]'); }} catch(e) {{}}
      const topics = [...DEFAULT_TOPICS];
      removed.forEach(t => {{ const i = topics.indexOf(t); if (i >= 0) topics.splice(i, 1); }});
      added.forEach(t => {{ if (!topics.includes(t) && TOPIC_META[t]) topics.push(t); }});
      _selectedTopics = topics;
      return _selectedTopics;
    }}

    function saveSelectedTopics(topics) {{
      _selectedTopics = topics;
      const added = topics.filter(t => !DEFAULT_TOPICS.includes(t));
      const removed = DEFAULT_TOPICS.filter(t => !topics.includes(t));
      localStorage.setItem(ADDED_KEY, JSON.stringify(added));
      localStorage.setItem(REMOVED_KEY, JSON.stringify(removed));
    }}

    function renderTabs() {{
      const selected = getSelectedTopics();
      const tabsEl = document.getElementById('tabs');
      tabsEl.innerHTML = '';

      selected.forEach((topic, i) => {{
        const meta = TOPIC_META[topic];
        if (!meta) return;
        const btn = document.createElement('button');
        btn.className = 'tab';
        btn.dataset.topic = topic;

        const label = document.createElement('span');
        label.innerHTML = `${{meta.icon}} ${{topic}} <span class="tab-count">${{meta.count}}</span>`;
        label.onclick = () => showTopicTab(topic);
        btn.appendChild(label);

        const close = document.createElement('span');
        close.className = 'tab-close';
        close.textContent = '×';
        close.onclick = (e) => {{ e.stopPropagation(); removeTopic(topic); }};
        btn.appendChild(close);

        tabsEl.appendChild(btn);
      }});

      const addBtn = document.createElement('button');
      addBtn.className = 'tab tab-add';
      addBtn.onclick = () => showInterestPanel();
      addBtn.dataset.topic = '__add__';
      addBtn.textContent = '+';
      tabsEl.appendChild(addBtn);

      const totalArticles = selected.reduce((sum, t) => sum + (TOPIC_META[t]?.count || 0), 0);
      document.getElementById('stat-articles').textContent = totalArticles;
      document.getElementById('stat-topics').textContent = selected.length;
    }}

    function showTopicTab(topic) {{
      document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.topic === topic));
      document.querySelectorAll('.topic-section').forEach(s => s.classList.toggle('active', s.dataset.topic === topic));
      document.getElementById('interest-panel').classList.remove('active');
      localStorage.setItem(TAB_KEY, topic);
    }}

    function showInterestPanel() {{
      document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.topic === '__add__'));
      document.querySelectorAll('.topic-section').forEach(s => s.classList.remove('active'));
      document.getElementById('interest-panel').classList.add('active');
      renderTopicGrid();
    }}

    function renderTopicGrid() {{
      const selected = getSelectedTopics();
      const grid = document.getElementById('topic-grid');
      grid.innerHTML = '';

      Object.entries(TOPIC_META).forEach(([topic, meta]) => {{
        const isSelected = selected.includes(topic);
        const item = document.createElement('div');
        item.className = 'topic-item' + (isSelected ? ' selected' : '');
        item.onclick = () => toggleTopic(topic);
        item.innerHTML = `
          <div class="topic-item-left">
            <span class="topic-item-icon">${{meta.icon}}</span>
            <div class="topic-item-info">
              <span class="topic-item-name">${{topic}}</span>
              <span class="topic-item-count">${{meta.count}} bài viết</span>
            </div>
          </div>
          <div class="topic-toggle"></div>
        `;
        grid.appendChild(item);
      }});
    }}

    function toggleTopic(topic) {{
      let selected = getSelectedTopics();
      const idx = selected.indexOf(topic);
      if (idx >= 0) {{
        selected.splice(idx, 1);
      }} else {{
        selected.push(topic);
      }}
      saveSelectedTopics(selected);
      renderTabs();
      renderTopicGrid();
    }}

    function removeTopic(topic) {{
      let selected = getSelectedTopics();
      const idx = selected.indexOf(topic);
      if (idx < 0) return;
      selected.splice(idx, 1);
      saveSelectedTopics(selected);
      renderTabs();
      const activeTab = localStorage.getItem(TAB_KEY);
      if (activeTab === topic) {{
        if (selected.length > 0) {{
          showTopicTab(selected[0]);
        }} else {{
          showInterestPanel();
        }}
      }}
    }}

    // Init
    renderTabs();
    const savedTab = localStorage.getItem(TAB_KEY);
    const selected = getSelectedTopics();
    if (savedTab && savedTab !== '__add__' && selected.includes(savedTab)) {{
      showTopicTab(savedTab);
    }} else if (selected.length > 0) {{
      showTopicTab(selected[0]);
    }} else {{
      showInterestPanel();
    }}
  </script>
</body>
</html>"""

# ─── Notification ──────────────────────────────────────────────────────────────

def notify_macos(title: str, message: str):
    script = f'display notification "{message}" with title "{title}" sound name "Ping"'
    try:
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True)
    except Exception:
        pass

# ─── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("📡 Radar RSS Chính Trị đang khởi động...\n")
    cfg = load_config()

    default_topics = cfg.get("default_topics", ALL_TOPICS[:3])
    sources = cfg["sources"]
    output_dir = BASE_DIR / cfg.get("output_dir", "output")
    output_dir.mkdir(exist_ok=True)

    print(f"🎯 Tất cả chủ đề: {', '.join(ALL_TOPICS)}")
    print(f"⭐ Mặc định: {', '.join(default_topics)}")
    print(f"📰 Đang fetch {len(sources)} nguồn RSS...\n")

    articles = fetch_all(sources)
    print(f"\n✅ Tổng cộng {len(articles)} bài, đang lọc theo tất cả chủ đề...\n")

    topics_data = filter_by_topics(articles, ALL_TOPICS)
    for topic, arts in topics_data.items():
        icon = TOPIC_ICONS.get(topic, "🌐")
        print(f"  {icon} {topic}: {len(arts)} bài")

    print("\n🔨 Đang tạo HTML...")
    html_content = build_html(topics_data, sources, default_topics)

    output_file = output_dir / "index.html"
    output_file.write_text(html_content, encoding="utf-8")
    print(f"✅ Đã tạo: {output_file}")

    total = sum(len(v) for v in topics_data.values())
    summary = " · ".join(f"{t}: {len(arts)}" for t, arts in topics_data.items())

    if cfg.get("notify", True):
        notify_macos("📡 Radar Chính Trị", f"{total} bài mới · {summary}")

    if cfg.get("open_browser", True):
        url = f"file://{output_file.resolve()}"
        webbrowser.open(url)
        print(f"🌐 Đã mở trình duyệt: {url}")

    print("\n🎉 Hoàn tất!")

if __name__ == "__main__":
    main()
