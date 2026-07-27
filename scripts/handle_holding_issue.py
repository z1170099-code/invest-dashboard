"""GitHub Issue経由で送信された保有銘柄の追加・削除リクエストを処理する。

.github/workflows/holding-issue.yml から実行される。Issue本文（ISSUE_BODY）は
GitHubのIssueフォームによって "### <項目名>\n\n<入力値>\n\n" の繰り返しでレンダリング
されるため、それをパースして add_holding() / remove_holding() に渡す。

項目名の文字列は .github/ISSUE_TEMPLATE/*.yml の label: と完全一致させる必要がある。
どちらかを変更したら、もう片方も必ず直すこと。

結果は comment.txt（Issueに投稿する日本語メッセージ）と changed.txt（"true"/"false"）
に書き出す。例外が起きても必ずこの2ファイルを書き切ってから終了する
（Issueがコメントも無く開いたままになる事態を避けるため）。
"""

import datetime as dt
import os
import re
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

from add_holding import _infer_market, _lookup_known, add_holding, remove_holding

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

_JST = ZoneInfo("Asia/Tokyo")
_ALLOWED_AUTHOR = "z1170099-code"
_COMMENT_PATH = Path("comment.txt")
_CHANGED_PATH = Path("changed.txt")


def _parse_issue_body(body: str) -> dict[str, str | None]:
    """"### 項目名\n\n値\n\n" 形式のIssue本文を {項目名: 値} の辞書にする。

    未入力の任意項目は値が "_No response_" になるため、それと空文字はNone扱いにする。
    """
    parts = re.split(r"^### (.+)$", body or "", flags=re.MULTILINE)
    fields: dict[str, str | None] = {}
    for i in range(1, len(parts), 2):
        label = parts[i].strip()
        value = parts[i + 1].strip() if i + 1 < len(parts) else ""
        fields[label] = None if value in ("", "_No response_") else value
    return fields


def _write_result(comment: str, changed: bool) -> None:
    _COMMENT_PATH.write_text(comment, encoding="utf-8")
    _CHANGED_PATH.write_text("true" if changed else "false", encoding="utf-8")


def main() -> None:
    author = os.environ.get("ISSUE_AUTHOR", "")
    if author != _ALLOWED_AUTHOR:
        # ワークフロー側のjob-level ifで既に弾かれているはずだが、念のための冗長なチェック。
        _write_result("権限がないため処理しませんでした。", changed=False)
        return

    labels = os.environ.get("ISSUE_LABELS", "")
    fields = _parse_issue_body(os.environ.get("ISSUE_BODY", ""))

    try:
        if "add-holding" in labels:
            symbol = fields.get("銘柄コード")
            if not symbol:
                raise RuntimeError("銘柄コードが未入力です。")
            amount_raw = fields.get("投資額（円）")
            if not amount_raw:
                raise RuntimeError("投資額が未入力です。")
            try:
                amount = int(amount_raw.replace(",", "").strip())
            except ValueError:
                raise RuntimeError(f"投資額「{amount_raw}」を数値として解釈できませんでした。")

            known = _lookup_known(symbol)
            name = fields.get("表示名") or known.get("name")
            if not name:
                raise RuntimeError(
                    f"{symbol} の表示名が見つかりませんでした。Issueで表示名を入力してください。"
                )
            market = fields.get("市場区分") or known.get("market") or _infer_market(symbol)
            theme = fields.get("テーマ") or known.get("theme")
            purchase_date = fields.get("購入日") or dt.datetime.now(tz=_JST).date().isoformat()

            comment = add_holding(symbol, name, market, amount, theme, purchase_date)
            _write_result(comment, changed=True)

        elif "remove-holding" in labels:
            symbol = fields.get("銘柄コード")
            if not symbol:
                raise RuntimeError("銘柄コードが未入力です。")
            purchase_date = fields.get("購入日")

            comment = remove_holding(symbol, purchase_date)
            _write_result(comment, changed=True)

        else:
            _write_result("想定外のラベルのため処理しませんでした。", changed=False)

    except Exception as e:
        _write_result(
            f"エラー: {e}\n\nお手数ですが内容を確認して、新しいIssueを作成し直してください。",
            changed=False,
        )


if __name__ == "__main__":
    main()
