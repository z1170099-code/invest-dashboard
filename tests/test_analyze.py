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


def test_build_accuracy_section_includes_horizon_breakdown_above_min_sample():
    summary = {
        "breakdown": [],
        "confidence_breakdown": [],
        "theme_breakdown": [],
        "horizon_breakdown": [
            {"horizon": "短期", "correct": 2, "incorrect": 6, "neutral": 0, "accuracy_pct": 25.0, "sample_size": 8},
            {"horizon": "中長期", "correct": 1, "incorrect": 1, "neutral": 0, "accuracy_pct": 50.0, "sample_size": 2},
        ],
    }
    section = analyze._build_accuracy_section(summary, {"買い候補", "売り候補"})
    assert "期間「短期」の判定: 過去8件中2件" in section
    assert "中長期" not in section.split("】", 1)[1].split("上記の傾向")[0]  # 件数不足の中長期は出さない


def test_response_schema_requires_horizon():
    assert "horizon" in analyze._RESPONSE_SCHEMA["required"]
    assert analyze._RESPONSE_SCHEMA["properties"]["horizon"]["enum"] == ["中長期", "短期"]


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


def test_build_yutai_section_empty_without_yutai():
    assert analyze._build_yutai_section(None) == ""


def test_build_prompt_includes_yutai_details():
    ticker = {
        "symbol": "9434.T",
        "name": "ソフトバンク",
        "market": "JP",
        "yutai": {"content": "PayPayマネーライト1,000円分", "shares": 100, "months": [3, 9]},
    }
    prompt = analyze._build_prompt(ticker, None, [])
    assert "【株主優待】" in prompt
    assert "PayPayマネーライト1,000円分" in prompt
    assert "権利確定月: 3月・9月末" in prompt


def test_build_prompt_includes_sector_instruction_only_for_sector_etfs():
    ticker = {"symbol": "1621.T", "name": "医薬品", "market": "JP", "sector": "医薬品"}
    prompt = analyze._build_prompt(ticker, None, [])
    assert "【業種別ETF】" in prompt
    assert "「医薬品」業種全体" in prompt
    assert analyze._build_sector_section(None) == ""


def test_build_sector_peer_table_lists_only_sector_etfs():
    tickers = [
        {"symbol": "1621.T", "name": "医薬品", "sector": "医薬品"},
        {"symbol": "1631.T", "name": "銀行", "sector": "銀行"},
        {"symbol": "AAPL", "name": "Apple"},
    ]
    stats = {"1621.T": {"change_1m_pct": 2.0, "change_3m_pct": 8.5}, "1631.T": None}
    table = analyze.build_sector_peer_table(tickers, stats)
    assert "- 医薬品: 1ヶ月 +2.00% / 3ヶ月 +8.50% / 6ヶ月 データなし" in table
    assert "- 銀行: 1ヶ月 データなし" in table
    assert "Apple" not in table
    assert analyze.build_sector_peer_table([{"symbol": "AAPL", "name": "Apple"}], {}) == ""


def test_build_prompt_includes_sector_peer_table_when_given():
    ticker = {"symbol": "1621.T", "name": "医薬品", "market": "JP", "sector": "医薬品", "sector_peers": "- 医薬品: 1ヶ月 +2.00%"}
    prompt = analyze._build_prompt(ticker, None, [])
    assert "【全業種の騰落率（比較用）】" in prompt
    assert "- 医薬品: 1ヶ月 +2.00%" in prompt


def test_build_sector_peer_table_can_list_tsumitate_indexes():
    tickers = [
        {"symbol": "2559.T", "name": "全世界株式", "tsumitate": {"index": "MSCI ACWI"}},
        {"symbol": "1621.T", "name": "医薬品", "sector": "医薬品"},
    ]
    stats = {"2559.T": {"change_1y_pct": 20.0}}
    table = analyze.build_sector_peer_table(tickers, stats, key="tsumitate")
    assert "- 全世界株式: 1ヶ月 データなし" in table
    assert "1年 +20.00%" in table
    assert "医薬品" not in table


def test_build_prompt_includes_tsumitate_section():
    ticker = {
        "symbol": "2559.T",
        "name": "全世界株式（オール・カントリー）",
        "market": "ETF",
        "tsumitate": {"index": "MSCI ACWI", "example_funds": ["eMAXIS Slim 全世界株式（オール・カントリー）"]},
        "tsumitate_peers": "- 全世界株式: 1年 +20.00%",
    }
    prompt = analyze._build_prompt(ticker, None, [])
    assert "【NISAつみたて投資枠】" in prompt
    assert "「MSCI ACWI」に連動するETF" in prompt
    assert "（例: eMAXIS Slim 全世界株式（オール・カントリー））" in prompt
    assert "【つみたて投資枠の主な指数の騰落率（比較用）】" in prompt
    assert analyze._build_tsumitate_section(None) == ""


def test_combine_subscores_weights_and_thresholds():
    assert analyze.combine_subscores({"trend": 50, "news": 20, "macro": -10}) == (23, "買い候補")
    assert analyze.combine_subscores({"trend": -40, "news": -10, "macro": 0}) == (-19, "売り候補")
    assert analyze.combine_subscores({"trend": 20, "news": 10, "macro": -10}) == (8, "様子見")
    # 範囲外の値は±100に丸め、欠けている観点は0として扱う
    assert analyze.combine_subscores({"trend": 300}) == (40, "買い候補")
    assert analyze.combine_subscores({}) == (0, "様子見")


