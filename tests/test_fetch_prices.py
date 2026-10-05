import fetch_prices as fp


def test_attach_relative_performance_computes_diff_for_known_market():
    price_stats = {"change_1w_pct": -5.0, "change_1m_pct": -10.0}
    benchmarks = {"^GSPC": {"change_1w_pct": -1.0, "change_1m_pct": -2.0}}
    fp.attach_relative_performance(price_stats, "US", benchmarks)

    assert price_stats["benchmark_symbol"] == "^GSPC"
    assert round(price_stats["change_1w_pct_relative"], 2) == -4.0
    assert round(price_stats["change_1m_pct_relative"], 2) == -8.0


def test_attach_relative_performance_uses_nikkei_for_jp_market():
    price_stats = {"change_1w_pct": 2.0}
    benchmarks = {"^N225": {"change_1w_pct": 1.0}}
    fp.attach_relative_performance(price_stats, "JP", benchmarks)

    assert price_stats["benchmark_symbol"] == "^N225"
    assert round(price_stats["change_1w_pct_relative"], 2) == 1.0


def test_attach_relative_performance_noop_when_price_stats_none():
    # Noneに対してエラーなく何もしないことを確認（呼び出し側で毎回Noneチェックしなくて済むように）
    fp.attach_relative_performance(None, "US", {"^GSPC": {"change_1w_pct": -1.0}})


def test_attach_relative_performance_noop_for_unmapped_market():
    price_stats = {"change_1w_pct": -5.0}
    fp.attach_relative_performance(price_stats, "暗号資産", {"^GSPC": {"change_1w_pct": -1.0}})

    assert "benchmark_symbol" not in price_stats
    assert "change_1w_pct_relative" not in price_stats


def test_attach_relative_performance_noop_when_market_missing():
    price_stats = {"change_1w_pct": -5.0}
    fp.attach_relative_performance(price_stats, None, {"^GSPC": {"change_1w_pct": -1.0}})

    assert "benchmark_symbol" not in price_stats


def test_attach_relative_performance_noop_when_benchmark_data_missing():
    price_stats = {"change_1w_pct": -5.0}
    fp.attach_relative_performance(price_stats, "US", {"^GSPC": None})

    assert "benchmark_symbol" not in price_stats
    assert "change_1w_pct_relative" not in price_stats


def test_attach_relative_performance_skips_period_when_ticker_value_missing():
    price_stats = {"change_1w_pct": None, "change_1m_pct": -10.0}
    benchmarks = {"^GSPC": {"change_1w_pct": -1.0, "change_1m_pct": -2.0}}
    fp.attach_relative_performance(price_stats, "US", benchmarks)

    assert "change_1w_pct_relative" not in price_stats
    assert round(price_stats["change_1m_pct_relative"], 2) == -8.0
