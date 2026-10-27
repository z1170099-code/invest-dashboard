"""分析結果からJinja2テンプレートを使って docs/index.html を生成する。"""

import datetime as dt
import json
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

# NISA成長投資枠の上限（2024年からの新NISA制度）。
_NISA_ANNUAL_GROWTH_LIMIT = 2_400_000
_NISA_LIFETIME_GROWTH_LIMIT = 12_000_000

# NISAつみたて投資枠の年間上限、および成長投資枠と合算した生涯の総枠上限。
_NISA_ANNUAL_TSUMITATE_LIMIT = 1_200_000
_NISA_LIFETIME_TOTAL_LIMIT = 18_000_000


_CHART_WIDTH = 600
_CHART_HEIGHT = 140


def _fmt_price(value: float) -> str:
    return f"{value:,.0f}" if value >= 1000 else f"{value:,.2f}"


def _fmt_price_or_dash(value) -> str:
    return _fmt_price(value) if isinstance(value, (int, float)) else "—"


def _build_price_chart(
    price_stats: dict | None, purchase_price=None, purchase_date: str | None = None
) -> dict | None:
    """1年の株価推移チャート（SVG折れ線）の描画用データを作る。データ不足ならNone。

    保有銘柄では取得単価の水平線と購入日の縦線も描くため、取得単価が範囲外でも
    見えるように縦軸の範囲に含める。
    """
    history = (price_stats or {}).get("history_1y") or []
    if len(history) < 2:
        return None

    closes = [c for _, c in history]
    has_purchase = isinstance(purchase_price, (int, float)) and purchase_price > 0
    values = closes + ([purchase_price] if has_purchase else [])
    lo, hi = min(values), max(values)
    pad = (hi - lo) * 0.08 or abs(hi) * 0.05 or 1.0
    lo, hi = lo - pad, hi + pad

    def y(v: float) -> float:
        return round(_CHART_HEIGHT - (v - lo) / (hi - lo) * _CHART_HEIGHT, 2)

    last = len(history) - 1
    points = [[d, c, y(c)] for d, c in history]
    path = "M" + " L".join(f"{round(i / last * _CHART_WIDTH, 2)},{p[2]}" for i, p in enumerate(points))

    purchase_x_pct = None
    if purchase_date and history[0][0] <= str(purchase_date) <= history[-1][0]:
        index = next(i for i, (d, _) in enumerate(history) if d >= str(purchase_date))
        purchase_x_pct = round(index / last * 100, 2)

    return {
        "width": _CHART_WIDTH,
        "height": _CHART_HEIGHT,
        "path": path,
        "points_json": json.dumps(points, ensure_ascii=False),
        "start_date": history[0][0],
        "end_date": history[-1][0],
        "max_display": _fmt_price(max(closes)),
        "min_display": _fmt_price(min(closes)),
        "latest_display": _fmt_price(closes[-1]),
        "purchase_y": y(purchase_price) if has_purchase else None,
        "purchase_y_pct": round(y(purchase_price) / _CHART_HEIGHT * 100, 2) if has_purchase else None,
        "purchase_display": _fmt_price(purchase_price) if has_purchase else None,
        "purchase_x_pct": purchase_x_pct,
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
        "anchor_id": f"ticker-{result['symbol']}",
        "name": result["name"],
        "market": result.get("market", ""),
        "theme": result.get("theme", ""),
        "group": group,
        "recommendation": result.get("recommendation", "分析失敗"),
        "horizon": result.get("horizon"),
        "status_key": status["key"],
        "status_icon": status["icon"],
        "score": score,
        "score_display": "—" if score is None else f"{score:+d}",
        "score_bar_pct": 0 if score is None else min(100, abs(score)),
        "reasoning": result.get("reasoning", ""),
        "key_factors": result.get("key_factors") or [],
        "risks": result.get("risks", ""),
        "reflection": result.get("reflection", ""),
        "analysis_failed": result.get("analysis_failed", False),
        "latest_close": price_stats.get("latest_close"),
        "latest_close_display": _fmt_price_or_dash(price_stats.get("latest_close")),
        "change_1d": _fmt_pct(price_stats.get("change_1d_pct")),
        "change_1w": _fmt_pct(price_stats.get("change_1w_pct")),
        "change_1m": _fmt_pct(price_stats.get("change_1m_pct")),
        "change_3m": _fmt_pct(price_stats.get("change_3m_pct")),
        "change_6m": _fmt_pct(price_stats.get("change_6m_pct")),
        "change_1y": _fmt_pct(price_stats.get("change_1y_pct")),
        "price_available": bool(price_stats),
        "chart": _build_price_chart(price_stats),
        "news": result.get("news") or [],
        "nisa_tag": (
            "NISA成長投資枠 対象目安"
            if nisa_eligible
            else ("NISA成長投資枠 対象外の可能性" if nisa_eligible is False else None)
        ),
    }


