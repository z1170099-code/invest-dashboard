from history import apply_group_results, build_key, load_history, save_history


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


def test_apply_group_results_does_not_touch_other_groups():
    history = {"holding:AAPL:2026-01-01": {"recommendation": "保有継続"}}
    results = []  # watchlistグループの結果が0件でも、holdingグループのエントリは残す
    apply_group_results(history, "watchlist", results)
    assert "holding:AAPL:2026-01-01" in history
