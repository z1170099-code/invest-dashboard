import datetime as dt

import sell_once

TODAY = dt.date(2026, 11, 13)
RULE = {"deadline": "2026-12-30", "min_gain_pct": 3}


def _result(gain, recommendation="保有継続", **extra):
    return {
        "symbol": "03311112",
        "name": "三菱UFJ 純金ファンド",
        "purchase_date": None,
        "gain_loss_pct": gain,
        "recommendation": recommendation,
        "price_stats": {"latest_close": 49000, "latest_date": "2026-11-12"},
        "sell_once": RULE,
        **extra,
    }


def test_no_rule_returns_none():
    assert sell_once.evaluate_sell_once({"symbol": "NVDA", "gain_loss_pct": 10}, {}, TODAY) is None
    assert sell_once.describe(None) is None


def test_no_cost_loss_and_small_gain_do_not_signal():
    signals = {}
    assert sell_once.evaluate_sell_once(_result(None), signals, TODAY)["status"] == "no_cost"
    assert sell_once.evaluate_sell_once(_result(-4.0, "売却検討"), signals, TODAY)["status"] == "loss"
    assert sell_once.evaluate_sell_once(_result(2.5, "売却検討"), signals, TODAY)["status"] == "below_margin"
    assert signals == {}


def test_enough_gain_waits_while_ai_says_hold():
    signals = {}
    state = sell_once.evaluate_sell_once(_result(5.0), signals, TODAY)
    assert state["status"] == "waiting_ai" and state["days_left"] == 47
    assert signals == {}


def test_signals_once_when_ai_says_sell_and_keeps_it_after_price_drops():
    signals = {}
    state = sell_once.evaluate_sell_once(_result(4.2, "売却検討"), signals, TODAY)
    assert state["status"] == "signaled" and state["new"] is True and state["reason"] == "ai"
    assert signals["03311112|"] == {
        "date": "2026-11-13", "price_date": "2026-11-12", "price": 49000, "gain_pct": 4.2, "reason": "ai",
    }
    # 翌日に含み損になっても、合図は取り消さず「新しい合図」にもしない
    later = sell_once.evaluate_sell_once(_result(-1.0), signals, TODAY + dt.timedelta(days=1))
    assert later["status"] == "signaled" and later["new"] is False and later["date"] == "2026-11-13"


def test_signals_near_deadline_even_if_ai_says_hold():
    signals = {}
    state = sell_once.evaluate_sell_once(_result(3.5), signals, dt.date(2026, 12, 16))
    assert state["status"] == "signaled" and state["reason"] == "deadline"


def test_failed_analysis_is_not_used_as_ai_sell():
    signals = {}
    state = sell_once.evaluate_sell_once(_result(6.0, "売却検討", analysis_failed=True), signals, TODAY)
    assert state["status"] == "waiting_ai" and signals == {}


def test_describe_messages():
    signals = {}
    signaled = sell_once.describe(sell_once.evaluate_sell_once(_result(4.2, "売却検討"), signals, TODAY))
    assert signaled["signaled"] and signaled["label"] == "売却の合図 11/13"
    assert "含み益+4.2%" in signaled["message"] and "取り消しません" in signaled["message"]

    loss = sell_once.describe(sell_once.evaluate_sell_once(_result(-4.0), {}, TODAY))
    assert not loss["signaled"] and "損切りしない" in loss["message"] and "あと47日" in loss["message"]

    after = sell_once.describe(sell_once.evaluate_sell_once(_result(-4.0), {}, dt.date(2027, 1, 5)))
    assert "期限（2026-12-30）は過ぎましたが" in after["message"]

    no_cost = sell_once.describe(sell_once.evaluate_sell_once(_result(None), {}, TODAY))
    assert "取得単価が未登録" in no_cost["message"]


def test_signals_round_trip(tmp_path):
    path = tmp_path / "data" / "sell_signals.json"
    assert sell_once.load_signals(path) == {}
    sell_once.save_signals(path, {"03311112|": {"date": "2026-11-13"}})
    assert sell_once.load_signals(path) == {"03311112|": {"date": "2026-11-13"}}
