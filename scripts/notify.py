"""AIの判定に重要な変化があったとき（新規の売却検討／強い買い候補）に、
メールでまとめて知らせるモジュール。

前回から状態が変わった銘柄だけを対象にする。同じ内容を毎日通知し続けると
煩わしいため、「すでにその状態だった」銘柄は対象外にする。
"""

import logging
import os
import smtplib
from email.mime.text import MIMEText

from history import build_key

logger = logging.getLogger(__name__)

_REPORT_URL = "https://z1170099-code.github.io/invest-dashboard/"
_STRONG_BUY_SCORE_THRESHOLD = 70


def find_newly_flagged_sell(portfolio_results: list[dict], history: dict, group: str = "holding") -> list[dict]:
    """前回は「売却検討」ではなかったが、今回新たに「売却検討」になった保有銘柄を返す。"""
    newly_flagged = []
    for r in portfolio_results:
        if r.get("recommendation") != "売却検討":
            continue
        key = build_key(group, r["symbol"], r.get("purchase_date"))
        previous = history.get(key)
        if previous is None or previous.get("recommendation") != "売却検討":
            newly_flagged.append(r)
    return newly_flagged


def find_newly_strong_buy(results: list[dict], history: dict, group: str) -> list[dict]:
    """前回はスコア{閾値}未満だったが、今回新たにスコア{閾値}以上の「買い候補」になった銘柄を返す。"""
    newly_strong = []
    for r in results:
        score = r.get("score")
        if r.get("recommendation") != "買い候補" or not isinstance(score, int):
            continue
        if score < _STRONG_BUY_SCORE_THRESHOLD:
            continue

        key = build_key(group, r["symbol"])
        previous = history.get(key)
        was_already_strong = (
            previous is not None
            and previous.get("recommendation") == "買い候補"
            and isinstance(previous.get("score"), int)
            and previous.get("score") >= _STRONG_BUY_SCORE_THRESHOLD
        )
        if not was_already_strong:
            newly_strong.append(r)
    return newly_strong


def _fmt_pct(value) -> str:
    return f"{value:+.2f}%" if isinstance(value, (int, float)) else "データなし"


def _build_sell_section(sell_alerts: list[dict]) -> str:
    lines = [f"■ 新たに「売却検討」と判断された保有銘柄（{len(sell_alerts)}件）", ""]
    for r in sell_alerts:
        lines.append(f"・{r.get('name')}（{r.get('symbol')}）")
        lines.append(f"  含み損益: {_fmt_pct(r.get('gain_loss_pct'))}")
        lines.append(f"  理由: {r.get('reasoning', '（記録なし）')}")
        lines.append("")
    return "\n".join(lines)


def _build_buy_section(buy_alerts: list[dict]) -> str:
    lines = [
        f"■ 新たにスコア{_STRONG_BUY_SCORE_THRESHOLD}以上の「買い候補」になった銘柄（{len(buy_alerts)}件）",
        "",
    ]
    for r in buy_alerts:
        score = r.get("score")
        score_display = f"{score:+d}" if isinstance(score, int) else "—"
        lines.append(f"・{r.get('name')}（{r.get('symbol')}） スコア {score_display}")
        lines.append(f"  理由: {r.get('reasoning', '（記録なし）')}")
        lines.append("")
    return "\n".join(lines)


def send_notification_email(sell_alerts: list[dict], buy_alerts: list[dict]) -> None:
    """新規の売却検討／強い買い候補がある場合のみ、1通にまとめてメール通知する。失敗しても例外を送出しない。"""
    if not sell_alerts and not buy_alerts:
        return

    sender = os.environ.get("GMAIL_ADDRESS")
    app_password = os.environ.get("GMAIL_APP_PASSWORD")
    recipient = os.environ.get("NOTIFY_TO_EMAIL") or sender

    if not sender or not app_password:
        logger.info("GMAIL_ADDRESS/GMAIL_APP_PASSWORDが未設定のため、通知メールをスキップします。")
        return

    subject_parts = []
    if buy_alerts:
        subject_parts.append(f"強い買い候補{len(buy_alerts)}件")
    if sell_alerts:
        subject_parts.append(f"売却検討{len(sell_alerts)}件")
    subject = f"【投資ダッシュボード】{' / '.join(subject_parts)}"

    sections = []
    if buy_alerts:
        sections.append(_build_buy_section(buy_alerts))
    if sell_alerts:
        sections.append(_build_sell_section(sell_alerts))
    sections.append(f"詳細はレポートをご確認ください: {_REPORT_URL}")
    sections.append("")
    sections.append("※ これは投資助言ではありません。最終的な判断は必ず自己責任で行ってください。")
    body = "\n\n".join(sections)

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, app_password)
            server.sendmail(sender, [recipient], msg.as_string())
        logger.info(
            "通知メールを送信しました（買い候補%d件・売却検討%d件）", len(buy_alerts), len(sell_alerts)
        )
    except Exception:
        logger.exception("通知メールの送信に失敗しましたが、レポートは正常に生成されています。")