def test_response_schema_asks_for_subscores_not_raw_score():
    assert "subscores" in analyze._RESPONSE_SCHEMA["required"]
    assert "score" not in analyze._RESPONSE_SCHEMA["properties"]


def test_active_profit_taking_carries_target_accounts():
    policy = {"profit_taking_until": "2026-12-31", "profit_taking_accounts": ["PayPay証券"]}
    result = analyze.active_profit_taking(policy, dt.date(2026, 10, 27))
    assert result["accounts"] == ["PayPay証券"]


def test_profit_taking_applies_only_to_target_accounts():
    pt = {"until": "2026-12-31", "days_left": 65, "accounts": ["PayPay証券"]}
    assert analyze.profit_taking_applies(pt, {"symbol": "NVDA"})  # account未入力はPayPay証券扱い
    assert not analyze.profit_taking_applies(pt, {"symbol": "LMT", "account": "楽天証券"})
    assert analyze.profit_taking_applies({"until": "2026-12-31", "days_left": 65}, {"account": "楽天証券"})  # 指定なしは全口座
    assert not analyze.profit_taking_applies(None, {"symbol": "NVDA"})


def test_build_fundamentals_section_formats_values_and_near_earnings():
    import datetime as dt
    f = {"trailingPE": 13.6, "forwardPE": 11.9, "priceToBook": 1.43, "trailingAnnualDividendYield": 0.0306,
         "revenueGrowth": 0.109, "recommendationMean": 2.1, "numberOfAnalystOpinions": 14,
         "next_earnings_date": "2026-11-04"}
    text = analyze._build_fundamentals_section(f, today=dt.date(2026, 11, 2))
    assert "PER（実績）: 13.6倍 / PER（予想）: 11.9倍 / PBR: 1.43倍" in text
    assert "配当利回り（実績）: +3.1%" in text
    assert "売上成長率（前年同期比）: +10.9% / 利益成長率: データなし" in text
    assert "アナリスト評価の平均: 2.10（1=強い買い〜5=売り、14人）" in text
    assert "次回決算発表予定: 2026-11-04（あと2日）" in text
    far = analyze._build_fundamentals_section({**f, "next_earnings_date": "2027-03-01"}, today=dt.date(2026, 11, 2))
    assert "次回決算" not in far
    assert analyze._build_fundamentals_section(None) == ""


class _FakeModels:
    def __init__(self, failures):
        self.failures = failures  # model -> 投げる例外（無ければ成功）
        self.calls = []

    def generate_content(self, model, contents, config):
        self.calls.append(model)
        if model in self.failures:
            raise self.failures[model]

        class R:
            text = '{"ok": true}'
        return R()


class _FakeClient:
    def __init__(self, failures):
        self.models = _FakeModels(failures)


def test_generate_json_switches_to_fallback_after_daily_quota(monkeypatch):
    monkeypatch.setattr(analyze.time, "sleep", lambda s: None)
    monkeypatch.setattr(analyze, "_exhausted_models", set())
    daily = Exception("429 RESOURCE_EXHAUSTED quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier")
    client = _FakeClient({"primary": daily})
    assert analyze._generate_json(client, "primary", "p", "s", {}, "AAA") == ({"ok": True}, analyze.FALLBACK_MODEL)
    # 上限に達したモデルは、次の銘柄からは呼ばない
    client.models.calls.clear()
    analyze._generate_json(client, "primary", "p", "s", {}, "BBB")
    assert client.models.calls == [analyze.FALLBACK_MODEL]


def test_generate_json_retries_then_falls_back_and_returns_none(monkeypatch):
    monkeypatch.setattr(analyze.time, "sleep", lambda s: None)
    monkeypatch.setattr(analyze, "_exhausted_models", set())
    boom = Exception("500 internal")
    client = _FakeClient({"primary": boom, analyze.FALLBACK_MODEL: boom})
    assert analyze._generate_json(client, "primary", "p", "s", {}, "AAA") is None
    assert client.models.calls == ["primary", "primary", analyze.FALLBACK_MODEL, analyze.FALLBACK_MODEL]


def test_model_for_group_uses_premium_model_only_for_holdings_and_watchlist(monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    assert analyze.model_for_group("holding") == analyze.DEFAULT_MODEL
    assert analyze.model_for_group("watchlist") == analyze.DEFAULT_MODEL
    assert analyze.model_for_group("candidate") == analyze.FALLBACK_MODEL
    monkeypatch.setenv("GEMINI_MODEL", "custom")
    assert analyze.model_for_group("candidate") == "custom"


def test_generate_json_switches_to_fallback_immediately_on_503(monkeypatch):
    monkeypatch.setattr(analyze.time, "sleep", lambda s: None)
    monkeypatch.setattr(analyze, "_exhausted_models", set())
    client = _FakeClient({"primary": Exception("503 UNAVAILABLE high demand")})
    assert analyze._generate_json(client, "primary", "p", "s", {}, "AAA") == ({"ok": True}, analyze.FALLBACK_MODEL)
    # 混雑は一時的なので、上限切れとは違い次の銘柄では再びprimaryを試す
    assert client.models.calls == ["primary", analyze.FALLBACK_MODEL]
    assert "primary" not in analyze._exhausted_models
