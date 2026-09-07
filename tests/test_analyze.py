import analyze


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
    assert "外れやすい" in analyze._describe_trend(30)


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
