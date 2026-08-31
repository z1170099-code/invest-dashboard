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
            "score": 85,  # |score| >= HIGH_CONFIDENCE_ABS_SCORE(80) -> "high"
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
            "score": 60,  # < 80 -> "normal"
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
