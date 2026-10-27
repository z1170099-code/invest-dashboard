import datetime as dt
from zoneinfo import ZoneInfo

import generate_report as gr

_JST = ZoneInfo("Asia/Tokyo")


def test_fmt_pct_positive_negative_zero_and_missing():
    assert gr._fmt_pct(5.0).startswith("▲")
    assert gr._fmt_pct(-5.0).startswith("▼")
    assert gr._fmt_pct(0).startswith("―")
    assert gr._fmt_pct(None) == "—"
    assert gr._fmt_pct("N/A") == "—"


def test_build_theme_allocation_computes_percentages():
    results = [
        {"theme": "半導体", "amount_invested_jpy": 3000},
        {"theme": "半導体", "amount_invested_jpy": 1000},
        {"theme": "資源・エネルギー", "amount_invested_jpy": 6000},
    ]
    allocation, excluded = gr._build_theme_allocation(results)
    assert excluded == 0
    by_theme = {a["theme"]: a for a in allocation}
    assert by_theme["半導体"]["amount"] == 4000
    assert round(by_theme["半導体"]["pct"]) == 40
    assert round(by_theme["資源・エネルギー"]["pct"]) == 60


def test_build_theme_allocation_excludes_missing_amount():
    results = [
        {"theme": "半導体", "amount_invested_jpy": 1000},
        {"theme": "資源・エネルギー"},  # amount_invested_jpy未入力
    ]
    allocation, excluded = gr._build_theme_allocation(results)
    assert excluded == 1
    assert len(allocation) == 1


def test_build_theme_allocation_defaults_missing_theme_to_unclassified():
    results = [{"amount_invested_jpy": 1000}]
    allocation, _ = gr._build_theme_allocation(results)
    assert allocation[0]["theme"] == "未分類"


def test_build_theme_allocation_empty_when_no_amounts():
    allocation, excluded = gr._build_theme_allocation([{"theme": "半導体"}])
    assert allocation == []
    assert excluded == 1


def test_build_nisa_usage_none_when_no_amounts():
    assert gr._build_nisa_usage([{"theme": "半導体"}]) is None


def test_build_nisa_usage_splits_annual_vs_lifetime():
    current_year = dt.datetime.now(tz=_JST).year
    results = [
        {"amount_invested_jpy": 5000, "purchase_date": f"{current_year}-01-01"},
        {"amount_invested_jpy": 3000, "purchase_date": f"{current_year - 1}-01-01"},
    ]
    usage = gr._build_nisa_usage(results)
    assert usage["current_year"] == current_year
    assert usage["annual_used"] == 5000
    assert usage["lifetime_used"] == 8000
    assert usage["excluded_count"] == 0


def test_build_nisa_usage_caps_percentage_at_100():
    current_year = dt.datetime.now(tz=_JST).year
    results = [{"amount_invested_jpy": 99_000_000, "purchase_date": f"{current_year}-01-01"}]
    usage = gr._build_nisa_usage(results)
    assert usage["annual_pct"] == 100
    assert usage["lifetime_pct"] == 100


def test_build_summary_buy_sorted_descending_sell_sorted_ascending():
    combined = [
        {"recommendation": "買い候補", "score": 50},
        {"recommendation": "買い候補", "score": 90},
        {"recommendation": "売り候補", "score": -30},
        {"recommendation": "売り候補", "score": -90},
        {"recommendation": "様子見", "score": 10},
    ]
    buy_list, sell_list = gr._build_summary(combined)
    assert [b["score"] for b in buy_list] == [90, 50]
    assert [s["score"] for s in sell_list] == [-90, -30]


def test_build_summary_by_horizon_splits_long_and_short():
    combined = [
        {"symbol": "L1", "recommendation": "買い候補", "score": 40, "horizon": "中長期"},
        {"symbol": "S1", "recommendation": "買い候補", "score": 30, "horizon": "短期"},
        {"symbol": "S2", "recommendation": "売り候補", "score": -32, "horizon": "短期"},
        {"symbol": "N1", "recommendation": "買い候補", "score": 35},  # horizon無しは中長期側
        {"symbol": "weak", "recommendation": "買い候補", "score": 19, "horizon": "中長期"},
        {"symbol": "W1", "recommendation": "様子見", "score": 0, "horizon": "短期"},
    ]
    sections = {s["key"]: s for s in gr._build_summary_by_horizon(combined)}

    assert [t["symbol"] for t in sections["long"]["buy"]] == ["L1", "N1"]
    assert sections["long"]["sell"] == []
    assert [t["symbol"] for t in sections["short"]["buy"]] == ["S1"]
    assert [t["symbol"] for t in sections["short"]["sell"]] == ["S2"]


