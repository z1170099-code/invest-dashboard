"""エントリーポイント: ウォッチリスト読み込み→株価取得→ニュース取得→AI分析→レポート生成 を実行する。"""

import logging
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from analyze import analyze_all, analyze_all_holdings
from fetch_news import fetch_macro_news, fetch_ticker_news
from fetch_prices import fetch_all_price_stats
from generate_report import generate_report

# GitHub Actions(Ubuntu)ではstdout/stderrがUTF-8でない場合があり、
# 日本語やBOM付き文字列をログ出力しようとしてUnicodeEncodeErrorが発生し、
# 本来のエラー原因が隠れてしまうことがあるため、明示的にUTF-8化する。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_DIR = _ROOT / "config"
_TEMPLATES_DIR = _ROOT / "templates"
_OUTPUT_PATH = _ROOT / "docs" / "index.html"


def _load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _analyze_group(
    label: str,
    tickers: list[dict],
    max_per_ticker: int,
    macro_news: list[dict],
    analyze_fn=analyze_all,
) -> list[dict]:
    if not tickers:
        return []

    logger.info("[%s] 対象銘柄: %d件", label, len(tickers))

    logger.info("[%s] 株価データを取得中...", label)
    price_stats_by_symbol = fetch_all_price_stats(tickers)

    logger.info("[%s] 個別銘柄のニュースを取得中...", label)
    news_by_symbol = {
        t["symbol"]: fetch_ticker_news(t["name"], max_per_ticker) for t in tickers
    }

    logger.info("[%s] Gemini APIで分析中...", label)
    return analyze_fn(tickers, price_stats_by_symbol, news_by_symbol, macro_news)


def main() -> None:
    load_dotenv(_ROOT / ".env")

    watchlist = _load_yaml(_CONFIG_DIR / "watchlist.yaml")
    candidate_pool = _load_yaml(_CONFIG_DIR / "candidate_pool.yaml")
    portfolio = _load_yaml(_CONFIG_DIR / "portfolio.yaml")
    news_config = _load_yaml(_CONFIG_DIR / "news_sources.yaml")

    tickers = watchlist.get("tickers", [])
    candidates = candidate_pool.get("candidates", [])
    holdings = portfolio.get("holdings", []) if portfolio else []

    if not tickers:
        raise RuntimeError("config/watchlist.yaml に銘柄が1件も登録されていません。")

    max_per_ticker = news_config.get("max_articles_per_ticker", 5)

    logger.info("マクロ経済ニュースを取得中...")
    macro_news = fetch_macro_news(
        news_config.get("macro_queries", []),
        news_config.get("max_articles_per_query", 3),
    )

    watchlist_results = _analyze_group("ウォッチリスト", tickers, max_per_ticker, macro_news)
    candidate_results = _analyze_group("ハイリスク候補", candidates, max_per_ticker, macro_news)
    portfolio_results = _analyze_group(
        "保有銘柄", holdings, max_per_ticker, macro_news, analyze_fn=analyze_all_holdings
    )

    logger.info("レポートを生成中...")
    generate_report(
        watchlist_results,
        candidate_results,
        portfolio_results,
        macro_news,
        _TEMPLATES_DIR,
        _OUTPUT_PATH,
    )

    logger.info("完了しました: %s", _OUTPUT_PATH)


if __name__ == "__main__":
    main()
