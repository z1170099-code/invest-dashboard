"""売買サマリーに添える2つの判断材料（2026-11-16 追加）。

1. 相場全体の状態: 日経平均とS&P500が200日移動平均より上か下か。
   10/18〜11/06 の判定を集計したところ、スコア上位の銘柄も相場全体の下落に引きずられて
   平均で約4%下がっていた。銘柄の選び方より、相場全体の向きが損益を大きく左右していたため。
   移動平均の上下で相場の向きを見る方法は昔から知られている（Faber, 2007 など）。

2. リストごとの過去の成績: これまでの買い候補（スコア20以上）が、判定してから今までに
   どれだけ動いたか。指数（日本株は日経平均、米国株はS&P500）との差も出す。
   同じ集計で、業種の代表銘柄は指数を上回り、ハイリスク候補・ウォッチリスト・株主優待は
   下回っていたため、どのリストの判定を信用するかの目安にする。
"""

import datetime as dt

INDEXES = (("^N225", "日経平均"), ("^GSPC", "S&P500"))

# サマリーに載せるリスト（track_record の group）と表示名。暗号資産はサマリーから外したので数えない。
SUMMARY_GROUPS = (
    ("sector_member", "業種の代表銘柄"),
    ("watchlist", "ウォッチリスト"),
    ("candidate", "ハイリスク候補"),
    ("yutai", "株主優待"),
)

MIN_SCORE = 20
MIN_AGE_DAYS = 7


def _status(latest: float, ma_50: float | None, ma_200: float | None) -> tuple[str, str]:
    if ma_200 is None or ma_50 is None:
        return "unknown", "データ不足"
    if latest > ma_200 and ma_50 > ma_200:
        return "up", "上昇基調"
    if latest < ma_200 and ma_50 < ma_200:
        return "down", "下落基調"
    return "mixed", "方向がはっきりしない"


def market_regime(benchmarks: dict) -> dict | None:
    """日経平均とS&P500の状態。どちらも取れなければNone。"""
    rows = []
    for symbol, name in INDEXES:
        stats = (benchmarks or {}).get(symbol)
        if not stats or not isinstance(stats.get("latest_close"), (int, float)):
            continue
        latest = stats["latest_close"]
        ma_50, ma_200 = stats.get("ma_50"), stats.get("ma_200")
        key, label = _status(latest, ma_50, ma_200)
        rows.append({
            "symbol": symbol,
            "name": name,
            "latest": latest,
            "latest_date": stats.get("latest_date"),
            "ma_200": ma_200,
            "gap_200_pct": (latest / ma_200 - 1) * 100 if ma_200 else None,
            "change_1m_pct": stats.get("change_1m_pct"),
            "key": key,
            "label": label,
        })
    if not rows:
        return None
    keys = {r["key"] for r in rows}
    if keys == {"up"}:
        overall = "up"
        message = "日経平均・S&P500とも上昇基調です。相場全体が個別株を押し上げやすい時期です。"
    elif "down" in keys:
        overall = "down"
        names = "・".join(r["name"] for r in rows if r["key"] == "down")
        message = (
            f"{names}が下落基調です。この時期は、スコアの高い買い候補も相場全体につられて下がりやすくなります"
            "（10/18〜11/06の判定では、毎日のスコア上位10銘柄も平均で約4%下がりました）。"
        )
    else:
        overall = "mixed"
        message = "相場全体の方向がはっきりしない時期です。上昇基調か下落基調かが決まるまで、値動きが荒くなりやすいです。"
    return {"overall": overall, "message": message, "indexes": rows}


def _market_of(symbol: str) -> str | None:
    if symbol.endswith("-USD"):
        return None  # 暗号資産
    if symbol.endswith(".T"):
        return "^N225"
    if symbol.isdigit():
        return None  # 投資信託（協会コード）
    return "^GSPC"


def _index_close_before(benchmark: dict, date_str: str) -> float | None:
    """判定日より前の最後の終値。判定は朝に行うため、判定時点の株価は前の営業日の終値になる。"""
    closes = benchmark.get("daily_closes") or {}
    earlier = [d for d in closes if d < date_str]
    return closes[max(earlier)] if earlier else None


def buy_call_performance(
    pending: list[dict], current_prices: dict, benchmarks: dict, today: dt.date,
    min_score: int = MIN_SCORE, min_age_days: int = MIN_AGE_DAYS,
) -> list[dict]:
    """リストごとに、スコア min_score 以上の買い候補が判定から今までにどれだけ動いたかを集計する。

    track_record の pending（まだ答え合わせ前の判定）を今の価格で評価する。中長期の判定は180日、
    短期は30日で答え合わせされて pending から消えるため、主に最近の判定と中長期の判定が対象になる。
    """
    cutoff = (today - dt.timedelta(days=min_age_days)).isoformat()
    sums: dict[str, dict] = {}
    for p in pending:
        if p.get("recommendation") != "買い候補" or (p.get("score") or 0) < min_score or p.get("date", "") > cutoff:
            continue
        index_symbol = _market_of(p["symbol"])
        now, then = current_prices.get(p["symbol"]), p.get("price_at_prediction")
        if not index_symbol or not isinstance(now, (int, float)) or not then:
            continue
        ret = (now / then - 1) * 100
        bucket = sums.setdefault(p["group"], {"n": 0, "ret": 0.0, "excess_n": 0, "excess": 0.0, "wins": 0})
        bucket["n"] += 1
        bucket["ret"] += ret
        benchmark = (benchmarks or {}).get(index_symbol) or {}
        index_then = p.get("benchmark_price_at_prediction") or _index_close_before(benchmark, p["date"])
        index_now = benchmark.get("latest_close")
        if isinstance(index_then, (int, float)) and index_then and isinstance(index_now, (int, float)):
            excess = ret - (index_now / index_then - 1) * 100
            bucket["excess_n"] += 1
            bucket["excess"] += excess
            bucket["wins"] += excess > 0

    rows = []
    for group, label in SUMMARY_GROUPS:
        b = sums.get(group)
        if not b:
            continue
        rows.append({
            "group": group,
            "label": label,
            "n": b["n"],
            "avg_return_pct": b["ret"] / b["n"],
            "avg_excess_pct": b["excess"] / b["excess_n"] if b["excess_n"] else None,
            "beat_index_pct": b["wins"] / b["excess_n"] * 100 if b["excess_n"] else None,
        })
    return rows
