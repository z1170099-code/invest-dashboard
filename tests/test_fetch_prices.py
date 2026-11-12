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


MUFG_CSV = """三菱ＵＦＪ 純金ファンド
基準日,基準価額(円),基準価額（分配金再投資）(円),分配金（税引前）(円),純資産総額（億円）
2026/11/10,49189,49189,,8335.38
2026/11/11,48549,48549,,8228.99
"""

SMTAM_CSV = """基準日,基準価額,分配金,純資産総額
2026/11/11,48474,-,5848.35
2026/11/12,48908,-,5905.50
"""


def test_parse_nav_csv_reads_both_asset_manager_formats():
    mufg = fp.parse_nav_csv(MUFG_CSV)
    assert list(mufg.values) == [49189.0, 48549.0]
    assert str(mufg.index[-1].date()) == "2026-11-11"
    smtam = fp.parse_nav_csv(SMTAM_CSV)
    assert list(smtam.values) == [48474.0, 48908.0]
    assert fp.parse_nav_csv("見出しなし\n1,2\n").empty


def test_fund_nav_stats_has_same_shape_as_stock_stats(monkeypatch):
    class _Response:
        content = SMTAM_CSV.encode("utf-8-sig")

        def raise_for_status(self):
            pass

    monkeypatch.setattr(fp.requests, "get", lambda *a, **k: _Response())
    stats = fp.fetch_fund_nav_stats("64315091", "https://example.com/nav.csv")
    assert stats["latest_close"] == 48908.0 and stats["latest_date"] == "2026-11-12"
    assert round(stats["change_1d_pct"], 2) == 0.90
    assert stats["history_1y"][-1] == ["2026-11-12", 48908.0]


def test_fetch_all_price_stats_uses_nav_csv_for_funds(monkeypatch):
    monkeypatch.setattr(fp, "fetch_fund_nav_stats", lambda symbol, url: {"fund": url})
    monkeypatch.setattr(fp, "fetch_price_stats", lambda symbol: {"stock": symbol})
    stats = fp.fetch_all_price_stats([{"symbol": "64315091", "nav_csv": "u"}, {"symbol": "NVDA"}])
    assert stats == {"64315091": {"fund": "u"}, "NVDA": {"stock": "NVDA"}}
