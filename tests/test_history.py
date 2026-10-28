from history import apply_group_results, build_key, fill_failed_from_history, load_history, save_history


def test_build_key_holding_includes_purchase_date():
    assert build_key("holding", "AAPL", "2026-01-01") == "holding:AAPL:2026-01-01"


def test_build_key_non_holding_ignores_purchase_date():
    assert build_key("watchlist", "AAPL") == "watchlist:AAPL"
    assert build_key("candidate", "AAPL", "2026-01-01") == "candidate:AAPL"


def test_load_history_missing_file_returns_empty_dict(tmp_path):
    assert load_history(tmp_path / "does_not_exist.json") == {}


def test_load_history_corrupt_file_returns_empty_dict(tmp_path):
    path = tmp_path / "history.json"
    path.write_text("{not valid json", encoding="utf-8")
    assert load_history(path) == {}


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "history.json"
    data = {"watchlist:AAPL": {"recommendation": "買い候補", "score": 70}}
    save_history(path, data)
    assert load_history(path) == data


def test_apply_group_results_records_successful_analysis():
    history = {}
    results = [
        {
            "symbol": "AAPL",
            "recommendation": "買い候補",
            "score": 70,
            "reasoning": "好材料",
            "price_stats": {"latest_close": 200.0},
            "analysis_failed": False,
        }
    ]
    apply_group_results(history, "watchlist", results)
    assert history["watchlist:AAPL"]["recommendation"] == "買い候補"
    assert history["watchlist:AAPL"]["latest_close"] == 200.0


def test_apply_group_results_keeps_previous_entry_on_failure():
    history = {"watchlist:AAPL": {"recommendation": "買い候補", "score": 70}}
    results = [{"symbol": "AAPL", "analysis_failed": True}]
    apply_group_results(history, "watchlist", results)
    # 分析失敗時は前回のエントリをそのまま残す
    assert history["watchlist:AAPL"]["recommendation"] == "買い候補"


def test_apply_group_results_prunes_removed_tickers():
    history = {"watchlist:AAPL": {"recommendation": "買い候補"}, "watchlist:MSFT": {"recommendation": "様子見"}}
    # 今回の結果にAAPLしか含まれない -> MSFTのエントリは削除される
    results = [
        {
            "symbol": "AAPL",
            "recommendation": "買い候補",
            "score": 70,
            "reasoning": "",
            "price_stats": {},
            "analysis_failed": False,
        }
    ]
    apply_group_results(history, "watchlist", results)
    assert "watchlist:MSFT" not in history
    assert "watchlist:AAPL" in history


def test_fill_failed_from_history_uses_previous_judgement():
    history = {
        "watchlist:AAPL": {
            "date": "2026-10-27",
            "recommendation": "買い候補",
            "score": 32,
            "reasoning": "前回の理由",
            "horizon": "短期",
        }
    }
    results = [{"symbol": "AAPL", "analysis_failed": True, "recommendation": "分析失敗", "score": None}]
    assert fill_failed_from_history(history, "watchlist", results) == 1
    r = results[0]
    assert (r["recommendation"], r["score"], r["reasoning"], r["horizon"]) == ("買い候補", 32, "前回の理由", "短期")
    assert r["stale_date"] == "2026-10-27"
    # 的中率の記録・履歴の更新から外すため、失敗フラグは残す
    assert r["analysis_failed"] is True


def test_fill_failed_from_history_skips_success_and_missing_history():
    history = {"watchlist:AAPL": {"date": "2026-10-27", "recommendation": "様子見", "score": 0}}
    ok = {"symbol": "AAPL", "analysis_failed": False, "recommendation": "買い候補", "score": 40}
    new = {"symbol": "MSFT", "analysis_failed": True, "recommendation": "分析失敗", "score": None}
    assert fill_failed_from_history(history, "watchlist", [ok, new]) == 0
    assert ok["recommendation"] == "買い候補"
    assert new["recommendation"] == "分析失敗"


def test_fill_failed_from_history_holding_key_uses_purchase_date():
    history = {"holding:LMT:2026-10-27": {"date": "2026-10-27", "recommendation": "保有継続", "score": None}}
    results = [
        {"symbol": "LMT", "purchase_date": "2026-07-24", "analysis_failed": True, "recommendation": "分析失敗"},
        {"symbol": "LMT", "purchase_date": "2026-10-27", "analysis_failed": True, "recommendation": "分析失敗"},
    ]
    assert fill_failed_from_history(history, "holding", results) == 1
    assert [r["recommendation"] for r in results] == ["分析失敗", "保有継続"]


def test_apply_group_results_records_horizon():
    history = {}
    results = [{"symbol": "AAPL", "recommendation": "様子見", "score": 5, "horizon": "中長期", "analysis_failed": False}]
    apply_group_results(history, "watchlist", results)
    assert history["watchlist:AAPL"]["horizon"] == "中長期"


def test_apply_group_results_does_not_touch_other_groups():
    history = {"holding:AAPL:2026-01-01": {"recommendation": "保有継続"}}
    results = []  # watchlistグループの結果が0件でも、holdingグループのエントリは残す
    apply_group_results(history, "watchlist", results)
    assert "holding:AAPL:2026-01-01" in history
