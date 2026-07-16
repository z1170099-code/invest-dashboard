"""分析結果からJinja2テンプレートを使って docs/index.html を生成する。"""

import datetime as dt
import logging
from pathlib import Path
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)

_JST = ZoneInfo("Asia/Tokyo")

_STATUS_MAP = {
    "買い候補": {"key": "good", "icon": "▲"},
    "様子見": {"key": "warning", "icon": "●"},
    "売り候補": {"key": "critical", "icon": "▼"},
    "分析失敗": {"key": "muted", "icon": "×"},
}

_HOLDING_STATUS_MAP = {
    "保有継続": {"key": "good", "icon": "●"},
    "売却検討": {"key": "critical", "icon": "▼"},
    "分析失敗": {"key": "muted", "icon": "×"},
}


def _fmt_pct(value) -> str:
    if not isinstance(value, (int, float)):
        return "—"
    arrow = "▲" if value > 0 else ("▼" if value < 0 else "―")
    return f"{arrow} {value:+.2f}%"


def _build_view_model(result: dict, group: str = "") -> dict:
    price_stats = result.get("price_stats") or {}
    status = _STATUS_MAP.get(result.get("recommendation"), _STATUS_MAP["分析失敗"])
    score = result.get("score")
    nisa_eligible = result.get("nisa_growth_eligible")

    return {
        "symbol": result["symbol"],
        "name": result["name"],
        "market": result.get("market", ""),
        "theme": result.get("theme", ""),
        "group": group,
        "recommendation": result.get("recommendation", "分析失敗"),
        "status_key": status["key"],
        "status_icon": status["icon"],
        "score": score,
        "score_display": "—" if score is None else f"{score:+d}",
        "score_bar_pct": 0 if score is None else min(100, abs(score)),
        "reasoning": result.get("reasoning", ""),
        "key_factors": result.get("key_factors") or [],
        "risks": result.get("risks", ""),
        "analysis_failed": result.get("analysis_failed", False),
        "latest_close": price_stats.get("latest_close"),
        "change_1d": _fmt_pct(price_stats.get("change_1d_pct")),
        "change_1w": _fmt_pct(price_stats.get("change_1w_pct")),
        "change_1m": _fmt_pct(price_stats.get("change_1m_pct")),
        "price_available": bool(price_stats),
        "news": result.get("news") or [],
        "nisa_tag": (
            "NISA成長投資枠 対象目安"
            if nisa_eligible
            else ("NISA成長投資枠 対象外の可能性" if nisa_eligible is False else None)
        ),
    }


def _build_holding_view_model(result: dict) -> dict:
    price_stats = result.get("price_stats") or {}
    status = _HOLDING_STATUS_MAP.get(result.get("recommendation"), _HOLDING_STATUS_MAP["分析失敗"])
    gain_loss_pct = result.get("gain_loss_pct")

    return {
        "symbol": result["symbol"],
        "name": result["name"],
        "market": result.get("market", ""),
        "recommendation": result.get("recommendation", "分析失敗"),
        "status_key": status["key"],
        "status_icon": status["icon"],
        "reasoning": result.get("reasoning", ""),
        "key_factors": result.get("key_factors") or [],
        "risks": result.get("risks", ""),
        "analysis_failed": result.get("analysis_failed", False),
        "purchase_date": result.get("purchase_date"),
        "purchase_price": result.get("purchase_price"),
        "latest_close": price_stats.get("latest_close") or result.get("latest_close"),
        "holding_days": result.get("holding_days"),
        "gain_loss_pct": gain_loss_pct,
        "gain_loss_display": _fmt_pct(gain_loss_pct),
        "change_1d": _fmt_pct(price_stats.get("change_1d_pct")),
        "change_1w": _fmt_pct(price_stats.get("change_1w_pct")),
        "change_1m": _fmt_pct(price_stats.get("change_1m_pct")),
        "price_available": bool(price_stats),
        "news": result.get("news") or [],
    }


def _sort_holdings(results: list[dict]) -> list[dict]:
    # 「売却検討」を優先的に上位表示し、同じ推奨内では含み損が大きい順に並べる
    def key(r):
        needs_action = r["recommendation"] != "売却検討"
        gain = r["gain_loss_pct"] if r["gain_loss_pct"] is not None else 0
        return (needs_action, gain)

    return sorted(results, key=key)


def _sort_by_score(results: list[dict]) -> list[dict]:
    # スコアが高い順（分析失敗はNoneなので最後に回す）にソート
    return sorted(
        results,
        key=lambda r: (r.get("score") is None, -(r.get("score") or 0)),
    )


def _build_summary(combined: list[dict]) -> tuple[list[dict], list[dict]]:
    buy_list = sorted(
        (t for t in combined if t["recommendation"] == "買い候補"),
        key=lambda t: -(t["score"] or 0),
    )
    sell_list = sorted(
        (t for t in combined if t["recommendation"] == "売り候補"),
        key=lambda t: (t["score"] or 0),
    )
    return buy_list, sell_list


def generate_report(
    watchlist_results: list[dict],
    candidate_results: list[dict],
    portfolio_results: list[dict],
    macro_news: list[dict],
    templates_dir: Path,
    output_path: Path,
) -> None:
    watchlist_view = [
        _build_view_model(r, group="ウォッチリスト") for r in _sort_by_score(watchlist_results)
    ]
    candidate_view = [
        _build_view_model(r, group="ハイリスク候補") for r in _sort_by_score(candidate_results)
    ]
    holding_view = [
        _build_holding_view_model(r) for r in _sort_holdings(portfolio_results)
    ]
    summary_buy, summary_sell = _build_summary(watchlist_view + candidate_view)

    env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=True)
    template = env.get_template("report.html.jinja")

    generated_at = dt.datetime.now(tz=_JST).strftime("%Y年%m月%d日 %H:%M (JST)")

    html = template.render(
        tickers=watchlist_view,
        candidates=candidate_view,
        holdings=holding_view,
        macro_news=macro_news,
        summary_buy=summary_buy,
        summary_sell=summary_sell,
        generated_at=generated_at,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    logger.info("レポートを生成しました: %s", output_path)
