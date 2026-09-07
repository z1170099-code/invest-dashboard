import datetime as dt

import track_record as tr


def test_classify_bullish():
    assert tr._classify("買い候補", 5.0) == "correct"
    assert tr._classify("買い候補", -5.0) == "incorrect"
    assert tr._classify("買い候補", 0.5) == "neutral"


def test_classify_bearish():
    assert tr._classify("売り候補", -5.0) == "correct"
    assert tr._classify("売り候補", 5.0) == "incorrect"
    assert tr._classify("売却検討", -5.0) == "correct"
    assert tr._classify("売却検討", 0.5) == "neutral"


def test_load_track_record_missing_file_returns_empty_shape(tmp_path):
    record = tr.load_track_record(tmp_path / "missing.json")
    assert record == tr._empty_record()


def test_load_track_record_migrates_old_format_without_crashing(tmp_path):
    path = tmp_path / "track_record.json"
    path.write_text('{"pending": [], "summary": {}, "recent_resolved": []}', encoding="utf-8")
    record = tr.load_track_record(path)
    assert record["summary_by_theme"] == {}
    assert record["summary_by_confidence"] == {}


def test_record_predictions_only_tracks_directional_recommendations():
    record = tr._empty_record()
    results = [
        {"symbol": "AAA", "recommendation": "買い候補", "score": 70, "price_stats": {"latest_close": 100}},
        {"symbol": "BBB", "recommendation": "様子見", "score": 10, "price_stats": {"latest_close": 100}},
    ]
    tr.record_predictions(record, "watchlist", results)
    symbols = {p["symbol"] for p in record["pending"]}
    assert symbols == {"AAA"}


def test_record_predictions_skips_analysis_failed():
    record = tr._empty_record()
    results = [
        {
            "symbol": "AAA",
            "recommendation": "買い候補",
            "score": 70,
            "price_stats": {"latest_close": 100},
            "analysis_failed": True,
        }
    ]
    tr.record_predictions(record, "watchlist", results)
    assert record["pending"] == []


def test_record_predictions_skips_missing_price():
    record = tr._empty_record()
    results = [{"symbol": "AAA", "recommendation": "買い候補", "score": 70, "price_stats": {}}]
    tr.record_predictions(record, "watchlist", results)
    assert record["pending"] == []


def test_record_predictions_captures_theme_and_score():
    record = tr._empty_record()
    results = [
        {
            "symbol": "AAA",
            "recommendation": "買い候補",
            "score": 85,
            "theme": "半導体",
            "price_stats": {"latest_close": 100},
        }
    ]
    tr.record_predictions(record, "watchlist", results)
    entry = record["pending"][0]
    assert entry["theme"] == "半導体"
    assert entry["score"] == 85


def test_record_predictions_does_not_duplicate_same_day():
    record = tr._empty_record()
    results = [{"symbol": "AAA", "recommendation": "買い候補", "score": 70, "price_stats": {"latest_close": 100}}]
    tr.record_predictions(record, "watchlist", results)
    tr.record_predictions(record, "watchlist", results)
    assert len(record["pending"]) == 1


def test_resolve_predictions_stays_pending_before_resolve_date():
    record = tr._empty_record()
    record["pending"] = [
        {
            "id": "watchlist:AAA:2026-01-01",
            "group": "watchlist",
            "symbol": "AAA",
            "name": "AAA",
            "recommendation": "買い候補",
            "theme": None,
            "score": 70,
            "date": "2026-01-01",
            "price_at_prediction": 100,
            "resolve_after": (tr._today() + dt.timedelta(days=1)).isoformat(),
        }
    ]
    tr.resolve_predictions(record, {"AAA": 120})
    assert len(record["pending"]) == 1
    assert record["summary"] == {}


def test_resolve_predictions_stays_pending_without_current_price():
    record = tr._empty_record()
    record["pending"] = [
        {
            "id": "watchlist:AAA:2026-01-01",
            "group": "watchlist",
            "symbol": "AAA",
            "name": "AAA",
            "recommendation": "買い候補",
            "theme": None,
            "score": 70,
            "date": "2026-01-01",
            "price_at_prediction": 100,
            "resolve_after": tr._today().isoformat(),
        }
    ]
    tr.resolve_predictions(record, {})  # AAAの現在価格が取得できていない
    assert len(record["pending"]) == 1


