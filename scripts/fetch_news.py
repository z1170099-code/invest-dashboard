"""Google News RSS検索を使って、銘柄ごと・マクロ経済のニュース見出しを取得する。

APIキー不要の公開RSSエンドポイント(https://news.google.com/rss/search)を利用する。
"""

import logging
import urllib.parse

import feedparser

logger = logging.getLogger(__name__)

_BASE_URL = "https://news.google.com/rss/search"


def _search_news(query: str, max_articles: int) -> list[dict]:
    encoded_query = urllib.parse.quote(query)
    url = f"{_BASE_URL}?q={encoded_query}&hl=ja&gl=JP&ceid=JP:ja"

    try:
        feed = feedparser.parse(url)
    except Exception:
        logger.exception("ニュース取得に失敗しました: %s", query)
        return []

    articles = []
    for entry in feed.entries[:max_articles]:
        articles.append(
            {
                "title": entry.get("title", ""),
                "link": entry.get("link", ""),
                "published": entry.get("published", ""),
                "source": entry.get("source", {}).get("title", ""),
            }
        )
    return articles


def fetch_ticker_news(name: str, max_articles: int = 5) -> list[dict]:
    """銘柄名で関連ニュースを検索する。取得できなければ空リストを返す。"""
    return _search_news(f"{name} 株価", max_articles)


def fetch_macro_news(queries: list[str], max_articles_per_query: int = 3) -> list[dict]:
    """マクロ経済系のキーワードで世界情勢ニュースを検索する。"""
    articles: list[dict] = []
    for query in queries:
        articles.extend(_search_news(query, max_articles_per_query))
    return articles
