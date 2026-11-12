"""保有銘柄ごとの「1回だけの売却合図」。

portfolio.yaml の保有銘柄に sell_once を書くと、毎回の実行で次の条件を確かめる。

- 含み益が min_gain_pct（既定+3%）以上
- かつ、AIが「売却検討」と判定した、または期限（deadline）まで final_days（既定14日）以内

条件を満たした最初の日に1回だけ合図を出し、data/sell_signals.json に記録する。一度出した合図は
その後値下がりしても取り消さない（日によって判定が揺れると、いつ売ればよいか決められないため）。
含み損のときと取得単価が未登録のときは合図を出さない（損切りはしない方針）。期限を過ぎても
条件を満たすまで判定を続ける。

min_gain_pct の余裕は、投資信託が注文した日の夕方に値段の決まる仕組み（ブラインド方式）のため。
朝の判定時点では前の営業日の基準価額しか分からず、売る日の値動きで含み益が消えることがある。
"""

import datetime as dt
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_MIN_GAIN_PCT = 3.0
DEFAULT_FINAL_DAYS = 14


def load_signals(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.exception("売却合図の記録を読めませんでした: %s", path)
        return {}


def save_signals(path: Path, signals: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(signals, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def signal_key(result: dict) -> str:
    return f"{result['symbol']}|{result.get('purchase_date') or ''}"


def evaluate_sell_once(result: dict, signals: dict, today: dt.date) -> dict | None:
    """sell_once の条件を確かめ、状態を返す。新しく合図を出すときは signals に記録する。

    status は signaled（合図を出した）・waiting_ai（含み益は十分だがAIが保有継続）・
    below_margin（含み益が余裕に届かない）・loss（含み損）・no_cost（取得単価が未登録）のどれか。
    """
    rule = result.get("sell_once")
    if not rule:
        return None
    deadline = None
    if rule.get("deadline"):
        try:
            deadline = dt.date.fromisoformat(str(rule["deadline"]))
        except ValueError:
            logger.warning("sell_once の deadline が日付として読めません: %s", rule["deadline"])
    state = {
        "min_gain_pct": float(rule.get("min_gain_pct", DEFAULT_MIN_GAIN_PCT)),
        "final_days": int(rule.get("final_days", DEFAULT_FINAL_DAYS)),
        "deadline": deadline.isoformat() if deadline else None,
        "days_left": (deadline - today).days if deadline else None,
        "new": False,
    }

    key = signal_key(result)
    if key in signals:
        return {**state, "status": "signaled", **signals[key]}

    gain = result.get("gain_loss_pct")
    if not isinstance(gain, (int, float)):
        return {**state, "status": "no_cost"}
    state["gain_pct"] = round(float(gain), 2)
    if gain <= 0:
        return {**state, "status": "loss"}
    if gain < state["min_gain_pct"]:
        return {**state, "status": "below_margin"}

    # 分析に失敗して前回の判定を表示している日は、AIの判定を合図の根拠にしない
    ai_sell = result.get("recommendation") == "売却検討" and not result.get("analysis_failed")
    near_deadline = state["days_left"] is not None and state["days_left"] <= state["final_days"]
    if not (ai_sell or near_deadline):
        return {**state, "status": "waiting_ai"}

    price_stats = result.get("price_stats") or {}
    record = {
        "date": today.isoformat(),
        "price_date": price_stats.get("latest_date"),
        "price": price_stats.get("latest_close"),
        "gain_pct": state["gain_pct"],
        "reason": "ai" if ai_sell else "deadline",
    }
    signals[key] = record
    logger.info("売却の合図を出しました: %s（含み益%+.2f%%）", result["symbol"], gain)
    return {**state, "status": "signaled", **record, "new": True}


def describe(state: dict | None) -> dict | None:
    """画面とメールに出す見出しと説明文を作る。"""
    if not state:
        return None
    min_gain = state["min_gain_pct"]
    deadline = state.get("deadline")
    final_days = state["final_days"]
    gain = state.get("gain_pct")
    status = state["status"]

    if status == "signaled":
        date = dt.date.fromisoformat(state["date"])
        reason = (
            "AIが値下がりの材料ありと判定した" if state.get("reason") == "ai"
            else f"期限まで{final_days}日を切った"
        )
        price_date = state.get("price_date") or "前の営業日"
        label = f"売却の合図 {date.month}/{date.day}"
        message = (
            f"{date.month}/{date.day}に売却の条件を満たしました。{price_date}の価格で含み益{gain:+.1f}%"
            f"（条件は+{min_gain:g}%以上）で、{reason}ためです。この合図は1回だけで、取り消しません。"
        )
        return {"status": status, "label": label, "message": message, "signaled": True}

    if status == "no_cost":
        message = "取得単価が未登録のため、利益が出ているか判定できません。合図はまだ出しません。"
    elif status == "loss":
        message = f"含み損{gain:+.1f}%です。損切りしない設定なので、合図は出していません。"
    elif status == "below_margin":
        message = (
            f"含み益{gain:+.1f}%です。売る日の値動きで損に変わらないよう、+{min_gain:g}%以上になるまで待っています。"
        )
    else:
        message = (
            f"含み益{gain:+.1f}%で、条件の+{min_gain:g}%以上は満たしています。"
            "AIがまだ値上がりの余地ありと判定しているため、合図は出していません。"
        )
        if deadline:
            message += f"期限の{final_days}日前からは、+{min_gain:g}%以上なら合図を出します。"
    days_left = state.get("days_left")
    if days_left is not None and days_left < 0:
        message += f"期限（{deadline}）は過ぎましたが、損切りしない設定なので、条件を満たすまで判定を続けます。"
    elif deadline:
        message += f"期限は{deadline}（あと{days_left}日）です。"
    return {"status": status, "label": "売却の合図待ち", "message": message, "signaled": False}