def _next_record_month(months: list[int], today: dt.date) -> dt.date | None:
    """次に来る権利確定月の1日を返す（今月が権利確定月なら今月）。"""
    if not months:
        return None
    upcoming = sorted(m for m in months if m >= today.month)
    if upcoming:
        return dt.date(today.year, upcoming[0], 1)
    return dt.date(today.year + 1, min(months), 1)


def _build_yutai_info(result: dict, budget_jpy: float | None, today: dt.date) -> dict:
    """株主優待銘柄のカードに出す情報（最低投資金額・優待利回り・1年の値幅での位置など）を作る。"""
    yutai = result.get("yutai") or {}
    price_stats = result.get("price_stats") or {}
    latest = price_stats.get("latest_close")
    shares = yutai.get("shares") or 100

    min_investment = latest * shares if isinstance(latest, (int, float)) else None
    annual_value = yutai.get("annual_value_jpy")
    yield_pct = (
        round(annual_value / min_investment * 100, 2)
        if isinstance(annual_value, (int, float)) and min_investment
        else None
    )

    # 1年の値幅（最安値=0%、最高値=100%）の中で、現在の株価がどのあたりにあるか
    closes = [c for _, c in price_stats.get("history_1y") or []]
    range_position_pct = None
    if len(closes) >= 2 and isinstance(latest, (int, float)) and max(closes) > min(closes):
        lo, hi = min(closes), max(closes)
        range_position_pct = round(min(100.0, max(0.0, (latest - lo) / (hi - lo) * 100)), 1)
    if range_position_pct is None:
        range_label = None
    elif range_position_pct <= 33:
        range_label = "安値圏"
    elif range_position_pct >= 67:
        range_label = "高値圏"
    else:
        range_label = "中間"

    next_record = _next_record_month(yutai.get("months") or [], today)
    return {
        "content": yutai.get("content", ""),
        "shares": shares,
        "months_display": "・".join(f"{m}月" for m in yutai.get("months") or []),
        "next_record_display": f"{next_record.year}年{next_record.month}月末" if next_record else None,
        "next_record_is_this_month": bool(next_record and next_record.month == today.month and next_record.year == today.year),
        "min_investment": min_investment,
        "min_investment_display": f"約{min_investment:,.0f}円" if min_investment else "—",
        "within_budget": None if min_investment is None or not budget_jpy else min_investment <= budget_jpy,
        "yield_display": f"{yield_pct:.2f}%" if yield_pct is not None else None,
        "range_position_pct": range_position_pct,
        "range_label": range_label,
        "link": yutai.get("link"),
        "source": yutai.get("source"),
    }


def _build_yutai_view(results: list[dict], budget_jpy: float | None, today: dt.date) -> list[dict]:
    views = []
    for r in _sort_by_score(results):
        view = _build_view_model(r, group="株主優待")
        view["yutai"] = _build_yutai_info(r, budget_jpy, today)
        views.append(view)
    return views