def test_resolve_predictions_updates_summary_theme_and_confidence():
    record = tr._empty_record()
    record["pending"] = [
        {
            "id": "candidate:AAA:2026-01-01",
            "group": "candidate",
            "symbol": "AAA",
            "name": "AAA",
            "recommendation": "買い候補",
            "theme": "半導体",
            "score": 85,  # |score| >= HIGH_CONFIDENCE_ABS_SCORE(60) -> "high"
            "date": "2026-01-01",
            "price_at_prediction": 100,
            "resolve_after": tr._today().isoformat(),
        }
    ]
    tr.resolve_predictions(record, {"AAA": 110})  # +10% -> correct

    assert record["pending"] == []
    assert record["summary"]["買い候補"] == {"correct": 1, "incorrect": 0, "neutral": 0}
    assert record["summary_by_theme"]["半導体"] == {"correct": 1, "incorrect": 0, "neutral": 0}
    assert record["summary_by_confidence"]["high"] == {"correct": 1, "incorrect": 0, "neutral": 0}
    assert len(record["recent_resolved"]) == 1
    assert record["recent_resolved"][0]["outcome"] == "correct"


def test_resolve_predictions_normal_confidence_band():
    record = tr._empty_record()
    record["pending"] = [
        {
            "id": "candidate:AAA:2026-01-01",
            "group": "candidate",
            "symbol": "AAA",
            "name": "AAA",
            "recommendation": "買い候補",
            "theme": None,
            "score": 45,  # < HIGH_CONFIDENCE_ABS_SCORE(60) -> "normal"
            "date": "2026-01-01",
            "price_at_prediction": 100,
            "resolve_after": tr._today().isoformat(),
        }
    ]
    tr.resolve_predictions(record, {"AAA": 90})  # -10% -> incorrect for a bullish call
    assert record["summary_by_confidence"]["normal"] == {"correct": 0, "incorrect": 1, "neutral": 0}
    assert "high" not in record["summary_by_confidence"]


def test_resolve_predictions_skips_theme_bucket_when_theme_missing():
    record = tr._empty_record()
    record["pending"] = [
        {
            "id": "watchlist:AAA:2026-01-01",
            "group": "watchlist",
            "symbol": "AAA",
            "name": "AAA",
            "recommendation": "買い候補",
            "theme": None,
            "score": None,
            "date": "2026-01-01",
            "price_at_prediction": 100,
            "resolve_after": tr._today().isoformat(),
        }
    ]
    tr.resolve_predictions(record, {"AAA": 110})
    assert record["summary_by_theme"] == {}
    assert record["summary_by_confidence"] == {}


def test_recent_resolved_capped_at_limit():
    record = tr._empty_record()
    for i in range(tr._RECENT_RESOLVED_LIMIT + 5):
        record["pending"].append(
            {
                "id": f"watchlist:SYM{i}:2026-01-01",
                "group": "watchlist",
                "symbol": f"SYM{i}",
                "name": f"SYM{i}",
                "recommendation": "買い候補",
                "theme": None,
                "score": None,
                "date": "2026-01-01",
                "price_at_prediction": 100,
                "resolve_after": tr._today().isoformat(),
            }
        )
    current_prices = {f"SYM{i}": 110 for i in range(tr._RECENT_RESOLVED_LIMIT + 5)}
    tr.resolve_predictions(record, current_prices)
    assert len(record["recent_resolved"]) == tr._RECENT_RESOLVED_LIMIT


def test_build_accuracy_summary_aggregates_across_dimensions():
    record = tr._empty_record()
    record["summary"] = {"買い候補": {"correct": 8, "incorrect": 4, "neutral": 2}}
    record["summary_by_theme"] = {"半導体": {"correct": 2, "incorrect": 6, "neutral": 0}}
    record["summary_by_confidence"] = {"high": {"correct": 2, "incorrect": 5, "neutral": 0}}

    summary = tr.build_accuracy_summary(record)

    assert summary["overall_sample_size"] == 12
    assert round(summary["overall_accuracy_pct"]) == 67

    theme_row = summary["theme_breakdown"][0]
    assert theme_row["theme"] == "半導体"
    assert theme_row["sample_size"] == 8
    assert round(theme_row["accuracy_pct"]) == 25

    confidence_row = summary["confidence_breakdown"][0]
    assert confidence_row["confidence"] == "high"
    assert confidence_row["sample_size"] == 7


def test_build_accuracy_summary_handles_all_empty():
    summary = tr.build_accuracy_summary(tr._empty_record())
    assert summary["overall_accuracy_pct"] is None
    assert summary["overall_sample_size"] == 0
    assert summary["breakdown"] == []
    assert summary["theme_breakdown"] == []
    assert summary["confidence_breakdown"] == []
    assert summary["streaks"] == {}


def _pending_entry(symbol="AAA", group="candidate", date="2026-01-01", score=45, theme=None):
    return {
        "id": f"{group}:{symbol}:{date}",
        "group": group,
        "symbol": symbol,
        "name": symbol,
        "recommendation": "買い候補",
        "theme": theme,
        "score": score,
        "date": date,
        "price_at_prediction": 100,
        "resolve_after": tr._today().isoformat(),
    }


