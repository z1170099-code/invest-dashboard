import datetime as dt

import analyze
import buy_guard
import history
import track_record


def _buy(symbol="6857.T", change_1m=5.0, off_high=-5.0, market="JP", score=30, recommendation="買い候補"):
    return {
        "symbol": symbol, "name": symbol, "market": market, "theme": "半導体", "recommendation": recommendation,
        "score": score, "price_stats": {"latest_close": 100.0, "change_1m_pct": change_1m, "off_52w_high_pct": off_high},
    }


def test_guard_reason_thresholds():
    assert buy_guard.guard_reason({"change_1m_pct": 20.0, "off_52w_high_pct": -29.9}) is None
    assert buy_guard.guard_reason({"change_1m_pct": 20.1})[0] == "hot"
    assert buy_guard.guard_reason({"off_52w_high_pct": -30.0})[0] == "falling"
    assert buy_guard.guard_reason(None) is None


def test_apply_buy_guard_downgrades_hot_and_falling_but_not_crypto_or_sells():
    hot, falling, normal = _buy(change_1m=25.0), _buy("AMD", off_high=-35.0, market="US"), _buy("7203.T")
    crypto = _buy("BTC-USD", change_1m=40.0, market="暗号資産")
    sell = _buy("9984.T", change_1m=30.0, recommendation="売り候補", score=-30)
    results = [hot, falling, normal, crypto, sell]
    assert buy_guard.apply_buy_guard(results) == 2
    assert hot["recommendation"] == "様子見" and hot["guard"] == {"reason": "hot", "ai_recommendation": "買い候補"}
    assert "直近1か月で+25%上がった急騰の直後" in hot["guard_note"] and "AIの判定: 買い候補 +30" in hot["guard_note"]
    assert falling["guard"]["reason"] == "falling" and "52週高値から-35%" in falling["guard_note"]
    assert normal["recommendation"] == crypto["recommendation"] == "買い候補" and sell["recommendation"] == "売り候補"
    # 2回かけても変わらない
    assert buy_guard.apply_buy_guard(results) == 0


def test_prompt_caution_only_for_extremes():
    assert "1か月で+20%を超えて上がった直後" in buy_guard.prompt_caution({"change_1m_pct": 25.0}, "JP")
    assert "52週高値から30%以上下がった" in buy_guard.prompt_caution({"off_52w_high_pct": -40.0}, "US")
    assert buy_guard.prompt_caution({"change_1m_pct": 5.0}, "JP") == ""
    assert buy_guard.prompt_caution({"change_1m_pct": 50.0}, "暗号資産") == ""
    prompt = analyze._build_prompt({"symbol": "6857.T", "name": "アドバンテスト", "market": "JP"},
                                   {"latest_close": 1, "change_1m_pct": 25.0}, [])
    assert "【注意（過去の判定の検証から）】" in prompt


def test_guarded_call_is_recorded_as_ai_buy_and_scored_separately(monkeypatch):
    monkeypatch.setattr(track_record, "_today", lambda: dt.date(2026, 11, 25))
    record = track_record._empty_record()
    r = _buy(change_1m=25.0)
    buy_guard.apply_buy_guard([r])
    track_record.record_predictions(record, "candidate", [r])
    (p,) = record["pending"]
    assert p["recommendation"] == "買い候補" and p["guarded"] == "hot"

    p.update({"benchmark_symbol": "^N225", "benchmark_price_at_prediction": 100.0})
    monkeypatch.setattr(track_record, "_today", lambda: dt.date(2026, 12, 30))
    # 株は -10%、指数は +0% → 絶対でも指数比でも「外れ」。通常の集計には入らない
    track_record.resolve_predictions(record, {"6857.T": 90.0, "^N225": 100.0})
    assert record["summary_guarded"] == {"hot": {"correct": 0, "incorrect": 1, "neutral": 0}}
    assert record["summary_guarded_relative"] == {"hot": {"correct": 0, "incorrect": 1, "neutral": 0}}
    assert record["summary"] == {} and record["summary_relative"] == {} and record["recent_resolved"] == []
    rows = track_record.build_accuracy_summary(record)["guarded_breakdown"]
    assert rows[0]["label"].startswith("急騰の直後") and rows[0]["relative_accuracy_pct"] == 0


def test_history_keeps_ai_call_and_reflection_mentions_guard():
    h = {}
    r = _buy(change_1m=25.0)
    buy_guard.apply_buy_guard([r])
    history.apply_group_results(h, "candidate", [r])
    entry = h["candidate:6857.T"]
    assert entry["recommendation"] == "買い候補" and entry["guard_reason"] == "hot"
    text = analyze._build_reflection_section(entry, 100.0)
    assert "前回の判断: 買い候補（スコア +30）（急騰の直後だったため、ダッシュボードでは様子見として表示）" in text


