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
from history import apply_group_results, load_history, save_history
from notify import find_newly_flagged_sell, find_newly_strong_buy, send_notification_email
from track_record import (
    build_accuracy_summary,
    load_track_record,
    record_predictions,
    resolve_predictions,
    save_track_record,
)

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
_HISTORY_PATH = _ROOT / "data" / "analysis_history.json"
_TRACK_RECORD_PATH = _ROOT / "data" / "track_record.json"


def _load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _analyze_group(
    label: str,
    tickers: list[dict],
    max_per_ticker: int,
    macro_news: list[dict],
    history: dict,
    group: str,
    accuracy_summary: dict,
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
    return analyze_fn(
        tickers,
        price_stats_by_symbol,
        news_by_symbol,
        macro_news,
        history=history,
        group=group,
        accuracy_summary=accuracy_summary,
    )


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

    history = load_history(_HISTORY_PATH)
    track_record = load_track_record(_TRACK_RECORD_PATH)
    # 分析前（＝前回実行までに確定した分）の的中率をAIへの入力として使う。
    # 今回の分析結果で確定する分は、今回のプロンプトには間に合わないため次回以降に反映される。
    accuracy_summary_for_prompt = build_accuracy_summary(track_record)

    logger.info("マクロ経済ニュースを取得中...")
    macro_news = fetch_macro_news(
        news_config.get("macro_queries", []),
        news_config.get("max_articles_per_query", 3),
    )

    watchlist_results = _analyze_group(
        "ウォッチリスト",
        tickers,
        max_per_ticker,
        macro_news,
        history,
        "watchlist",
        accuracy_summary_for_prompt,
    )
    candidate_results = _analyze_group(
        "ハイリスク候補",
        candidates,
        max_per_ticker,
        macro_news,
        history,
        "candidate",
        accuracy_summary_for_prompt,
    )
    portfolio_results = _analyze_group(
        "保有銘柄",
        holdings,
        max_per_ticker,
        macro_news,
        history,
        "holding",
        accuracy_summary_for_prompt,
        analyze_fn=analyze_all_holdings,
    )

    all_results = watchlist_results + candidate_results + portfolio_results
    current_prices = {
        r["symbol"]: r["price_stats"]["latest_close"]
        for r in all_results
        if r.get("price_stats") and isinstance(r["price_stats"].get("latest_close"), (int, float))
    }
    resolve_predictions(track_record, current_prices)
    record_predictions(track_record, "watchlist", watchlist_results)
    record_predictions(track_record, "candidate", candidate_results)
    record_predictions(track_record, "holding", portfolio_results)
    # レポート表示用は、今回確定した分も反映した最新の的中率を使う。
    accuracy_summary = build_accuracy_summary(track_record)

    logger.info("レポートを生成中...")
    generate_report(
        watchlist_results,
        candidate_results,
        portfolio_results,
        macro_news,
        accuracy_summary,
        _TEMPLATES_DIR,
        _OUTPUT_PATH,
    )

    # historyを更新（＝前回状態を上書き）する前に、前回との比較で
    # 「新たに売却検討になった銘柄」「新たにスコア70以上の買い候補になった銘柄」を通知する。
    sell_alerts = find_newly_flagged_sell(portfolio_results, history)
    buy_alerts = find_newly_strong_buy(watchlist_results, history, "watchlist") + find_newly_strong_buy(
        candidate_results, history, "candidate"
    )
    send_notification_email(sell_alerts, buy_alerts)

    try:
        apply_group_results(history, "watchlist", watchlist_results)
        apply_group_results(history, "candidate", candidate_results)
        apply_group_results(history, "holding", portfolio_results)
        save_history(_HISTORY_PATH, history)
    except Exception:
        logger.exception("履歴の保存に失敗しましたが、レポートは正常に生成されています。")

    try:
        save_track_record(_TRACK_RECORD_PATH, track_record)
    except Exception:
        logger.exception("的中率記録の保存に失敗しましたが、レポートは正常に生成されています。")

    logger.info("完了しました: %s", _OUTPUT_PATH)


if __name__ == "__main__":
    main()
