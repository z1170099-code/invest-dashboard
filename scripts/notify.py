"""保有銘柄が新たに「売却検討」と判定されたときに、メールで知らせるモジュール。

前回も「売却検討」だった銘柄は毎日通知すると煩わしいため対象外とし、
「前回は売却検討ではなかったが、今回新たに売却検討になった」銘柄のみを通知する。
"""

import logging
import os
import smtplib
from email.mime.text import MIMEText

from history import build_key

logger = logging.getLogger(__name__)

_REPORT_URL = "https://z1170099-code.github.io/invest-dashboard/"


def find_newly_flagged(portfolio_results: list[dict], history: dict, group: str = "holding") -> list[dict]:
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


def _fmt_pct(value) -> str:
    return f"{value:+.2f}%" if isinstance(value, (int, float)) else "データなし"


def _build_email_body(newly_flagged: list[dict]) -> str:
    lines = ["以下の保有銘柄について、AIが新たに「売却検討」と判断しました。", ""]
    for r in newly_flagged:
        lines.append(f"■ {r.get('name')}（{r.get('symbol')}）")
        lines.append(f"  含み損益: {_fmt_pct(r.get('gain_loss_pct'))}")
        lines.append(f"  理由: {r.get('reasoning', '（記録なし）')}")
        lines.append("")
    lines.append(f"詳細はレポートをご確認ください: {_REPORT_URL}")
    lines.append("")
    lines.append("※ これは投資助言ではありません。最終的な判断は必ず自己責任で行ってください。")
    return "\n".join(lines)


def send_email_notification(newly_flagged: list[dict]) -> None:
    """新たに「売却検討」になった銘柄をメールで通知する。失敗しても例外を送出しない。"""
    if not newly_flagged:
        return

    sender = os.environ.get("GMAIL_ADDRESS")
    app_password = os.environ.get("GMAIL_APP_PASSWORD")
    recipient = os.environ.get("NOTIFY_TO_EMAIL") or sender

    if not sender or not app_password:
        logger.info("GMAIL_ADDRESS/GMAIL_APP_PASSWORDが未設定のため、通知メールをスキップします。")
        return

    subject = f"【投資ダッシュボード】売却検討の新規判定 {len(newly_flagged)}件"
    body = _build_email_body(newly_flagged)

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, app_password)
            server.sendmail(sender, [recipient], msg.as_string())
        logger.info("通知メールを送信しました（%d件）", len(newly_flagged))
    except Exception:
        logger.exception("通知メールの送信に失敗しましたが、レポートは正常に生成されています。")
