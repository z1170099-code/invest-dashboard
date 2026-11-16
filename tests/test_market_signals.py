import datetime as dt

import pandas as pd

import fetch_prices as fp
import market_signals as ms

TODAY = dt.date(2026, 11, 17)


def _bench(latest, ma_50, ma_200, daily=None, change_1m=None):
    return {"latest_close": latest, "latest_date": "2026-11-14", "ma_50": ma_50, "ma_200": ma_200,
            "change_1m_pct": change_1m, "daily_closes": daily or {}}


def test_market_regime_labels_each_index():
    state = ms.market_regime({
        "^N225": _bench(48000, 49000, 50000, change_1m=-4.0),  # 下
        "^GSPC": _bench(6900, 6800, 6600),  # 上
    })
    keys = {r["name"]: (r["key"], r["label"]) for r in state["indexes"]}
    assert keys == {"日経平均": ("down", "下落基調"), "S&P500": ("up", "上昇基調")}
    assert state["overall"] == "down" and "日経平均が下落基調" in state["message"]
    assert round(state["indexes"][0]["gap_200_pct"], 1) == -4.0

    up = ms.market_regime({"^N225": _bench(52000, 51000, 50000), "^GSPC": _bench(6900, 6800, 6600)})
    assert up["overall"] == "up"
    mixed = ms.market_regime({"^N225": _bench(51000, 49000, 50000), "^GSPC": _bench(6900, 6800, 6600)})
    assert mixed["overall"] == "mixed" and mixed["indexes"][0]["label"] == "方向がはっきりしない"
    assert ms.market_regime({}) is None


def test_buy_call_performance_by_group_against_index():
    benchmarks = {
        # 判定時の指数は、判定日より前の最後の終値（11/02 の判定なら 10/31）
        "^N225": _bench(44000, 0, 0, daily={"2026-10-30": 39000, "2026-10-31": 40000, "2026-11-02": 41000}),
        "^GSPC": _bench(6600, 0, 0),
    }
    pending = [
        # 業種の代表銘柄: +20%、日経平均は 40000→44000 で +10% なので、指数との差は +10%
        {"group": "sector_member", "symbol": "4502.T", "recommendation": "買い候補", "score": 30,
         "date": "2026-11-02", "price_at_prediction": 100},
        # 記録済みの指数の価格があればそれを使う: 株 -10%、S&P500 6000→6600 で +10% → 差 -20%
        {"group": "candidate", "symbol": "AMD", "recommendation": "買い候補", "score": 25, "date": "2026-11-02",
         "price_at_prediction": 200, "benchmark_symbol": "^GSPC", "benchmark_price_at_prediction": 6000},
        # 数えないもの: スコア不足・売り候補・暗号資産・7日たっていない・価格が無い
        {"group": "candidate", "symbol": "PLTR", "recommendation": "買い候補", "score": 19, "date": "2026-11-02", "price_at_prediction": 1},
        {"group": "candidate", "symbol": "SOUN", "recommendation": "売り候補", "score": -30, "date": "2026-11-02", "price_at_prediction": 1},
        {"group": "candidate", "symbol": "BTC-USD", "recommendation": "買い候補", "score": 30, "date": "2026-11-02", "price_at_prediction": 1},
        {"group": "candidate", "symbol": "TSM", "recommendation": "買い候補", "score": 30, "date": "2026-11-12", "price_at_prediction": 1},
        {"group": "watchlist", "symbol": "NOPRICE", "recommendation": "買い候補", "score": 30, "date": "2026-11-02", "price_at_prediction": 1},
    ]
    prices = {"4502.T": 120, "AMD": 180, "PLTR": 9, "SOUN": 9, "BTC-USD": 9, "TSM": 9}
    rows = ms.buy_call_performance(pending, prices, benchmarks, TODAY)
    by = {r["group"]: r for r in rows}
    assert list(by) == ["sector_member", "candidate"]  # 表示順は SUMMARY_GROUPS どおり
    assert by["sector_member"]["n"] == 1 and round(by["sector_member"]["avg_return_pct"], 1) == 20.0
    assert round(by["sector_member"]["avg_excess_pct"], 1) == 10.0 and by["sector_member"]["beat_index_pct"] == 100
    assert by["candidate"]["n"] == 1 and round(by["candidate"]["avg_excess_pct"], 1) == -20.0
    assert by["candidate"]["label"] == "ハイリスク候補"


def test_add_moving_averages():
    idx = pd.date_range("2026-01-01", periods=210, freq="B")
    closes = pd.Series(range(1, 211), index=idx, dtype=float)
    stats = {}
    fp.add_moving_averages(stats, closes)
    assert stats["ma_50"] == sum(range(161, 211)) / 50
    assert stats["ma_200"] == sum(range(11, 211)) / 200
    assert len(stats["daily_closes"]) == 210 and stats["daily_closes"][idx[-1].date().isoformat()] == 210.0

    short = {}
    fp.add_moving_averages(short, closes.head(60))
    assert short["ma_200"] is None and short["ma_50"] is not None
