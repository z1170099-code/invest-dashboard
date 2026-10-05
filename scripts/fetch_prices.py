"""yfinanceを使って株価データを取得し、変化率などの指標を計算する。"""

import logging

import yfinance as yf

logger = logging.getLogger(__name__)


def fetch_price_stats(symbol: str) -> dict | None:
    """指定した銘柄の価格統計を取得する。取得できない場合はNoneを返す。"""
    try:
        # 1年騰落率の計算に最低252営業日分必要なため、境界での不足を避けて2年分取得する。
        history = yf.Ticker(symbol).history(period="2y", interval="1d")
    except Exception:
        logger.exception("価格取得に失敗しました: %s", symbol)
        return None

    if history is None or history.empty:
        logger.warning("価格データが空でした: %s", symbol)
        return None

    closes = history["Close"].dropna()
    if len(closes) < 2:
        logger.warning("価格データが不足しています: %s", symbol)
        return None

    latest = closes.iloc[-1]

    def pct_change_over(days: int) -> float | None:
        if len(closes) <= days:
            return None
        past = closes.iloc[-(days + 1)]
        if past == 0:
            return None
        return (latest / past - 1) * 100

    daily_returns = closes.pct_change().dropna()
    recent_returns = daily_returns.tail(20)
    volatility = float(recent_returns.std() * 100) if not recent_returns.empty else None

    one_year = closes.tail(252) if len(closes) >= 2 else closes
    high_52w = float(one_year.max())
    low_52w = float(one_year.min())
    off_high_pct = (latest / high_52w - 1) * 100 if high_52w else None

    return {
        "symbol": symbol,
        "latest_close": float(latest),
        "latest_date": closes.index[-1].date().isoformat(),
        "change_1d_pct": pct_change_over(1),
        "change_1w_pct": pct_change_over(5),
        "change_1m_pct": pct_change_over(21),
        "change_3m_pct": pct_change_over(63),
        "change_6m_pct": pct_change_over(126),
        "change_1y_pct": pct_change_over(252),
        "volatility_20d_pct": volatility,
        "high_52w": high_52w,
        "low_52w": low_52w,
        "off_52w_high_pct": off_high_pct,
    }


def fetch_all_price_stats(tickers: list[dict]) -> dict[str, dict | None]:
    """ウォッチリストの全銘柄について価格統計を取得する。

    戻り値は symbol -> stats（取得失敗時はNone）の辞書。
    1銘柄の失敗が他の銘柄の処理を止めないようにする。
    """
    results: dict[str, dict | None] = {}
    for ticker in tickers:
        symbol = ticker["symbol"]
        results[symbol] = fetch_price_stats(symbol)
    return results


# 市場ごとの比較対象ベンチマーク指数。ETF・暗号資産など対応する指数が無い市場は対象外。
_BENCHMARK_BY_MARKET = {
    "US": "^GSPC",
    "JP": "^N225",
}


def fetch_benchmarks() -> dict[str, dict | None]:
    """市場ごとのベンチマーク指数（米国:S&P500, 日本:日経225）の価格統計を取得する。

    個別銘柄が「市場全体と一緒に動いただけ」なのか「銘柄固有の動き」なのかをAIが
    区別できるようにするための比較対象。複数銘柄で共有するため、銘柄ごとではなく
    一度だけ取得する。
    """
    symbols = set(_BENCHMARK_BY_MARKET.values())
    return {symbol: fetch_price_stats(symbol) for symbol in symbols}


def attach_relative_performance(
    price_stats: dict | None, market: str | None, benchmarks: dict[str, dict | None]
) -> None:
    """price_statsに、同期間のベンチマーク比の相対パフォーマンス（change_*_pct_relative）を追加する。

    例えば「1ヶ月で-5%」という値動きも、同期間の市場全体が-4%なら「市場並み」、
    市場が+2%なら「銘柄固有の弱さ」と、意味が大きく変わる。この違いをAIに伝えるための
    補助情報であり、対応するベンチマークが無い市場（ETF・暗号資産など）は何もしない。
    """
    if not price_stats or not market:
        return
    benchmark_symbol = _BENCHMARK_BY_MARKET.get(market)
    benchmark = benchmarks.get(benchmark_symbol) if benchmark_symbol else None
    if not benchmark:
        return

    price_stats["benchmark_symbol"] = benchmark_symbol
    for period in ("1w", "1m", "3m", "6m", "1y"):
        key = f"change_{period}_pct"
        ticker_change = price_stats.get(key)
        benchmark_change = benchmark.get(key)
        if isinstance(ticker_change, (int, float)) and isinstance(benchmark_change, (int, float)):
            price_stats[f"{key}_relative"] = ticker_change - benchmark_change
