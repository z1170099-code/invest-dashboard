"""Gemini APIを使って、価格データとニュースから銘柄ごとのスコア・推奨・理由を生成する。

注意: このスクリプトが生成する内容はAIによる自動分析であり、投資助言ではない。
生成されるレポートには必ず免責事項を表示すること（generate_report.py側で対応）。
"""

import json
import logging
import os
import time

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-flash-lite-latest"

_SYSTEM_INSTRUCTION = """\
あなたは個人投資家向けの情報整理アシスタントです。
与えられた株価の変化率、関連ニュースの見出し、そして世界情勢・マクロ経済ニュースから、
その銘柄について「参考情報としてのスコア・注目度」を整理してください。
特に、世界情勢・マクロ経済ニュースがその銘柄にプラス/マイナスどちらに働きそうかを
判断材料の一つとして重視してください。

厳守事項:
- あなたの出力は投資助言ではなく、あくまで個人が判断材料として参考にするための情報整理です。
- 断定的な将来予測（「必ず上がる」等）はせず、根拠となる事実（価格の動き・ニュース内容・世界情勢）に基づいて説明してください。
- 出力は指定されたJSON形式のみとし、それ以外の文章（前置き・コードブロック記号など）は一切含めないでください。
"""

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {
            "type": "integer",
            "description": "-100(強い売り材料)から100(強い買い材料)のスコア",
        },
        "recommendation": {
            "type": "string",
            "enum": ["買い候補", "様子見", "売り候補"],
        },
        "reasoning": {
            "type": "string",
            "description": "2〜3文の日本語での説明",
        },
        "key_factors": {
            "type": "array",
            "items": {"type": "string"},
            "description": "判断の根拠となった要因の短い箇条書き（2〜4個）",
        },
        "risks": {
            "type": "string",
            "description": "注意すべきリスクを1文で",
        },
    },
    "required": ["score", "recommendation", "reasoning", "key_factors", "risks"],
}


def _build_prompt(
    ticker: dict,
    price_stats: dict | None,
    news: list[dict],
    macro_news: list[dict] | None = None,
) -> str:
    name = ticker["name"]
    symbol = ticker["symbol"]
    market = ticker.get("market", "")
    theme = ticker.get("theme")

    if price_stats is None:
        price_section = "株価データは取得できませんでした。"
    else:
        def fmt(value):
            return f"{value:+.2f}%" if isinstance(value, (int, float)) else "データなし"

        price_section = (
            f"直近終値: {price_stats.get('latest_close')}\n"
            f"前日比: {fmt(price_stats.get('change_1d_pct'))}\n"
            f"1週間騰落率: {fmt(price_stats.get('change_1w_pct'))}\n"
            f"1ヶ月騰落率: {fmt(price_stats.get('change_1m_pct'))}\n"
            f"直近20日ボラティリティ: {fmt(price_stats.get('volatility_20d_pct'))}\n"
            f"52週高値からの乖離: {fmt(price_stats.get('off_52w_high_pct'))}\n"
        )

    if news:
        news_section = "\n".join(f"- {a['title']}（{a.get('source', '')}）" for a in news)
    else:
        news_section = "関連ニュースは見つかりませんでした。"

    if macro_news:
        macro_section = "\n".join(f"- {a['title']}（{a.get('source', '')}）" for a in macro_news)
    else:
        macro_section = "特筆すべき世界情勢・マクロ経済ニュースはありません。"

    theme_line = f"\n注目テーマ: {theme}\n" if theme else ""

    return f"""\
銘柄: {name}（{symbol}, {market}）
{theme_line}
【株価データ】
{price_section}

【関連ニュース見出し】
{news_section}

【世界情勢・マクロ経済ニュース】
{macro_section}

上記をもとに、指定されたJSONスキーマに従って分析結果を出力してください。
"""


def _get_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "環境変数 GEMINI_API_KEY が設定されていません。"
            ".env またはGitHub Secretsを確認してください。"
        )
    return genai.Client(api_key=api_key)


_PASSTHROUGH_FIELDS = ("theme", "risk_level", "nisa_growth_eligible")


def _base_fields(ticker: dict) -> dict:
    base = {
        "symbol": ticker["symbol"],
        "name": ticker["name"],
        "market": ticker.get("market", ""),
    }
    for field in _PASSTHROUGH_FIELDS:
        if field in ticker:
            base[field] = ticker[field]
    return base


def analyze_ticker(
    client: genai.Client,
    ticker: dict,
    price_stats: dict | None,
    news: list[dict],
    macro_news: list[dict] | None = None,
    model: str | None = None,
) -> dict:
    """1銘柄を分析し、結果の辞書を返す。失敗した場合は分析失敗を示す辞書を返す。"""
    model = model or os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
    prompt = _build_prompt(ticker, price_stats, news, macro_news)

    for attempt in range(2):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=_SYSTEM_INSTRUCTION,
                    response_mime_type="application/json",
                    response_schema=_RESPONSE_SCHEMA,
                ),
            )
            data = json.loads(response.text)
            return {
                **_base_fields(ticker),
                "price_stats": price_stats,
                "news": news,
                "analysis_failed": False,
                **data,
            }
        except Exception:
            logger.exception(
                "Gemini分析に失敗しました（試行%d回目）: %s", attempt + 1, ticker["symbol"]
            )
            time.sleep(8)

    return {
        **_base_fields(ticker),
        "price_stats": price_stats,
        "news": news,
        "analysis_failed": True,
        "score": None,
        "recommendation": "分析失敗",
        "reasoning": "AIによる分析中にエラーが発生したため、この銘柄の分析結果はありません。",
        "key_factors": [],
        "risks": "",
    }


def analyze_all(
    tickers: list[dict],
    price_stats_by_symbol: dict[str, dict | None],
    news_by_symbol: dict[str, list[dict]],
    macro_news: list[dict] | None = None,
) -> list[dict]:
    client = _get_client()
    results = []
    for i, ticker in enumerate(tickers):
        if i > 0:
            # 無料枠のレート制限（1分あたりのリクエスト数）を超えないための間隔
            time.sleep(4)
        symbol = ticker["symbol"]
        result = analyze_ticker(
            client,
            ticker,
            price_stats_by_symbol.get(symbol),
            news_by_symbol.get(symbol, []),
            macro_news,
        )
        results.append(result)
    return results
