"""答え合わせ済みの判定を、指数比（同じ期間の日経平均・S&P500と比べて上か下か）でも採点し直す（1回だけ使う）。

指数比の採点は 2026-11-02 以降の判定からしか記録していなかったため、2026-11-25 に、それより前に
答え合わせした判定も採点して summary_relative / summary_relative_by_theme に加えた。

- どの判定がいつ答え合わせされたかは、data/track_record.json の git の履歴から調べる
  （pending から消えた更新の日＝答え合わせの日。朝の実行なので、その日の前の営業日の終値で採点されている）
- 判定時の銘柄の価格は記録済みの price_at_prediction、答え合わせのときの価格と指数は yfinance の終値
- 2回かけると二重に数えるので、record["relative_backfill"] があるときは何もしない

使い方: python scripts/backfill_relative_accuracy.py
"""

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yaml
import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from track_record import (  # noqa: E402
    _TRACKED,
    _add_outcome,
    _classify,
    benchmark_for,
    load_track_record,
    save_track_record,
)

ROOT = Path(__file__).resolve().parent.parent
RECORD_PATH = ROOT / "data" / "track_record.json"
JST = ZoneInfo("Asia/Tokyo")


def config_markets() -> dict[str, str]:
    """今の設定ファイルにある銘柄の market。"""
    def load(name):
        path = ROOT / "config" / name
        return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}) if path.exists() else {}

    markets = {}
    for t in load("watchlist.yaml").get("tickers", []):
        markets[t["symbol"]] = t.get("market", "")
    for t in load("candidate_pool.yaml").get("candidates", []):
        markets[t["symbol"]] = t.get("market", "")
    for t in load("yutai.yaml").get("stocks") or []:
        markets[t["symbol"]] = t.get("market", "JP")
    for s in load("sectors.yaml").get("sectors") or []:
        markets[s["symbol"]] = s.get("market", "JP")
        for m in s.get("members") or []:
            markets.setdefault(m["symbol"], s.get("market", "JP"))
    for h in load("portfolio.yaml").get("holdings") or []:
        markets.setdefault(h["symbol"], h.get("market", ""))
    for f in load("tsumitate_funds.yaml").get("funds") or []:
        markets[f["symbol"]] = f.get("market", "ETF")
    return markets


def resolved_predictions() -> list[tuple[dict, str]]:
    """(判定, 答え合わせの日) の一覧。git の履歴で pending から消えた日を答え合わせの日とする。"""
    log = subprocess.run(
        ["git", "-C", str(ROOT), "log", "--reverse", "--format=%h %aI", "--", "data/track_record.json"],
        capture_output=True, text=True, check=True,
    ).stdout.split("\n")
    previous: dict[str, dict] = {}
    resolved = []
    for line in filter(None, log):
        commit, stamp = line.split()
        day = dt.datetime.fromisoformat(stamp).astimezone(JST).date().isoformat()
        raw = subprocess.run(
            ["git", "-C", str(ROOT), "show", f"{commit}:data/track_record.json"], capture_output=True, check=True,
        ).stdout
        try:
            pending = {p["id"]: p for p in json.loads(raw.decode("utf-8")).get("pending", [])}
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        for pid, p in previous.items():
            # 答え合わせの日より前に消えたもの（手で消した等）は数えない
            if pid not in pending and day >= p["resolve_after"]:
                resolved.append((p, day))
        previous = pending
    return resolved


def close_before(series: pd.Series, date_str: str) -> float | None:
    earlier = series[series.index < pd.Timestamp(date_str)]
    return float(earlier.iloc[-1]) if len(earlier) else None


def main() -> None:
    record = load_track_record(RECORD_PATH)
    if record.get("relative_backfill"):
        print("すでに採点し直し済みです:", record["relative_backfill"])
        return

    markets = config_markets()
    items = []
    for p, day in resolved_predictions():
        if p.get("recommendation") not in _TRACKED or p.get("benchmark_price_at_prediction"):
            continue  # 指数の値が記録済みの判定は、答え合わせのときに指数比でも採点されている
        index = benchmark_for(p["symbol"], p.get("group", ""), markets)
        if index:
            items.append((p, day, index))

    symbols = sorted({p["symbol"] for p, _, _ in items} | {"^N225", "^GSPC"})
    parts = [
        yf.download(symbols[i:i + 80], start="2026-06-01", auto_adjust=False, progress=False)["Close"]
        for i in range(0, len(symbols), 80)
    ]
    close = pd.concat(parts, axis=1, sort=True)
    close.index = pd.to_datetime(close.index).tz_localize(None)

    counted, skipped = 0, 0
    for p, day, index in items:
        stock = close[p["symbol"]].dropna() if p["symbol"] in close.columns else pd.Series(dtype=float)
        bench = close[index].dropna()
        price_now = close_before(stock, day)
        index_then, index_now = close_before(bench, p["date"]), close_before(bench, day)
        if not (price_now and index_then and index_now and p.get("price_at_prediction")):
            skipped += 1
            continue
        change = (price_now / p["price_at_prediction"] - 1) * 100
        excess = change - (index_now / index_then - 1) * 100
        outcome = _classify(p["recommendation"], excess)
        _add_outcome(record["summary_relative"], p["recommendation"], outcome)
        if p.get("theme"):
            _add_outcome(record["summary_relative_by_theme"], p["theme"], outcome)
        counted += 1

    record["relative_backfill"] = {
        "date": dt.datetime.now(tz=JST).date().isoformat(),
        "count": counted,
        "skipped": skipped,
        "note": "2026-11-02 より前の判定で、答え合わせ済みのものを指数比で採点し直した（scripts/backfill_relative_accuracy.py）",
    }
    save_track_record(RECORD_PATH, record)
    print(f"採点し直した判定 {counted} 件（株価が取れず飛ばした {skipped} 件）")
    print(json.dumps(record["summary_relative"], ensure_ascii=False))


if __name__ == "__main__":
    main()
