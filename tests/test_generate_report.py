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