def _build_sector_view(sector_results: list[dict], member_results: list[dict]) -> list[dict]:
    """業種別ETFのカードに、その業種の代表銘柄の判定（スコア順）と、業種内の注目銘柄を添える。

    注目銘柄は「買い候補」のうちスコアが最も高い銘柄。買い候補が無い業種では付けない。
    """
    lookup = {r["symbol"]: r for r in member_results}
    views = []
    for r in _sort_by_score(sector_results):
        view = _build_view_model(r, group="業種別ETF")
        members = [lookup[m["symbol"]] for m in r.get("members") or [] if m.get("symbol") in lookup]
        view["members"] = [_build_view_model(m, group="業種内の代表銘柄") for m in _sort_by_score(members)]
        top = view["members"][0] if view["members"] else None
        view["top_member"] = top if top and top["recommendation"] == "買い候補" else None
        views.append(view)
    return views


def _build_summary_sources(
    watchlist_view: list[dict], candidate_view: list[dict], yutai_view: list[dict], sector_member_results: list[dict]
) -> list[dict]:
    """売買サマリーに載せる銘柄。業種別ETFは業種の物差しなので載せない。

    業種内の代表銘柄のうち、ほかのリストに無く追加で分析した銘柄は、業種カードの中の
    カード（id="member-…"）へ飛ぶようにする。同じ銘柄が重複しないよう最初の1件だけ残す。
    """
    members = [
        {**_build_view_model(r, group=f"業種代表（{r.get('theme') or '業種'}）"), "anchor_id": f"member-{r['symbol']}"}
        for r in sector_member_results
    ]
    seen, combined = set(), []
    for v in watchlist_view + candidate_view + yutai_view + members:
        if v["symbol"] in seen:
            continue
        seen.add(v["symbol"])
        combined.append(v)
    return combined


def _build_holding_view_model(result: dict) -> dict:
    price_stats = result.get("price_stats") or {}
    status = _HOLDING_STATUS_MAP.get(result.get("recommendation"), _HOLDING_STATUS_MAP["分析失敗"])
    gain_loss_pct = result.get("gain_loss_pct")
    latest_close = price_stats.get("latest_close") or result.get("latest_close")

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
        "reflection": result.get("reflection", ""),
        "analysis_failed": result.get("analysis_failed", False),
        "purchase_date": result.get("purchase_date"),
        "purchase_price": result.get("purchase_price"),
        "purchase_price_display": _fmt_price_or_dash(result.get("purchase_price")),
        "latest_close": latest_close,
        "latest_close_display": _fmt_price_or_dash(latest_close),
        "holding_days": result.get("holding_days"),
        "gain_loss_pct": gain_loss_pct,
        "gain_loss_display": _fmt_pct(gain_loss_pct),
        "gain_class": (
            "gain-up" if (gain_loss_pct or 0) > 0 else ("gain-down" if (gain_loss_pct or 0) < 0 else "")
        ),
        "change_1d": _fmt_pct(price_stats.get("change_1d_pct")),
        "change_1w": _fmt_pct(price_stats.get("change_1w_pct")),
        "change_1m": _fmt_pct(price_stats.get("change_1m_pct")),
        "change_3m": _fmt_pct(price_stats.get("change_3m_pct")),
        "change_6m": _fmt_pct(price_stats.get("change_6m_pct")),
        "change_1y": _fmt_pct(price_stats.get("change_1y_pct")),
        "price_available": bool(price_stats),
        "chart": _build_price_chart(price_stats, result.get("purchase_price"), result.get("purchase_date")),
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


def _build_theme_allocation(portfolio_results: list[dict]) -> tuple[list[dict], int]:
    """保有銘柄をテーマ別に集計する。amount_invested_jpyが未入力の銘柄は集計から除外する。"""
    totals: dict[str, float] = {}
    excluded_count = 0
    for r in portfolio_results:
        amount = r.get("amount_invested_jpy")
        if not isinstance(amount, (int, float)):
            excluded_count += 1
            continue
        theme = r.get("theme") or "未分類"
        totals[theme] = totals.get(theme, 0) + amount

    grand_total = sum(totals.values())
    if grand_total <= 0:
        return [], excluded_count

    allocation = [
        {"theme": theme, "amount": amount, "pct": amount / grand_total * 100}
        for theme, amount in totals.items()
    ]
    allocation.sort(key=lambda a: -a["amount"])
    return allocation, excluded_count