def test_update_streak_starts_at_one_on_first_outcome():
    record = tr._empty_record()
    tr._update_streak(record, "candidate:AAA", _pending_entry(), "incorrect")
    assert record["streak_by_position"]["candidate:AAA"]["count"] == 1
    assert record["streak_by_position"]["candidate:AAA"]["outcome"] == "incorrect"


def test_update_streak_extends_on_repeated_same_outcome():
    record = tr._empty_record()
    tr._update_streak(record, "candidate:AAA", _pending_entry(), "incorrect")
    tr._update_streak(record, "candidate:AAA", _pending_entry(), "incorrect")
    tr._update_streak(record, "candidate:AAA", _pending_entry(), "incorrect")
    assert record["streak_by_position"]["candidate:AAA"]["count"] == 3


def test_update_streak_resets_when_outcome_flips():
    record = tr._empty_record()
    tr._update_streak(record, "candidate:AAA", _pending_entry(), "incorrect")
    tr._update_streak(record, "candidate:AAA", _pending_entry(), "incorrect")
    tr._update_streak(record, "candidate:AAA", _pending_entry(), "correct")
    entry = record["streak_by_position"]["candidate:AAA"]
    assert entry["count"] == 1
    assert entry["outcome"] == "correct"


def test_update_streak_neutral_does_not_change_existing_streak():
    record = tr._empty_record()
    tr._update_streak(record, "candidate:AAA", _pending_entry(), "incorrect")
    tr._update_streak(record, "candidate:AAA", _pending_entry(), "incorrect")
    tr._update_streak(record, "candidate:AAA", _pending_entry(), "neutral")
    entry = record["streak_by_position"]["candidate:AAA"]
    assert entry["count"] == 2
    assert entry["outcome"] == "incorrect"


def test_resolve_predictions_builds_streak_over_multiple_runs():
    record = tr._empty_record()

    # 1日目: 買い候補判定 -> 不正解
    record["pending"] = [_pending_entry(date="2026-01-01")]
    tr.resolve_predictions(record, {"AAA": 90})  # -10% -> incorrect

    # 2日目: 別の予測が同じ銘柄に対して再び不正解
    record["pending"] = [_pending_entry(date="2026-01-02")]
    tr.resolve_predictions(record, {"AAA": 90})

    streak = record["streak_by_position"]["candidate:AAA"]
    assert streak["count"] == 2
    assert streak["outcome"] == "incorrect"


def test_get_streak_returns_none_when_missing():
    summary = {"streaks": {}}
    assert tr.get_streak(summary, "candidate", "AAA") is None
    assert tr.get_streak(None, "candidate", "AAA") is None


def test_get_streak_returns_entry_for_matching_position():
    summary = {"streaks": {"candidate:AAA": {"outcome": "incorrect", "count": 3}}}
    streak = tr.get_streak(summary, "candidate", "AAA")
    assert streak["count"] == 3


def test_get_streak_uses_purchase_date_for_holdings():
    summary = {"streaks": {"holding:AAA:2026-01-01": {"outcome": "incorrect", "count": 2}}}
    assert tr.get_streak(summary, "holding", "AAA", "2026-01-01")["count"] == 2
    assert tr.get_streak(summary, "holding", "AAA", "2026-02-01") is None


def test_holding_streak_survives_record_and_resolve_roundtrip():
    """record_predictions -> resolve_predictions -> build_accuracy_summary -> get_streak を
    実際のホールディング結果で通し、streakのキーがpurchase_date込みで一致することを確認する
    （record_predictionsがpurchase_dateを保存し忘れると、streak_by_positionのキーが
    "holding:SYMBOL:None"になり、get_streak側の実際のpurchase_date指定のキーと
    一致しなくなる回帰バグを防ぐ）。
    """
    record = tr._empty_record()
    holding_result = {
        "symbol": "PAYP",
        "name": "PayPay Corporation",
        "recommendation": "売却検討",
        "purchase_date": "2026-03-19",
        "theme": "フィンテック",
        "price_stats": {"latest_close": 20.0},
    }
    tr.record_predictions(record, "holding", [holding_result])
    # 期限を過ぎさせて確定させる
    record["pending"][0]["resolve_after"] = tr._today().isoformat()
    tr.resolve_predictions(record, {"PAYP": 18.0})  # 下落 -> 売却検討は的中

    summary = tr.build_accuracy_summary(record)
    streak = tr.get_streak(summary, "holding", "PAYP", "2026-03-19")
    assert streak is not None
    assert streak["count"] == 1
    assert streak["outcome"] == "correct"
