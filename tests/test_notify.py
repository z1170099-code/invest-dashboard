import notify


def test_find_newly_flagged_sell_first_time():
    results = [
        {
            "symbol": "AAA",
            "name": "テスト株A",
            "recommendation": "売却検討",
            "purchase_date": "2026-01-01",
            "gain_loss_pct": -10.0,
            "reasoning": "",
        }
    ]
    out = notify.find_newly_flagged_sell(results, {})
    assert len(out) == 1


def test_find_newly_flagged_sell_excludes_already_flagged():
    results = [
        {
            "symbol": "AAA",
            "name": "テスト株A",
            "recommendation": "売却検討",
            "purchase_date": "2026-01-01",
            "gain_loss_pct": -10.0,
            "reasoning": "",
        }
    ]
    history = {"holding:AAA:2026-01-01": {"recommendation": "売却検討"}}
    out = notify.find_newly_flagged_sell(results, history)
    assert out == []


def test_find_newly_flagged_sell_includes_transition_from_hold():
    results = [
        {
            "symbol": "AAA",
            "name": "テスト株A",
            "recommendation": "売却検討",
            "purchase_date": "2026-01-01",
            "gain_loss_pct": -10.0,
            "reasoning": "",
        }
    ]
    history = {"holding:AAA:2026-01-01": {"recommendation": "保有継続"}}
    out = notify.find_newly_flagged_sell(results, history)
    assert len(out) == 1


def test_find_newly_flagged_sell_excludes_holding_recommendation():
    results = [{"symbol": "BBB", "name": "テスト株B", "recommendation": "保有継続", "purchase_date": "2026-01-01"}]
    out = notify.find_newly_flagged_sell(results, {})
    assert out == []


def test_find_newly_strong_buy_first_time_above_threshold():
    results = [{"symbol": "AAA", "name": "テスト株A", "recommendation": "買い候補", "score": 75, "reasoning": ""}]
    out = notify.find_newly_strong_buy(results, {}, "watchlist")
    assert len(out) == 1


def test_find_newly_strong_buy_excludes_already_strong():
    results = [{"symbol": "AAA", "name": "テスト株A", "recommendation": "買い候補", "score": 75, "reasoning": ""}]
    history = {"watchlist:AAA": {"recommendation": "買い候補", "score": 80}}
    out = notify.find_newly_strong_buy(results, history, "watchlist")
    assert out == []


def test_find_newly_strong_buy_includes_transition_across_threshold():
    results = [{"symbol": "AAA", "name": "テスト株A", "recommendation": "買い候補", "score": 75, "reasoning": ""}]
    history = {"watchlist:AAA": {"recommendation": "買い候補", "score": 65}}
    out = notify.find_newly_strong_buy(results, history, "watchlist")
    assert len(out) == 1


def test_find_newly_strong_buy_boundary_exactly_at_threshold_included():
    results = [
        {
            "symbol": "AAA",
            "name": "テスト株A",
            "recommendation": "買い候補",
            "score": notify._STRONG_BUY_SCORE_THRESHOLD,
            "reasoning": "",
        }
    ]
    out = notify.find_newly_strong_buy(results, {}, "watchlist")
    assert len(out) == 1


def test_find_newly_strong_buy_just_below_threshold_excluded():
    results = [
        {
            "symbol": "AAA",
            "name": "テスト株A",
            "recommendation": "買い候補",
            "score": notify._STRONG_BUY_SCORE_THRESHOLD - 1,
            "reasoning": "",
        }
    ]
    out = notify.find_newly_strong_buy(results, {}, "watchlist")
    assert out == []


def test_find_newly_strong_buy_excludes_non_buy_recommendation():
    results = [{"symbol": "DDD", "name": "テスト株D", "recommendation": "様子見", "score": 90, "reasoning": ""}]
    out = notify.find_newly_strong_buy(results, {}, "watchlist")
    assert out == []


def test_build_sell_section_contains_key_fields():
    alerts = [
        {"symbol": "AAA", "name": "テスト株A", "gain_loss_pct": -12.3, "reasoning": "理由A"},
    ]
    text = notify._build_sell_section(alerts)
    assert "テスト株A" in text
    assert "AAA" in text
    assert "-12.30%" in text
    assert "理由A" in text


def test_build_buy_section_contains_score():
    alerts = [{"symbol": "AAA", "name": "テスト株A", "score": 82, "reasoning": "好材料"}]
    text = notify._build_buy_section(alerts)
    assert "+82" in text
    assert "好材料" in text


def test_send_notification_email_noop_when_both_empty(monkeypatch):
    called = False

    class _ShouldNotBeCalled:
        def __call__(self, *a, **k):
            nonlocal called
            called = True
            raise AssertionError("SMTP should not be invoked")

    monkeypatch.setattr(notify.smtplib, "SMTP_SSL", _ShouldNotBeCalled())
    notify.send_notification_email([], [])
    assert called is False


def test_send_notification_email_skips_without_credentials(monkeypatch):
    monkeypatch.delenv("GMAIL_ADDRESS", raising=False)
    monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)

    def _fail(*a, **k):
        raise AssertionError("SMTP should not be invoked without credentials")

    monkeypatch.setattr(notify.smtplib, "SMTP_SSL", _fail)
    alerts = [{"symbol": "AAA", "name": "テスト株A", "gain_loss_pct": -5.0, "reasoning": ""}]
    # 例外を送出しないことも確認する
    notify.send_notification_email(alerts, [])