def _build_nisa_usage(portfolio_results: list[dict]) -> dict | None:
    """NISA成長投資枠の使用状況を集計する。

    このアプリに登録された購入（すべてNISA成長投資枠で購入している前提）のみを
    対象とした概算であり、証券会社側の正式な消化額とは異なる場合がある。
    amount_invested_jpyが未入力の銘柄は集計から除外する。
    """
    current_year = dt.datetime.now(tz=_JST).year
    annual_used = 0.0
    lifetime_used = 0.0
    excluded_count = 0

    for r in portfolio_results:
        amount = r.get("amount_invested_jpy")
        if not isinstance(amount, (int, float)):
            excluded_count += 1
            continue
        lifetime_used += amount
        purchase_date = r.get("purchase_date")
        if isinstance(purchase_date, str) and purchase_date[:4] == str(current_year):
            annual_used += amount

    if lifetime_used <= 0:
        return None

    return {
        "current_year": current_year,
        "annual_used": annual_used,
        "annual_limit": _NISA_ANNUAL_GROWTH_LIMIT,
        "annual_pct": min(100, annual_used / _NISA_ANNUAL_GROWTH_LIMIT * 100),
        "lifetime_used": lifetime_used,
        "lifetime_limit": _NISA_LIFETIME_GROWTH_LIMIT,
        "lifetime_pct": min(100, lifetime_used / _NISA_LIFETIME_GROWTH_LIMIT * 100),
        "excluded_count": excluded_count,
    }


def _parse_date(value) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError:
        return None


def _months_overlap(range_start: dt.date, range_end: dt.date, entry_start: dt.date, entry_end: dt.date) -> int:
    """[range_start, range_end]と[entry_start, entry_end]が重なる月数（両端の月を含む）を数える。"""
    lo = max(range_start, entry_start)
    hi = min(range_end, entry_end)
    if lo > hi:
        return 0
    return (hi.year - lo.year) * 12 + (hi.month - lo.month) + 1


def _build_tsumitate_usage(entries: list[dict], growth_lifetime_used: float) -> dict:
    """つみたて投資枠の使用状況（年間・生涯）と、年内に年間枠を使い切るための月額目安を計算する。

    config/nisa_tsumitate.yamlの積立設定（開始日・月額）から概算する。証券会社側の
    正式な消化額とは異なる場合がある。まだ積立を始めていない場合（entriesが空）でも、
    月額目安は「0円から始めた場合の目安」として意味があるため、Noneは返さず常に計算する。
    """
    today = dt.datetime.now(tz=_JST).date()
    year_start = dt.date(today.year, 1, 1)

    annual_used = 0.0
    lifetime_used = 0.0
    excluded_count = 0

    for e in entries:
        amount = e.get("monthly_amount_jpy")
        start = _parse_date(e.get("start_date"))
        if not isinstance(amount, (int, float)) or start is None:
            excluded_count += 1
            continue
        end = _parse_date(e.get("end_date")) or today

        lifetime_used += _months_overlap(start, today, start, end) * amount
        annual_used += _months_overlap(year_start, today, start, end) * amount

    remaining_annual = max(0.0, _NISA_ANNUAL_TSUMITATE_LIMIT - annual_used)
    months_remaining = 12 - today.month + 1  # 今月を含めた年末までの残り月数
    suggested_monthly = (remaining_annual / months_remaining) if months_remaining > 0 else None

    combined_lifetime_used = lifetime_used + growth_lifetime_used

    return {
        "current_year": today.year,
        "annual_used": annual_used,
        "annual_limit": _NISA_ANNUAL_TSUMITATE_LIMIT,
        "annual_pct": min(100, annual_used / _NISA_ANNUAL_TSUMITATE_LIMIT * 100),
        "lifetime_used": lifetime_used,
        "combined_lifetime_used": combined_lifetime_used,
        "combined_lifetime_limit": _NISA_LIFETIME_TOTAL_LIMIT,
        "combined_lifetime_pct": min(100, combined_lifetime_used / _NISA_LIFETIME_TOTAL_LIMIT * 100),
        "months_remaining_this_year": max(0, months_remaining),
        "remaining_annual": remaining_annual,
        "suggested_monthly_to_fill_annual": suggested_monthly,
        "has_entries": bool(entries),
        "excluded_count": excluded_count,
    }


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


