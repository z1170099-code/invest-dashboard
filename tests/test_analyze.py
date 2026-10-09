import datetime as dt

import analyze


def test_active_profit_taking_none_without_policy():
    assert analyze.active_profit_taking(None, dt.date(2026, 10, 9)) is None
    assert analyze.active_profit_taking({}, dt.date(2026, 10, 9)) is None


def test_active_profit_taking_active_before_deadline():
    result = analyze.active_profit_taking({"profit_taking_until": "2026-12-31"}, dt.date(2026, 10, 9))
    assert result == {"until": "2026-12-31", "days_left": 83}


def test_active_profit_taking_active_on_deadline_day():
    result = analyze.active_profit_taking({"profit_taking_until": "2026-12-31"}, dt.date(2026, 12, 31))
    assert result["days_left"] == 0


def test_active_profit_taking_expires_after_deadline():
    assert analyze.active_profit_taking({"profit_taking_until": "2026-12-31"}, dt.date(2027, 1, 1)) is None


def test_active_profit_taking_invalid_date_is_ignored():
    assert analyze.active_profit_taking({"profit_taking_until": "someday"}, dt.date(2026, 10, 9)) is None


def test_profit_taking_section_empty_when_inactive():
    assert analyze._build_profit_taking_section(None, 10.0) == ""


def test_profit_taking_section_pushes_sell_for_gains():
    section = analyze._build_profit_taking_section({"until": "2026-12-31", "days_left": 83}, 14.8)
    assert "+14.80%の含み益" in section
    assert "売却検討" in section


def test_profit_taking_section_normal_judgment_for_losses():
    section = analyze._build_profit_taking_section({"until": "2026-12-31", "days_left": 83}, -5.0)
    assert "利確の対象ではありません" in section


def test_profit_taking_section_treats_unknown_gain_as_not_profitable():
    section = analyze._build_profit_taking_section({"until": "2026-12-31", "days_left": 83}, None)
    assert "利確の対象ではありません" in section


def test_fmt_pct_formats_number_and_handles_missing():
    assert analyze._fmt_pct(5.0) == "+5.00%"
    assert analyze._fmt_pct(-5.0) == "-5.00%"
    assert analyze._fmt_pct(None) == "データなし"
    assert analyze._fmt_pct("N/A") == "データなし"


def test_format_price_section_handles_missing_price_stats():
    assert analyze._format_price_section(None) == "株価データは取得できませんでした。"


def test_format_price_section_includes_relative_when_present():
    price_stats = {
        "latest_close": 100,
        "change_1d_pct": 1.0,
        "change_1w_pct": -5.0,
        "change_1w_pct_relative": -4.0,
        "benchmark_symbol": "^GSPC",
    }
    section = analyze._format_price_section(price_stats)
    assert "1週間騰落率: -5.00%（^GSPC比 -4.00%）" in section


def test_format_price_section_omits_relative_when_absent():
    price_stats = {"latest_close": 100, "change_1w_pct": -5.0}
    section = analyze._format_price_section(price_stats)
    assert "1週間騰落率: -5.00%\n" in section
    assert "（" not in section  # 指数比の注記が付かない


def test_build_reflection_section_empty_when_no_previous():
    assert analyze._build_reflection_section(None, 100) == ""


def test_build_reflection_section_includes_previous_details():
    previous = {
        "date": "2026-01-01",
        "recommendation": "買い候補",
        "score": 70,
        "reasoning": "好材料があった",
        "latest_close": 100,
    }
    section = analyze._build_reflection_section(previous, 110)
    assert "2026-01-01" in section
    assert "買い候補" in section
    assert "好材料があった" in section
    assert "+10.00%" in section


def test_describe_trend_low_accuracy_warns():
    assert "外れやすい" in analyze._describe_trend(40)


def test_describe_trend_severely_low_accuracy_warns_more_strongly():
    text = analyze._describe_trend(30)
    assert "偶然" in text
    assert "外れやすい" not in text  # より強い警告文言に置き換わっている


def test_describe_trend_high_accuracy_praises():
    assert "的中しやすい" in analyze._describe_trend(80)


def test_describe_trend_mid_accuracy_neutral():
    assert analyze._describe_trend(60) == "的中率は平均的です。"


def test_build_accuracy_section_empty_when_no_summary():
    assert analyze._build_accuracy_section(None, {"買い候補", "売り候補"}) == ""


def test_build_accuracy_section_empty_below_min_sample():
    summary = {
        "breakdown": [
            {"recommendation": "買い候補", "correct": 2, "incorrect": 1, "neutral": 0, "accuracy_pct": 66.7, "sample_size": 3},
        ],
        "confidence_breakdown": [],
        "theme_breakdown": [],
    }
    assert analyze._build_accuracy_section(summary, {"買い候補", "売り候補"}) == ""


def test_build_accuracy_section_includes_recommendation_breakdown_above_min_sample():
    summary = {
        "breakdown": [
            {"recommendation": "買い候補", "correct": 8, "incorrect": 4, "neutral": 2, "accuracy_pct": 66.7, "sample_size": 12},
        ],
        "confidence_breakdown": [],
        "theme_breakdown": [],
    }
    section = analyze._build_accuracy_section(summary, {"買い候補", "売り候補"})
    assert "買い候補" in section
    assert "12件中8件" in section


