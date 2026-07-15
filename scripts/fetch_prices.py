"""yfinanceを使って株価データを取得し、変化率などの指標を計算する。"""

import logging

import yfinance as yf

logger = logging.getLogger(__name__)


def fetch_price_stats(symbol: str) -> dict | None:
    """指定した銘柄の価格統計を取得する。取得できない場合はNoneを返す。"""
    try:
        history = yf.Ticker(symbol).history(period="1y", interval="1d")
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
        "change_1d_pct": pct_change_over(1),
        "change_1w_pct": pct_change_over(5),
        "change_1m_pct": pct_change_over(21),
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
