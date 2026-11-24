"""急騰の直後と急落の途中に出た「買い候補」を、表示上「様子見」に下げる（2026-11-25 追加）。

8/12〜11/24 の判定4千件余りを、判定後の株価と突き合わせて調べた結果による。暗号資産を除く買い候補で、
10営業日後に値上がりしていた割合は次のとおりだった。

- 判定前の1か月で+20%を超えて上がっていた銘柄（130件）: 23%（10月は17%）
- 52週高値から30%以上下がっていた銘柄（41件）: 15%
- それ以外（約1,200件）: 約45%

AIの判定そのもの（ai_recommendation）は残し、track_record では通常の的中率とは別に
（summary_guarded）答え合わせする。この決まりが本当に効いているかを後で確かめるため。
"""

HOT_1M_PCT = 20.0
FALLING_OFF_HIGH_PCT = -30.0

REASON_LABELS = {"hot": "急騰の直後", "falling": "急落の途中"}


def guard_reason(price_stats: dict | None) -> tuple[str, str] | None:
    """(理由のキー, 説明) を返す。当てはまらなければNone。"""
    ps = price_stats or {}
    change_1m = ps.get("change_1m_pct")
    off_high = ps.get("off_52w_high_pct")
    if isinstance(change_1m, (int, float)) and change_1m > HOT_1M_PCT:
        return "hot", f"直近1か月で{change_1m:+.0f}%上がった急騰の直後"
    if isinstance(off_high, (int, float)) and off_high <= FALLING_OFF_HIGH_PCT:
        return "falling", f"52週高値から{off_high:.0f}%下がった急落の途中"
    return None


def apply_buy_guard(results: list[dict]) -> int:
    """当てはまる買い候補を様子見に下げる（in-place）。下げた件数を返す。

    暗号資産は値動きの幅が株と違い、この集計にも入れていないため対象にしない。
    すでに下げた結果にもう一度かけても変わらない（分析に失敗して前回の判定を埋めた後にもかけるため）。
    """
    count = 0
    for r in results:
        if r.get("recommendation") != "買い候補" or r.get("market") == "暗号資産":
            continue
        found = guard_reason(r.get("price_stats"))
        if not found:
            continue
        key, text = found
        score = r.get("score")
        r["guard"] = {"reason": key, "ai_recommendation": "買い候補"}
        r["recommendation"] = "様子見"
        r["guard_note"] = (
            f"{text}のため、様子見として表示しています（AIの判定: 買い候補"
            + (f" {score:+d}" if isinstance(score, int) else "")
            + "）。過去の判定では、このような銘柄の買い候補はその後下がることが多かったためです。"
        )
        count += 1
    return count


def prompt_caution(price_stats: dict | None, market: str | None) -> str:
    """AIへの注意書き。当てはまらない銘柄・暗号資産では空文字。"""
    if market == "暗号資産":
        return ""
    found = guard_reason(price_stats)
    if not found:
        return ""
    key, text = found
    if key == "hot":
        detail = (
            "過去の判定を検証したところ、1か月で+20%を超えて上がった直後の銘柄を「買い候補」とした判定は、"
            "10営業日後に値上がりしていたのが約2割にとどまりました。"
            "勢いが強いことだけを理由に買い候補にせず、さらに上がる具体的な根拠があるかを慎重に判断してください。"
        )
    else:
        detail = (
            "過去の判定を検証したところ、52週高値から30%以上下がった銘柄を「買い候補」とした判定は、"
            "10営業日後に値上がりしていたのが約15%にとどまりました。"
            "割安に見えることだけを理由に買い候補にせず、下落が止まった具体的な根拠があるかを慎重に判断してください。"
        )
    return f"\n【注意（過去の判定の検証から）】\nこの銘柄は{text}です。{detail}\n"