def test_build_summary_keeps_only_strong_calls_up_to_limit():
    low = gr.SUMMARY_MIN_ABS_SCORE
    combined = [{"symbol": f"B{i}", "recommendation": "買い候補", "score": low + i} for i in range(14)]
    combined += [{"symbol": f"S{i}", "recommendation": "売り候補", "score": -low - i} for i in range(8)]
    combined += [
        {"symbol": "weak", "recommendation": "買い候補", "score": low - 1},
        {"symbol": "weak-sell", "recommendation": "売り候補", "score": -low + 1},
    ]
    buy_list, sell_list = gr._build_summary(combined)
    assert [t["symbol"] for t in buy_list] == [f"B{i}" for i in range(13, 3, -1)]  # 買いは上位10件
    assert [t["symbol"] for t in sell_list] == [f"S{i}" for i in range(7, 2, -1)]  # 売りは上位5件
    assert all(t["symbol"].startswith(("B", "S")) for t in buy_list + sell_list)  # 基準未満は載せない


def test_build_summary_by_horizon_orders_long_section_first():
    sections = gr._build_summary_by_horizon([])
    assert [s["key"] for s in sections] == ["long", "short"]
    assert all(s["buy"] == [] and s["sell"] == [] for s in sections)


def test_sort_holdings_prioritizes_sell_candidates():
    results = [
        {"recommendation": "保有継続", "gain_loss_pct": 20},
        {"recommendation": "売却検討", "gain_loss_pct": -5},
        {"recommendation": "保有継続", "gain_loss_pct": -50},
    ]
    sorted_results = gr._sort_holdings(results)
    assert sorted_results[0]["recommendation"] == "売却検討"


def test_sort_by_score_puts_missing_scores_last():
    results = [{"score": None}, {"score": 10}, {"score": 90}]
    sorted_results = gr._sort_by_score(results)
    assert [r["score"] for r in sorted_results] == [90, 10, None]


_HISTORY = [["2026-01-05", 100.0], ["2026-01-12", 110.0], ["2026-01-19", 90.0], ["2026-01-26", 105.0]]


def test_build_price_chart_none_without_enough_history():
    assert gr._build_price_chart(None) is None
    assert gr._build_price_chart({"history_1y": [["2026-01-05", 100.0]]}) is None


def test_build_price_chart_path_spans_full_width_and_stays_in_bounds():
    chart = gr._build_price_chart({"history_1y": _HISTORY})
    coords = [tuple(map(float, seg.split(","))) for seg in chart["path"][1:].split(" L")]
    assert coords[0][0] == 0
    assert coords[-1][0] == chart["width"]
    assert all(0 <= y <= chart["height"] for _, y in coords)
    # 最高値(110)が一番上(yが最小)、最安値(90)が一番下に描かれる
    assert min(coords, key=lambda c: c[1]) == coords[1]
    assert max(coords, key=lambda c: c[1]) == coords[2]
    assert chart["max_display"] == "110.00"
    assert chart["min_display"] == "90.00"
    assert chart["purchase_y"] is None
    assert chart["purchase_x_pct"] is None


def test_build_price_chart_includes_out_of_range_purchase_price():
    chart = gr._build_price_chart({"history_1y": _HISTORY}, purchase_price=200.0)
    # 取得単価が株価より大きく上でも、チャート内に収まるよう縦軸を広げる
    assert 0 <= chart["purchase_y"] <= chart["height"]
    assert chart["purchase_display"] == "200.00"


def test_build_price_chart_marks_purchase_date_within_range():
    chart = gr._build_price_chart({"history_1y": _HISTORY}, purchase_price=100.0, purchase_date="2026-01-15")
    # 2026-01-15以降で最初の点は3点目(index 2)、全4点なので2/3の位置
    assert chart["purchase_x_pct"] == round(2 / 3 * 100, 2)


def test_build_price_chart_ignores_purchase_date_outside_range():
    chart = gr._build_price_chart({"history_1y": _HISTORY}, purchase_date="2025-06-01")
    assert chart["purchase_x_pct"] is None


def test_fmt_price_uses_no_decimals_for_large_values():
    assert gr._fmt_price(33180.0) == "33,180"
    assert gr._fmt_price(230.36) == "230.36"


