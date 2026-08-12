"""AIの過去の判定（買い候補・売り候補・売却検討）が、その後の値動きと
一致していたかを追跡し、的中率として集計するモジュール。

判定日から7日後の株価と比較し、判定の方向（上昇を期待/下落を期待）と
実際の変化率の符号が一致していれば「的中」、逆であれば「不的中」とする。
変化率が±1%以内の場合は判定なし（様子見扱い）として、的中率の集計対象から除外する。

「様子見」「保有継続」は方向性のある予測ではないため、そもそも記録しない。

過去の全件を保持すると際限なく増え続けるため、確定した結果は
種別ごとの件数（summary）にのみ集約し、個別の履歴は直近20件（recent_resolved）だけを残す。
"""

import datetime as dt
import json
import logging
from pathlib import Path
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_JST = ZoneInfo("Asia/Tokyo")

_NEUTRAL_BAND_PCT = 1.0
_RESOLVE_AFTER_DAYS = 7
_RECENT_RESOLVED_LIMIT = 20

_BULLISH = {"買い候補"}
_BEARISH = {"売り候補", "売却検討"}
_TRACKED = _BULLISH | _BEARISH


def _today() -> dt.date:
    return dt.datetime.now(tz=_JST).date()


def _prediction_id(group: str, symbol: str, purchase_date, date_str: str) -> str:
    base = f"{group}:{symbol}:{purchase_date}" if group == "holding" else f"{group}:{symbol}"
    return f"{base}:{date_str}"


def load_track_record(path: Path) -> dict:
    if not path.exists():
        return {"pending": [], "summary": {}, "recent_resolved": []}
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        logger.exception("的中率記録の読み込みに失敗したため、記録なしとして続行します: %s", path)
        return {"pending": [], "summary": {}, "recent_resolved": []}
    data.setdefault("pending", [])
    data.setdefault("summary", {})
    data.setdefault("recent_resolved", [])
    return data


def save_track_record(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")


def record_predictions(record: dict, group: str, results: list[dict]) -> None:
    """今回の分析結果のうち、方向性のある判定（買い候補・売り候補・売却検討）を保留リストに追加する。"""
    today_str = _today().isoformat()
    existing_ids = {p["id"] for p in record["pending"]}

    for r in results:
        recommendation = r.get("recommendation")
        if recommendation not in _TRACKED or r.get("analysis_failed"):
            continue
        price_stats = r.get("price_stats") or {}
        price = price_stats.get("latest_close")
        if not isinstance(price, (int, float)):
            continue

        pred_id = _prediction_id(group, r["symbol"], r.get("purchase_date"), today_str)
        if pred_id in existing_ids:
            continue

        record["pending"].append(
            {
                "id": pred_id,
                "group": group,
                "symbol": r["symbol"],
                "name": r.get("name", r["symbol"]),
                "recommendation": recommendation,
                "date": today_str,
                "price_at_prediction": price,
                "resolve_after": (_today() + dt.timedelta(days=_RESOLVE_AFTER_DAYS)).isoformat(),
            }
        )


def _classify(recommendation: str, change_pct: float) -> str:
    if recommendation in _BULLISH:
        if change_pct > _NEUTRAL_BAND_PCT:
            return "correct"
        if change_pct < -_NEUTRAL_BAND_PCT:
            return "incorrect"
        return "neutral"
    # _BEARISH（売り候補・売却検討）
    if change_pct < -_NEUTRAL_BAND_PCT:
        return "correct"
    if change_pct > _NEUTRAL_BAND_PCT:
        return "incorrect"
    return "neutral"


def resolve_predictions(record: dict, current_prices: dict[str, float]) -> None:
    """判定から7日経過した保留中の予測を、現在の株価と照らして確定させる。

    current_prices: symbol -> 最新終値 の辞書（今回の実行で価格取得できた銘柄のみ）。
    対象銘柄が今回のリストから外れて価格が取得できない場合は、取得できるまで保留し続ける。
    """
    today = _today()
    still_pending = []

    for p in record["pending"]:
        price_now = current_prices.get(p["symbol"])
        resolve_after = dt.date.fromisoformat(p["resolve_after"])
        if today < resolve_after or not isinstance(price_now, (int, float)):
            still_pending.append(p)
            continue

        price_then = p["price_at_prediction"]
        change_pct = (price_now / price_then - 1) * 100 if price_then else 0.0
        outcome = _classify(p["recommendation"], change_pct)

        bucket = record["summary"].setdefault(
            p["recommendation"], {"correct": 0, "incorrect": 0, "neutral": 0}
        )
        bucket[outcome] += 1

        record["recent_resolved"].insert(
            0,
            {
                **p,
                "resolved_date": today.isoformat(),
                "price_at_resolution": price_now,
                "change_pct": change_pct,
                "outcome": outcome,
            },
        )

    record["pending"] = still_pending
    record["recent_resolved"] = record["recent_resolved"][:_RECENT_RESOLVED_LIMIT]


def build_accuracy_summary(record: dict) -> dict:
    """レポート表示用に、判定種別ごと・全体の的中率を集計する。"""
    breakdown = []
    total_correct = 0
    total_incorrect = 0
    total_neutral = 0

    for recommendation, counts in record["summary"].items():
        correct = counts.get("correct", 0)
        incorrect = counts.get("incorrect", 0)
        neutral = counts.get("neutral", 0)
        scored = correct + incorrect
        breakdown.append(
            {
                "recommendation": recommendation,
                "correct": correct,
                "incorrect": incorrect,
                "neutral": neutral,
                "accuracy_pct": (correct / scored * 100) if scored else None,
                "sample_size": scored,
            }
        )
        total_correct += correct
        total_incorrect += incorrect
        total_neutral += neutral

    breakdown.sort(key=lambda b: b["recommendation"])
    total_scored = total_correct + total_incorrect

    return {
        "overall_accuracy_pct": (total_correct / total_scored * 100) if total_scored else None,
        "overall_sample_size": total_scored,
        "overall_neutral": total_neutral,
        "pending_count": len(record["pending"]),
        "breakdown": breakdown,
        "recent_resolved": record["recent_resolved"],
    }
