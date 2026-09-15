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