def test_parse_date_valid():
    assert gr._parse_date("2026-03-19") == dt.date(2026, 3, 19)


def test_parse_date_invalid_or_missing_returns_none():
    assert gr._parse_date(None) is None
    assert gr._parse_date("") is None
    assert gr._parse_date("not-a-date") is None


def test_months_overlap_counts_inclusive_months():
    assert gr._months_overlap(dt.date(2026, 1, 1), dt.date(2026, 6, 1), dt.date(2026, 1, 1), dt.date(2026, 6, 1)) == 6


def test_months_overlap_no_overlap_returns_zero():
    assert gr._months_overlap(dt.date(2026, 1, 1), dt.date(2026, 3, 1), dt.date(2026, 6, 1), dt.date(2026, 12, 1)) == 0


def test_months_overlap_partial_overlap():
    # rangeは1月〜3月、entryは2月開始 -> 重なるのは2月・3月の2ヶ月
    assert gr._months_overlap(dt.date(2026, 1, 1), dt.date(2026, 3, 1), dt.date(2026, 2, 1), dt.date(2026, 12, 1)) == 2


def test_build_tsumitate_usage_empty_entries_still_computes_suggestion():
    today = dt.datetime.now(tz=_JST).date()
    usage = gr._build_tsumitate_usage([], growth_lifetime_used=0.0)
    months_remaining = 12 - today.month + 1
    assert usage["has_entries"] is False
    assert usage["annual_used"] == 0
    assert usage["lifetime_used"] == 0
    assert usage["months_remaining_this_year"] == months_remaining
    assert round(usage["suggested_monthly_to_fill_annual"], 2) == round(1_200_000 / months_remaining, 2)


def test_build_tsumitate_usage_counts_one_month_for_single_day_entry():
    today = dt.datetime.now(tz=_JST).date()
    year_start = today.replace(month=1, day=1)
    entries = [{"start_date": year_start.isoformat(), "end_date": year_start.isoformat(), "monthly_amount_jpy": 10000}]
    usage = gr._build_tsumitate_usage(entries, growth_lifetime_used=0.0)
    assert usage["has_entries"] is True
    assert usage["annual_used"] == 10000
    assert usage["lifetime_used"] == 10000


def test_build_tsumitate_usage_counts_full_months_from_start_of_year():
    today = dt.datetime.now(tz=_JST).date()
    year_start = today.replace(month=1, day=1)
    entries = [{"start_date": year_start.isoformat(), "monthly_amount_jpy": 10000}]
    usage = gr._build_tsumitate_usage(entries, growth_lifetime_used=0.0)
    expected = today.month * 10000
    assert usage["annual_used"] == expected
    assert usage["lifetime_used"] == expected


def test_build_tsumitate_usage_combines_growth_and_tsumitate_for_lifetime():
    usage = gr._build_tsumitate_usage([], growth_lifetime_used=500_000)
    assert usage["combined_lifetime_used"] == 500_000
    assert usage["lifetime_used"] == 0


def test_build_tsumitate_usage_excludes_invalid_entries():
    entries = [
        {"start_date": None, "monthly_amount_jpy": 10000},
        {"start_date": "not-a-date", "monthly_amount_jpy": 10000},
    ]
    usage = gr._build_tsumitate_usage(entries, growth_lifetime_used=0.0)
    assert usage["excluded_count"] == 2
    assert usage["annual_used"] == 0
    assert usage["lifetime_used"] == 0


def test_next_record_month_picks_upcoming_or_wraps_to_next_year():
    assert gr._next_record_month([3, 9], dt.date(2026, 10, 25)) == dt.date(2027, 3, 1)
    assert gr._next_record_month([4, 10], dt.date(2026, 10, 25)) == dt.date(2026, 10, 1)
    assert gr._next_record_month([2, 8], dt.date(2026, 5, 1)) == dt.date(2026, 8, 1)
    assert gr._next_record_month([], dt.date(2026, 5, 1)) is None


def _yutai_result(latest=500, annual_value=1500, history=None):
    return {
        "symbol": "9831.T",
        "name": "ヤマダホールディングス",
        "yutai": {"content": "優待割引券", "shares": 100, "months": [3, 9], "annual_value_jpy": annual_value},
        "price_stats": {
            "latest_close": latest,
            "history_1y": history if history is not None else [["2026-01-01", 400], ["2026-06-01", 600], ["2026-10-01", latest]],
        },
    }


