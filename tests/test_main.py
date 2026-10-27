import main


def test_sector_member_tickers_skips_already_analyzed_and_duplicates():
    sectors = [
        {"symbol": "1617.T", "name": "食品", "theme": "食品", "market": "JP",
         "members": [{"symbol": "2914.T", "name": "JT"}, {"symbol": "2802.T", "name": "味の素"}]},
        {"symbol": "1630.T", "name": "小売", "theme": "小売", "market": "JP",
         "members": [{"symbol": "2802.T", "name": "味の素"}, {"symbol": "9983.T", "name": "ファーストリテイリング"}]},
    ]
    tickers = main._sector_member_tickers(sectors, {"2914.T"})
    assert [t["symbol"] for t in tickers] == ["2802.T", "9983.T"]
    assert tickers[0]["theme"] == "食品" and tickers[1]["theme"] == "小売"
    assert main._sector_member_tickers([{"symbol": "1617.T", "name": "食品"}], set()) == []