def test_benchmark_for_and_backfill():
    markets = {"1655.T": "ETF", "7203.T": "JP", "AAPL": "US"}
    assert track_record.benchmark_for("7203.T", "watchlist", markets) == "^N225"
    assert track_record.benchmark_for("1655.T", "watchlist", markets) is None  # 設定で ETF
    assert track_record.benchmark_for("285A.T", "holding", markets) == "^N225"  # 設定から外れた日本株
    assert track_record.benchmark_for("PAYP", "holding", markets) == "^GSPC"
    assert track_record.benchmark_for("BTC-USD", "candidate", markets) is None
    assert track_record.benchmark_for("03311112", "holding", markets) is None
    assert track_record.benchmark_for("2559.T", "tsumitate_fund", markets) is None

    record = track_record._empty_record()
    record["pending"] = [
        {"symbol": "7203.T", "group": "watchlist", "date": "2026-10-20"},
        {"symbol": "AAPL", "group": "watchlist", "date": "2026-10-20", "benchmark_symbol": "^GSPC",
         "benchmark_price_at_prediction": 6000.0},
        {"symbol": "BTC-USD", "group": "candidate", "date": "2026-10-20"},
    ]
    benchmarks = {"^N225": {"daily_closes": {"2026-10-16": 49000.0, "2026-10-17": 50000.0, "2026-10-20": 51000.0}}}
    assert track_record.backfill_benchmark_prices(record, benchmarks, markets) == 1
    assert record["pending"][0]["benchmark_symbol"] == "^N225"
    assert record["pending"][0]["benchmark_price_at_prediction"] == 50000.0  # 判定日の前の営業日
    assert record["pending"][1]["benchmark_price_at_prediction"] == 6000.0
    assert "benchmark_symbol" not in record["pending"][2]


def test_report_shows_guard_note_tag_and_guarded_breakdown(tmp_path):
    from pathlib import Path

    import generate_report as gr

    hot = _buy("AMD", change_1m=25.0, market="US")
    hot["theme"] = "半導体"
    buy_guard.apply_buy_guard([hot])
    record = track_record._empty_record()
    record["summary_guarded_relative"] = {"hot": {"correct": 3, "incorrect": 7, "neutral": 0}}
    record["summary_guarded"] = {"hot": {"correct": 2, "incorrect": 8, "neutral": 0}}
    output = tmp_path / "index.html"
    gr.generate_report(
        [], [hot], [], [], track_record.build_accuracy_summary(record),
        Path(__file__).resolve().parent.parent / "templates", output,
    )
    html = output.read_text(encoding="utf-8")
    card = html.split('id="ticker-AMD"')[1].split("</details>")[0]
    assert "急騰の直後</span>" in card and "様子見" in card and "直近1か月で+25%上がった急騰の直後" in card
    summary = html.split('id="summary"')[1].split("</section>")[0]
    assert "AMD" not in summary  # 様子見なので売買サマリーに載らない
    accuracy = html.split('id="accuracy"')[1].split("</section>")[0]
    assert "急騰・急落で様子見に下げた買い候補のその後" in accuracy and "市場平均比 30%（10件）" in accuracy


def test_accuracy_section_uses_relative_when_enough():
    summary = {
        "breakdown": [{"recommendation": "買い候補", "sample_size": 700, "correct": 200, "accuracy_pct": 28.6}],
        "relative_breakdown": [{"recommendation": "買い候補", "sample_size": 555, "correct": 256, "accuracy_pct": 46.1}],
        "confidence_breakdown": [{"confidence": "normal", "sample_size": 600, "correct": 200, "accuracy_pct": 33.3}],
        "horizon_breakdown": [{"horizon": "短期", "sample_size": 45, "correct": 38, "accuracy_pct": 84.4}],
        "theme_breakdown": [{"theme": "金融", "sample_size": 54, "correct": 16, "accuracy_pct": 29.6}],
        "relative_theme_breakdown": [{"theme": "金融", "sample_size": 40, "correct": 22, "accuracy_pct": 55.0}],
    }
    text = analyze._build_accuracy_section(summary, {"買い候補"}, "金融")
    assert "過去555件中256件" in text and "過去700件" not in text
    assert "同じ期間の指数" in text and "通常の確信度の判定" not in text and "期間「短期」" not in text
    assert "テーマ「金融」: 過去40件中22件" in text

    absolute = analyze._build_accuracy_section({**summary, "relative_breakdown": []}, {"買い候補"}, "金融")
    assert "過去700件中200件" in absolute and "テーマ「金融」: 過去54件中16件" in absolute
    assert "通常の確信度の判定" in absolute and "期間「短期」" in absolute
