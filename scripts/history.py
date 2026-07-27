"""前回分析結果を次回実行時の「振り返り」に使うための最小限の永続化ヘルパー。

保存するのは各銘柄の最新1件のみ（履歴の蓄積はしない）。振り返りに使うのは
常に「前回」の1件で十分なため、リスト化はしない。
"""

import datetime as dt
import json
import logging
from pathlib import Path
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_JST = ZoneInfo("Asia/Tokyo")


def build_key(group: str, symbol: str, purchase_date: str | None = None) -> str:
    if group == "holding":
        return f"holding:{symbol}:{purchase_date}"
    return f"{group}:{symbol}"


def today_str() -> str:
    return dt.datetime.now(tz=_JST).date().isoformat()


def load_history(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        logger.exception("履歴ファイルの読み込みに失敗したため、履歴なしとして続行します: %s", path)
        return {}


def save_history(path: Path, history: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")


def apply_group_results(history: dict, group: str, results: list[dict]) -> None:
    """今回の分析結果でhistoryを更新する（in-place）。

    分析失敗した銘柄は前回のエントリをそのまま残し（1回の失敗で振り返りの
    連続性を失わないため）、今回のリストに存在しない銘柄のエントリは削除する
    （config/*.yamlから外した銘柄を自動的に忘れる）。
    """
    seen_keys = set()
    for r in results:
        key = build_key(group, r["symbol"], r.get("purchase_date"))
        seen_keys.add(key)
        if r.get("analysis_failed"):
            continue
        price_stats = r.get("price_stats") or {}
        history[key] = {
            "date": today_str(),
            "recommendation": r.get("recommendation"),
            "score": r.get("score"),
            "reasoning": r.get("reasoning"),
            "latest_close": price_stats.get("latest_close"),
        }

    prefix = f"{group}:"
    for key in [k for k in history if k.startswith(prefix) and k not in seen_keys]:
        del history[key]
