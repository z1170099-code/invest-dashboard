"""yfinanceを使って株価データを取得し、変化率などの指標を計算する。

投資信託はyfinanceに無いため、運用会社が公開している基準価額のCSVから同じ形の指標を作る。
"""

import csv
import io
import logging

import pandas as pd
import requests
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

    return _stats_from_closes(symbol, history["Close"].dropna())


def parse_nav_csv(text: str) -> pd.Series:
    """基準価額のCSV（1列目が基準日、2列目が基準価額）を、日付順の終値の系列にする。

    三菱UFJアセットマネジメント（1行目にファンド名）と三井住友トラスト・アセットマネジメント
    （1行目が見出し）のどちらの形でも読めるよう、「基準日」で始まる行を見出しとして探す。
    """
    rows = list(csv.reader(io.StringIO(text)))
    header = next((i for i, r in enumerate(rows) if r and r[0].strip().startswith("基準日")), None)
    if header is None:
        return pd.Series(dtype=float)
    dates, navs = [], []
    for r in rows[header + 1:]:
        if len(r) < 2 or not r[1].strip().replace(",", "").isdigit():
            continue
        try:
            dates.append(pd.Timestamp(r[0].strip().replace("/", "-")))
        except ValueError:
            continue
        navs.append(float(r[1].strip().replace(",", "")))
    return pd.Series(navs, index=pd.DatetimeIndex(dates)).sort_index()


def fetch_fund_nav_stats(symbol: str, nav_csv: str) -> dict | None:
    """投資信託の基準価額（1万口あたり）のCSVを読み、株価と同じ形の価格統計を返す。取得できなければNone。"""
    try:
        response = requests.get(nav_csv, headers={"User-Agent": "Mozilla/5.0 invest-dashboard"}, timeout=30)
        response.raise_for_status()
    except Exception:
        logger.exception("基準価額の取得に失敗しました: %s", symbol)
        return None
    raw = response.content
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp932", errors="replace")
    closes = parse_nav_csv(text)
    # 株価と同じく、1年騰落率の計算に足りる2年分だけ使う
    closes = closes[closes.index >= closes.index.max() - pd.Timedelta(days=730)] if len(closes) else closes
    return _stats_from_closes(symbol, closes)


def _stats_from_closes(symbol: str, closes: pd.Series) -> dict | None:
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

    # レポートの1年チャート用。日次252点×銘柄数だとHTMLが重くなるため、
    # 最新日を起点に5営業日おき（≒週次）に間引く。
    weekly = one_year.iloc[::-1].iloc[::5].iloc[::-1]
    history_1y = [[d.date().isoformat(), round(float(v), 4)] for d, v in weekly.items()]

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
        "history_1y": history_1y,
    }


def fetch_all_price_stats(tickers: list[dict]) -> dict[str, dict | None]:
    """ウォッチリストの全銘柄について価格統計を取得する。

    戻り値は symbol -> stats（取得失敗時はNone）の辞書。
    1銘柄の失敗が他の銘柄の処理を止めないようにする。
    """
    results: dict[str, dict | None] = {}
    for ticker in tickers:
        symbol = ticker["symbol"]
        if ticker.get("nav_csv"):
            results[symbol] = fetch_fund_nav_stats(symbol, ticker["nav_csv"])
        else:
            results[symbol] = fetch_price_stats(symbol)
    return results


# AIに渡す財務・バリュエーションの項目（yfinanceのinfoのキー）。比率の項目は小数（0.12=12%）。
_FUNDAMENTAL_KEYS = (
    "trailingPE", "forwardPE", "priceToBook", "trailingAnnualDividendYield", "revenueGrowth",
    "earningsGrowth", "profitMargins", "returnOnEquity", "recommendationMean", "numberOfAnalystOpinions",
)


def fetch_fundamentals(symbol: str) -> dict | None:
    """PER・PBR・成長率・利益率・アナリスト評価・次回決算日を取得する。取得できなければNone。

    株価の変化率とニュース見出しだけでは割高・割安や業績の勢いが分からないため、AIの判断材料に加える。
    提供元のデータには誤り（分割直後の予想PERなど）が混じることがあるため、プロンプト側で注意書きを添える。
    """
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info or {}
    except Exception:
        logger.exception("財務データの取得に失敗しました: %s", symbol)
        return None

    data = {k: info[k] for k in _FUNDAMENTAL_KEYS if isinstance(info.get(k), (int, float))}
    try:
        dates = (ticker.calendar or {}).get("Earnings Date") or []
        if dates:
            data["next_earnings_date"] = min(dates).isoformat()
    except Exception:
        logger.warning("決算日の取得に失敗しました: %s", symbol)
    return data or None


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