def test_build_yutai_info_computes_investment_yield_and_range():
    info = gr._build_yutai_info(_yutai_result(), 100000, dt.date(2026, 10, 25))
    assert info["min_investment"] == 50000
    assert info["min_investment_display"] == "約50,000円"
    assert info["within_budget"] is True
    assert info["yield_display"] == "3.00%"
    assert info["range_position_pct"] == 50.0
    assert info["range_label"] == "中間"
    assert info["months_display"] == "3月・9月"
    assert info["next_record_display"] == "2027年3月末"
    assert info["next_record_is_this_month"] is False


def test_build_yutai_info_flags_over_budget_and_low_range():
    history = [["2026-01-01", 2000], ["2026-06-01", 1500], ["2026-10-01", 1100]]
    info = gr._build_yutai_info(_yutai_result(latest=1100, annual_value=None, history=history), 100000, dt.date(2026, 10, 25))
    assert info["within_budget"] is False
    assert info["yield_display"] is None
    assert info["range_label"] == "安値圏"


def test_build_yutai_info_handles_missing_price():
    result = _yutai_result()
    result["price_stats"] = None
    info = gr._build_yutai_info(result, 100000, dt.date(2026, 10, 25))
    assert info["min_investment_display"] == "—"
    assert info["within_budget"] is None
    assert info["range_position_pct"] is None


def _analysis(symbol, name, score, recommendation, **extra):
    return {
        "symbol": symbol,
        "name": name,
        "market": "JP",
        "score": score,
        "recommendation": recommendation,
        "horizon": "中長期",
        "reasoning": "理由",
        "key_factors": ["要因"],
        "risks": "リスク",
        "price_stats": {"latest_close": 1000, "change_3m_pct": 5.0, "history_1y": [["2026-01-01", 900], ["2026-10-01", 1000]]},
        **extra,
    }


def test_generate_report_renders_sector_ranking_and_yutai(tmp_path):
    from pathlib import Path

    import track_record

    sectors = [
        _analysis("1621.T", "医薬品", -20, "売り候補", sector="医薬品", theme="医薬品"),
        _analysis("1631.T", "銀行", 40, "買い候補", sector="銀行", theme="銀行"),
    ]
    yutai = [_analysis("9434.T", "ソフトバンク", 10, "様子見", yutai={"content": "PayPay", "shares": 100, "months": [3], "annual_value_jpy": 1000})]
    output = tmp_path / "index.html"
    gr.generate_report(
        [], [], [], [],
        track_record.build_accuracy_summary(track_record.load_track_record(tmp_path / "none.json")),
        Path(__file__).resolve().parent.parent / "templates",
        output,
        yutai_results=yutai,
        yutai_config={"max_min_investment_jpy": 150000, "checked_on": "2026-10-25"},
        sector_results=sectors,
    )
    html = output.read_text(encoding="utf-8")
    assert 'href="#sectors"' in html and 'id="sectors"' in html
    sector_html = html.split('id="sectors"')[1].split("</section>")[0]
    # スコアが高い銀行が先に並ぶ
    assert sector_html.index("銀行") < sector_html.index("医薬品")
    assert 'id="yutai"' in html and "PayPay" in html


def test_holding_view_formats_prices_and_gain_class():
    view = gr._build_holding_view_model({
        "symbol": "PAYP",
        "name": "PayPay",
        "recommendation": "売却検討",
        "purchase_price": 20.45,
        "gain_loss_pct": -26.55,
        "price_stats": {"latest_close": 15.020000457763672},
    })
    assert view["latest_close_display"] == "15.02"
    assert view["purchase_price_display"] == "20.45"
    assert view["gain_class"] == "gain-down"
    assert gr._fmt_price_or_dash(None) == "—"
    assert gr._fmt_price_or_dash(12755.0) == "12,755"


