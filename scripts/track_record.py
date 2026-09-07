"""AIの過去の判定（買い候補・売り候補・売却検討）が、その後の値動きと
一致していたかを追跡し、的中率として集計するモジュール。

判定日から30日後の株価と比較し、判定の方向（上昇を期待/下落を期待）と
実際の変化率の符号が一致していれば「的中」、逆であれば「不的中」とする。
変化率が±1%以内の場合は判定なし（様子見扱い）として、的中率の集計対象から除外する。

検証期間はもともと7日だったが、プロンプト側で「3ヶ月・6ヶ月・1年の中長期トレンドを
判断の主たる根拠にする」よう指示しているのに対し、7日後の値動きで正解/不正解を
判定するのは物差しとして短すぎ、短期的なノイズで「不正解」扱いになりやすかった。
3ヶ月に合わせると検証に時間がかかりすぎるため、両者の中間として30日を採用している。

「様子見」「保有継続」は方向性のある予測ではないため、そもそも記録しない。

過去の全件を保持すると際限なく増え続けるため、確定した結果は
種別ごと・テーマごと・確信度ごとの件数（summary系）にのみ集約し、
個別の履歴は直近20件（recent_resolved）だけを残す。

テーマ別・確信度別の内訳を別に持つのは、AIに「どのテーマ／どの確信度帯で
外れやすいか」という、より具体的な傾向を伝えるため（種別ごとの的中率だけでは
「なぜ外れやすいか」が分からず、判断の改善につながりにくい）。

さらに、同一銘柄（同一ポジション）で判定が連続して外れ続けているケースを検知するため、
銘柄ごとの直近の連続的中/連続不的中の回数（streak_by_position）も別途保持する。
テーマ別の的中率は複数銘柄の平均であるため、「特定の1銘柄だけが繰り返し外れている」
という状況を薄めてしまう。個別銘柄の連続外れをAIに直接伝えることで、
「同じ理由付けで同じ判定を繰り返す」ことをより避けやすくする狙い。
recent_resolvedは件数上限があり銘柄をまたいですぐに押し出されてしまうため、
連続回数はrecent_resolvedから再集計するのではなく、専用のカウンタとして
resolve_predictions実行のたびに更新・永続化する。
"""

import datetime as dt
import json
import logging
from pathlib import Path
from zoneinfo import ZoneInfo

from history import build_key

logger = logging.getLogger(__name__)

_JST = ZoneInfo("Asia/Tokyo")

_NEUTRAL_BAND_PCT = 1.0
_RESOLVE_AFTER_DAYS = 30
_RECENT_RESOLVED_LIMIT = 20

_BULLISH = {"買い候補"}
_BEARISH = {"売り候補", "売却検討"}
_TRACKED = _BULLISH | _BEARISH

# |スコア|がこの値以上の判定を「確信度が高い」とみなす（売却検討はスコアが無いため対象外）。
# 実際に出力されるスコアは25〜65程度に収まることが多く、80では「高確信度」がほぼ
# 出現せず区分が機能しなかったため、60に引き下げている。
HIGH_CONFIDENCE_ABS_SCORE = 60

# 銘柄ごとの連続的中/不的中を「傾向」としてプロンプトに含める最低回数。
# 1回だけでは既存の反省機能（前回1件の振り返り）と情報が重複するため、2回以上を対象にする。
MIN_STREAK_FOR_PROMPT = 2

_EMPTY_RECORD = {
    "pending": [],
    "summary": {},
    "recent_resolved": [],
    "summary_by_theme": {},
    "summary_by_confidence": {},
    "streak_by_position": {},
}


def _empty_record() -> dict:
    return {k: ([] if isinstance(v, list) else {}) for k, v in _EMPTY_RECORD.items()}


def _today() -> dt.date:
    return dt.datetime.now(tz=_JST).date()


def _prediction_id(group: str, symbol: str, purchase_date, date_str: str) -> str:
    base = f"{group}:{symbol}:{purchase_date}" if group == "holding" else f"{group}:{symbol}"
    return f"{base}:{date_str}"


