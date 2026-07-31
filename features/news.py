import datetime, requests
from bs4 import BeautifulSoup
from config import NEWS_API_KEY, now_jkt
from ai.groq_client import groq_complete
from tracer import trace

@trace
def get_news(topic: str) -> str:
    articles = _fetch_articles(topic)
    if articles is None:
        return f"📭 Could not fetch news for *{topic}*. Try again later."
    if not articles:
        return f"📭 No news found for *{topic}*."

    a = articles[0]
    return summarize_article(
        title=a.get("title", "No title"),
        article_url=a.get("url", ""),
        source=a.get("source", {}).get("name", "Unknown source"),
        published=a.get("publishedAt", "")[:10],
        description=a.get("content") or a.get("description") or "",
    )

# ================================================================
# STRUCTURED — list[dict] shape for the mobile REST API. NewsAPI call
# only, no scrape, no LLM summarization — that's too slow to fan out
# across a list. See summarize_article() for the per-article detail path.
# ================================================================
@trace
def get_news_structured(topic: str, limit: int = 5) -> list[dict]:
    articles = _fetch_articles(topic, limit=limit)
    if not articles:
        return []
    return [
        {
            "title": a.get("title", "No title"),
            "source": a.get("source", {}).get("name", "Unknown source"),
            "publishedAt": a.get("publishedAt", "")[:10],
            "url": a.get("url", ""),
            "description": a.get("description") or "",
        }
        for a in articles
    ]

def _fetch_articles(topic: str, limit: int = 5) -> list[dict] | None:
    """Returns None on request failure (distinct from an empty result list)."""
    url = (
        f"https://newsapi.org/v2/everything"
        f"?q={topic}&apiKey={NEWS_API_KEY}&pageSize={limit}&language=en&sortBy=relevancy"
        f"&from={(now_jkt() - datetime.timedelta(days=7)).strftime('%Y-%m-%d')}"
    )
    try:
        data = requests.get(url, timeout=10).json()
        return data.get("articles", [])
    except Exception:
        return None

# ================================================================
# SUMMARIZE ONE ARTICLE — scrapes the full text (falling back to the
# NewsAPI description) and runs it through Groq. Used both by get_news()
# (topic search, always the top result) and the mobile detail route,
# which already has title/source/publishedAt/description from a prior
# get_news_structured() call and only needs the slow part done once,
# for the one article the user tapped.
# ================================================================
@trace
def summarize_article(title: str, article_url: str, source: str = "", published: str = "", description: str = "") -> str:
    raw_text = description or ""

    if article_url:
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            page    = requests.get(article_url, headers=headers, timeout=10)
            soup    = BeautifulSoup(page.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()
            scraped = " ".join(p.get_text().strip() for p in soup.find_all("p") if len(p.get_text().strip()) > 0)
            if len(scraped) > len(raw_text):
                raw_text = scraped[:5000]
        except Exception as e:
            print(f"[Scrape error] {e}")

    if not raw_text:
        raw_text = "Content not available."

    prompt = f"""You are a news summarizer for WhatsApp. Summarize the article below.

🔍 *What happened:*
[2-3 sentences explaining the main event]

👥 *Who is impacted:*
[Who is affected and how]

⚠️ *Why it matters:*
[Significance or consequences]

✅ *Solution / Response:* (skip if none)
[Actions taken or official responses]

📌 *Key takeaway:*
[One concise sentence]

Article title: {title}
Article content: {raw_text}"""

    try:
        summary = groq_complete("", prompt, max_tokens=1024, temperature=0.5)
    except Exception as e:
        print(f"[News summary error] {e}")
        summary = raw_text[:500] + "..."

    return (
        f"📰 *{title}*\n"
        f"🗞 {source} · {published}\n"
        f"─────────────────\n"
        f"{summary}\n\n"
        f"🔗 {article_url}"
    )