def _build_summary_by_horizon(combined: list[dict]) -> list[dict]:
    """売買サマリーを中長期・短期に分ける。

    horizonが無い判定（導入前の記録や分析失敗）は、それまでのプロンプトが
    中長期トレンドを主軸にしていたため中長期側に入れる。
    """
    short = [t for t in combined if t.get("horizon") == "短期"]
    long = [t for t in combined if t.get("horizon") != "短期"]
    sections = []
    for key, label, note, items in (
        ("long", "中長期（半年〜1年以上）", "時間をかけて効いてくる業績・テーマ・中長期トレンドに基づく判定", long),
        ("short", "短期（1〜3ヶ月）", "決算・イベント・直近のニュースや値動きに基づく判定。値動きが大きくなりやすい点に注意", short),
    ):
        buy, sell = _build_summary(items)
        sections.append({"key": key, "label": label, "note": note, "buy": buy, "sell": sell})
    return sections


def generate_report(
    watchlist_results: list[dict],
    candidate_results: list[dict],
    portfolio_results: list[dict],
    macro_news: list[dict],
    accuracy_summary: dict,
    templates_dir: Path,
    output_path: Path,
    tsumitate_entries: list[dict] | None = None,
    profit_taking: dict | None = None,
    yutai_results: list[dict] | None = None,
    yutai_config: dict | None = None,
    sector_results: list[dict] | None = None,
    sector_member_results: list[dict] | None = None,
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
    now = dt.datetime.now(tz=_JST)
    generated_at = now.strftime("%Y年%m月%d日 %H:%M (JST)")
    yutai_config = yutai_config or {}
    yutai_budget = yutai_config.get("max_min_investment_jpy")
    yutai_view = _build_yutai_view(yutai_results or [], yutai_budget, now.date())
    summary_sections = _build_summary_by_horizon(
        _build_summary_sources(watchlist_view, candidate_view, yutai_view, sector_member_results or [])
    )
    theme_allocation, theme_allocation_excluded_count = _build_theme_allocation(portfolio_results)
    nisa_usage = _build_nisa_usage(portfolio_results)
    tsumitate_usage = _build_tsumitate_usage(
        tsumitate_entries or [], nisa_usage["lifetime_used"] if nisa_usage else 0.0
    )

    # 暗号資産（現物）は株式と資産クラスが異なるため、専用セクションに分けて表示する。
    crypto_view = [v for v in candidate_view if v["market"] == "暗号資産"]
    candidate_view = [v for v in candidate_view if v["market"] != "暗号資産"]

    env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=True)
    template = env.get_template("report.html.jinja")

    # 代表銘柄の判定は、ほかのリスト（保有銘柄を除く）の判定を使い回し、無い銘柄は追加分析の結果を使う
    sector_view = _build_sector_view(
        sector_results or [],
        watchlist_results + candidate_results + (yutai_results or []) + (sector_member_results or []),
    )

    html = template.render(
        tickers=watchlist_view,
        candidates=candidate_view,
        crypto=crypto_view,
        holdings=holding_view,
        macro_news=macro_news,
        summary_sections=summary_sections,
        theme_allocation=theme_allocation,
        theme_allocation_excluded_count=theme_allocation_excluded_count,
        nisa_usage=nisa_usage,
        tsumitate_usage=tsumitate_usage,
        profit_taking=profit_taking,
        yutai=yutai_view,
        sectors=sector_view,
        yutai_budget_display=f"{yutai_budget:,.0f}円" if yutai_budget else None,
        yutai_checked_on=yutai_config.get("checked_on"),
        accuracy=accuracy_summary,
        generated_at=generated_at,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    logger.info("レポートを生成しました: %s", output_path)