def load_track_record(path: Path) -> dict:
    if not path.exists():
        return _empty_record()
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        logger.exception("的中率記録の読み込みに失敗したため、記録なしとして続行します: %s", path)
        return _empty_record()
    for key, default in _EMPTY_RECORD.items():
        data.setdefault(key, [] if isinstance(default, list) else {})
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

        score = r.get("score")
        record["pending"].append(
            {
                "id": pred_id,
                "group": group,
                "symbol": r["symbol"],
                "name": r.get("name", r["symbol"]),
                "recommendation": recommendation,
                "theme": r.get("theme"),
                "score": score if isinstance(score, int) else None,
                # 保有銘柄はsymbolだけでは一意にならない（同じ銘柄を複数回買った場合）ため、
                # build_key()での照合（連続的中/不的中の集計キー）にpurchase_dateが必要。
                "purchase_date": r.get("purchase_date"),
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


def _update_streak(record: dict, position_key: str, p: dict, outcome: str) -> None:
    """指定ポジションの連続的中/連続不的中カウンタを更新する（neutralは維持も更新もしない）。"""
    if outcome == "neutral":
        return

    previous = record["streak_by_position"].get(position_key)
    if previous and previous.get("outcome") == outcome:
        count = previous["count"] + 1
    else:
        count = 1

    record["streak_by_position"][position_key] = {
        "outcome": outcome,
        "count": count,
        "symbol": p["symbol"],
        "name": p.get("name"),
        "theme": p.get("theme"),
    }


def resolve_predictions(record: dict, current_prices: dict[str, float]) -> None:
    """判定から30日経過した保留中の予測を、現在の株価と照らして確定させる。

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

        theme = p.get("theme")
        if theme:
            theme_bucket = record["summary_by_theme"].setdefault(
                theme, {"correct": 0, "incorrect": 0, "neutral": 0}
            )
            theme_bucket[outcome] += 1

        score = p.get("score")
        if isinstance(score, int):
            confidence_label = "high" if abs(score) >= HIGH_CONFIDENCE_ABS_SCORE else "normal"
            confidence_bucket = record["summary_by_confidence"].setdefault(
                confidence_label, {"correct": 0, "incorrect": 0, "neutral": 0}
            )
            confidence_bucket[outcome] += 1

        position_key = build_key(p["group"], p["symbol"], p.get("purchase_date"))
        _update_streak(record, position_key, p, outcome)

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


def _bucketed_breakdown(buckets: dict, label_key: str) -> list[dict]:
    """{ラベル: {correct, incorrect, neutral}} 形式の集計を、的中率つきのリストに変換する。"""
    breakdown = []
    for label, counts in buckets.items():
        correct = counts.get("correct", 0)
        incorrect = counts.get("incorrect", 0)
        neutral = counts.get("neutral", 0)
        scored = correct + incorrect
        breakdown.append(
            {
                label_key: label,
                "correct": correct,
                "incorrect": incorrect,
                "neutral": neutral,
                "accuracy_pct": (correct / scored * 100) if scored else None,
                "sample_size": scored,
            }
        )
    breakdown.sort(key=lambda b: b[label_key])
    return breakdown


def build_accuracy_summary(record: dict) -> dict:
    """レポート表示用に、判定種別・テーマ別・確信度別、および全体の的中率を集計する。"""
    breakdown = _bucketed_breakdown(record["summary"], "recommendation")
    theme_breakdown = _bucketed_breakdown(record["summary_by_theme"], "theme")
    confidence_breakdown = _bucketed_breakdown(record["summary_by_confidence"], "confidence")

    total_correct = sum(b["correct"] for b in breakdown)
    total_incorrect = sum(b["incorrect"] for b in breakdown)
    total_neutral = sum(b["neutral"] for b in breakdown)
    total_scored = total_correct + total_incorrect

    return {
        "overall_accuracy_pct": (total_correct / total_scored * 100) if total_scored else None,
        "overall_sample_size": total_scored,
        "overall_neutral": total_neutral,
        "pending_count": len(record["pending"]),
        "breakdown": breakdown,
        "theme_breakdown": theme_breakdown,
        "confidence_breakdown": confidence_breakdown,
        "recent_resolved": record["recent_resolved"],
        "streaks": record["streak_by_position"],
    }


def get_streak(accuracy_summary: dict | None, group: str, symbol: str, purchase_date: str | None = None) -> dict | None:
    """特定の銘柄（ポジション）の現在の連続的中/連続不的中を取得する。データが無ければNone。"""
    if not accuracy_summary:
        return None
    return accuracy_summary.get("streaks", {}).get(build_key(group, symbol, purchase_date))