def test_build_accuracy_section_filters_out_irrelevant_recommendation():
    summary = {
        "breakdown": [
            {"recommendation": "売却検討", "correct": 8, "incorrect": 4, "neutral": 0, "accuracy_pct": 66.7, "sample_size": 12},
        ],
        "confidence_breakdown": [],
        "theme_breakdown": [],
    }
    # 買い候補・売り候補だけを対象にしているので、売却検討の内訳は含まれない
    assert analyze._build_accuracy_section(summary, {"買い候補", "売り候補"}) == ""


def test_build_accuracy_section_includes_confidence_breakdown():
    summary = {
        "breakdown": [],
        "confidence_breakdown": [
            {"confidence": "high", "correct": 2, "incorrect": 5, "neutral": 0, "accuracy_pct": 28.6, "sample_size": 7},
        ],
        "theme_breakdown": [],
    }
    section = analyze._build_accuracy_section(summary, {"買い候補", "売り候補"})
    assert "確信度が高い判定" in section
    assert "7件中2件" in section


def test_build_accuracy_section_includes_matching_theme_only():
    summary = {
        "breakdown": [],
        "confidence_breakdown": [],
        "theme_breakdown": [
            {"theme": "半導体", "correct": 2, "incorrect": 6, "neutral": 0, "accuracy_pct": 25.0, "sample_size": 8},
        ],
    }
    matching = analyze._build_accuracy_section(summary, {"買い候補", "売り候補"}, "半導体")
    assert "半導体" in matching

    non_matching = analyze._build_accuracy_section(summary, {"買い候補", "売り候補"}, "資源・エネルギー")
    assert non_matching == ""


def test_build_accuracy_section_warns_when_high_confidence_underperforms_normal():
    summary = {
        "breakdown": [],
        "confidence_breakdown": [
            {"confidence": "high", "correct": 0, "incorrect": 9, "neutral": 3, "accuracy_pct": 0.0, "sample_size": 9},
            {"confidence": "normal", "correct": 12, "incorrect": 46, "neutral": 10, "accuracy_pct": 20.7, "sample_size": 58},
        ],
        "theme_breakdown": [],
    }
    section = analyze._build_accuracy_section(summary, {"買い候補", "売り候補"})
    assert "警告" in section
    assert "確信度スコアが実際の正しさを反映できていない" in section


def test_build_accuracy_section_no_warning_when_high_confidence_outperforms_normal():
    summary = {
        "breakdown": [],
        "confidence_breakdown": [
            {"confidence": "high", "correct": 8, "incorrect": 2, "neutral": 0, "accuracy_pct": 80.0, "sample_size": 10},
            {"confidence": "normal", "correct": 3, "incorrect": 7, "neutral": 0, "accuracy_pct": 30.0, "sample_size": 10},
        ],
        "theme_breakdown": [],
    }
    section = analyze._build_accuracy_section(summary, {"買い候補", "売り候補"})
    assert "警告" not in section


def test_build_accuracy_section_no_theme_arg_omits_theme_line():
    summary = {
        "breakdown": [
            {"recommendation": "買い候補", "correct": 8, "incorrect": 4, "neutral": 0, "accuracy_pct": 66.7, "sample_size": 12},
        ],
        "confidence_breakdown": [],
        "theme_breakdown": [
            {"theme": "半導体", "correct": 2, "incorrect": 6, "neutral": 0, "accuracy_pct": 25.0, "sample_size": 8},
        ],
    }
    section = analyze._build_accuracy_section(summary, {"買い候補", "売り候補"})
    assert "半導体" not in section


def test_describe_streak_none_when_no_streak():
    assert analyze._describe_streak(None) is None


def test_describe_streak_none_below_min_count():
    assert analyze._describe_streak({"outcome": "incorrect", "count": 1}) is None


def test_describe_streak_warns_on_incorrect_streak():
    text = analyze._describe_streak({"outcome": "incorrect", "count": 4})
    assert "4回連続" in text
    assert "外れ" in text


def test_describe_streak_praises_correct_streak():
    text = analyze._describe_streak({"outcome": "correct", "count": 3})
    assert "3回連続" in text
    assert "的中" in text


def test_build_accuracy_section_includes_streak_line():
    streak = {"outcome": "incorrect", "count": 4}
    section = analyze._build_accuracy_section(None, {"買い候補"}, streak=streak)
    # accuracy_summaryがNoneの場合は全体が空文字のままになる（streak単独では表示しない仕様）
    assert section == ""


def test_build_accuracy_section_combines_streak_with_other_data():
    summary = {
        "breakdown": [
            {"recommendation": "買い候補", "correct": 8, "incorrect": 4, "neutral": 0, "accuracy_pct": 66.7, "sample_size": 12},
        ],
        "confidence_breakdown": [],
        "theme_breakdown": [],
    }
    streak = {"outcome": "incorrect", "count": 4}
    section = analyze._build_accuracy_section(summary, {"買い候補", "売り候補"}, streak=streak)
    assert "4回連続" in section
    assert "買い候補" in section