def test_generate_report_groups_yutai_buy_candidates_first(tmp_path):
    from pathlib import Path

    import track_record

    yutai = [
        _analysis("7803.T", "ブシロード", 10, "様子見", yutai={"content": "ポイント", "shares": 100, "months": [6, 12]}),
        _analysis("9432.T", "NTT", 30, "買い候補", yutai={
            "content": "dポイント", "shares": 100, "months": [3],
            "link": "https://example.com/ntt", "source": "楽天証券 株主優待検索（10万円以下）",
        }),
    ]
    output = tmp_path / "index.html"
    gr.generate_report(
        [], [], [], [],
        track_record.build_accuracy_summary(track_record.load_track_record(tmp_path / "none.json")),
        Path(__file__).resolve().parent.parent / "templates",
        output,
        yutai_results=yutai,
        yutai_config={"max_min_investment_jpy": 100000},
    )
    html = output.read_text(encoding="utf-8")
    section = html.split('id="yutai"')[1].split("</section>")[0]
    buy_part, rest_part = section.split('class="group-more"')
    assert "NTT" in buy_part and "ブシロード" not in buy_part
    assert "ブシロード" in rest_part
    assert 'href="https://example.com/ntt"' in buy_part
    assert "出典: 楽天証券 株主優待検索（10万円以下）" in buy_part


def test_build_sector_view_attaches_members_by_score_and_top_buy():
    sectors = [_analysis("1617.T", "食品", 30, "買い候補", members=[
        {"symbol": "2914.T", "name": "JT"}, {"symbol": "2802.T", "name": "味の素"}, {"symbol": "9999.T", "name": "未分析"},
    ])]
    members = [_analysis("2914.T", "JT", 10, "様子見"), _analysis("2802.T", "味の素", 35, "買い候補")]
    view = gr._build_sector_view(sectors, members)[0]
    assert [m["name"] for m in view["members"]] == ["味の素", "JT"]  # 判定の無い銘柄は出さない
    assert view["top_member"]["name"] == "味の素"


def test_build_sector_view_has_no_top_member_without_buy():
    sectors = [_analysis("1631.T", "銀行", -20, "売り候補", members=[{"symbol": "8306.T", "name": "MUFG"}])]
    view = gr._build_sector_view(sectors, [_analysis("8306.T", "MUFG", -15, "売り候補")])[0]
    assert view["top_member"] is None
    assert len(view["members"]) == 1


def test_generate_report_renders_sector_members_with_unique_ids(tmp_path):
    from pathlib import Path

    import track_record

    sectors = [_analysis("1617.T", "食品", 30, "買い候補", sector="食品", members=[{"symbol": "2914.T", "name": "JT"}])]
    candidates = [_analysis("2914.T", "JT", 40, "買い候補")]
    output = tmp_path / "index.html"
    gr.generate_report(
        [], candidates, [], [],
        track_record.build_accuracy_summary(track_record.load_track_record(tmp_path / "none.json")),
        Path(__file__).resolve().parent.parent / "templates",
        output,
        sector_results=sectors,
    )
    html = output.read_text(encoding="utf-8")
    sector_html = html.split('id="sectors"')[1].split("</section>")[0]
    assert "業種内の注目" in sector_html and 'id="member-2914.T"' in sector_html
    assert html.count('id="ticker-2914.T"') == 1  # 候補セクションのカードとIDが重複しない


def test_summary_sources_include_yutai_and_new_sector_members_with_anchors():
    watch = [gr._build_view_model(_analysis("7203.T", "トヨタ", 20, "買い候補"), group="ウォッチリスト")]
    cand = [gr._build_view_model(_analysis("2914.T", "JT", 40, "買い候補"), group="ハイリスク候補")]
    yutai = [gr._build_view_model(_analysis("9432.T", "NTT", 30, "買い候補"), group="株主優待")]
    members = [_analysis("6501.T", "日立製作所", 45, "買い候補", theme="電機・精密"), _analysis("2914.T", "JT", 40, "買い候補")]
    combined = gr._build_summary_sources(watch, cand, yutai, members)
    by_symbol = {v["symbol"]: v for v in combined}
    assert set(by_symbol) == {"7203.T", "2914.T", "9432.T", "6501.T"}  # JTは重複させない
    assert by_symbol["6501.T"]["anchor_id"] == "member-6501.T"
    assert by_symbol["6501.T"]["group"] == "業種代表（電機・精密）"
    assert by_symbol["2914.T"]["anchor_id"] == "ticker-2914.T"
    buy = gr._build_summary_by_horizon(combined)[0]["buy"]
    assert buy[0]["name"] == "日立製作所"  # スコア45が先頭


def test_subscores_display_formats_signs():
    shown = gr._build_subscores_display({"trend": 40, "news": 0, "macro": -15})
    assert [(s["label"], s["display"], s["sign"]) for s in shown] == [
        ("値動き", "+40", "up"), ("ニュース", "+0", ""), ("マクロ", "-15", "down"),
    ]
    assert gr._build_subscores_display(None) == []
