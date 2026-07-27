"""Gemini APIを使って、価格データとニュースから銘柄ごとのスコア・推奨・理由を生成する。

注意: このスクリプトが生成する内容はAIによる自動分析であり、投資助言ではない。
生成されるレポートには必ず免責事項を表示すること（generate_report.py側で対応）。
"""

import datetime as dt
import json
import logging
import os
import time

from google import genai
from google.genai import types

from history import build_key

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
- reflectionフィールドには、前回分析がある場合のみ、前回の判断がその後の値動きと照らして
  妥当だったかを簡潔に振り返って記入してください。前回分析がない場合（初回分析）は空文字のままにしてください。
- 前回分析がある場合、その振り返りは記録するだけで終わらせず、今回の判断そのものに反映させてください。
  振り返りと今回の判断が矛盾しないようにすること（例: 前回の判断が外れていたと振り返りながら、
  今回も同じ理由で同じ判断を繰り返すのは避ける）。
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
        "reflection": {
            "type": "string",
            "description": "前回分析からの振り返り（初回分析の場合は空文字）",
        },
    },
    "required": ["score", "recommendation", "reasoning", "key_factors", "risks"],
}


def _build_reflection_section(previous: dict | None, latest_close) -> str:
    """前回の分析結果と、その後の実際の値動きをプロンプト用に整形する。前回分析がなければ空文字。"""
    if not previous:
        return ""

    def fmt_close(value):
        return value if isinstance(value, (int, float)) else "データなし"

    prev_close = previous.get("latest_close")
    change_note = "データなし"
    if isinstance(prev_close, (int, float)) and isinstance(latest_close, (int, float)) and prev_close:
        change_note = f"{(latest_close / prev_close - 1) * 100:+.2f}%"

    score_line = f"（スコア {previous['score']:+d}）" if isinstance(previous.get("score"), int) else ""

    return f"""
【前回の分析（{previous.get('date', '不明')}）】
前回の判断: {previous.get('recommendation', '不明')}{score_line}
前回の理由: {previous.get('reasoning', '（記録なし）')}
前回終値: {fmt_close(prev_close)} → 今回終値: {fmt_close(latest_close)}（変化率: {change_note}）

上記の前回判断が、その後の実際の値動きと照らして妥当だったかをreflectionフィールドに簡潔に記入してください。
さらに重要な点として、この振り返りは記録するだけでなく、今回のスコア・推奨・理由の判断そのものに
反映させてください。例えば前回の判断が結果的に外れていた場合、同じ考え方をそのまま繰り返さず、
何が読み違いだったのか（重視しすぎた材料、軽視していたリスクなど）を踏まえて今回は判断を調整すること。
前回の判断が結果的に妥当だった場合は、その判断の根拠となった考え方を今回も引き続き重視してよい。
"""


def _build_prompt(
    ticker: dict,
    price_stats: dict | None,
    news: list[dict],
    macro_news: list[dict] | None = None,
    previous: dict | None = None,
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
    reflection_section = _build_reflection_section(
        previous, price_stats.get("latest_close") if price_stats else None
    )

    return f"""\
銘柄: {name}（{symbol}, {market}）
{theme_line}
【株価データ】
{price_section}

【関連ニュース見出し】
{news_section}

【世界情勢・マクロ経済ニュース】
{macro_section}
{reflection_section}

上記をもとに、指定されたJSONスキーマに従って分析結果を出力してください。
"""


_HOLDING_SYSTEM_INSTRUCTION = """\
あなたは個人投資家向けの情報整理アシスタントです。
ユーザーが既に保有している銘柄について、購入価格・購入日からの含み損益、保有期間、
株価の動き、関連ニュース、世界情勢・マクロ経済ニュースを踏まえて、
「保有を続けるべきか、売却を検討すべきか」の参考情報を整理してください。

判断にあたって考慮してほしい観点（すべてを機械的に当てはめるのではなく、総合的に判断すること）:
- 含み益が出ている場合、その利益を確定させる材料（過熱感、悪材料の出現など）があるか
- 含み損が出ている場合、損切りすべき悪材料があるか、それとも一時的な下落で保有継続が妥当か
- 保有期間の長さ（短期急騰・急落なのか、長期でじっくり保有してきたものか）
- 世界情勢・マクロ経済ニュースが今後の見通しにプラス/マイナスどちらに働きそうか

厳守事項:
- あなたの出力は投資助言ではなく、あくまで個人が判断材料として参考にするための情報整理です。
- 断定的な将来予測はせず、根拠となる事実に基づいて説明してください。
- 出力は指定されたJSON形式のみとし、それ以外の文章は一切含めないでください。
- reflectionフィールドには、前回分析がある場合のみ、前回の判断がその後の値動きと照らして
  妥当だったかを簡潔に振り返って記入してください。前回分析がない場合（初回分析）は空文字のままにしてください。
- 前回分析がある場合、その振り返りは記録するだけで終わらせず、今回の判断そのものに反映させてください。
  振り返りと今回の判断が矛盾しないようにすること（例: 前回の判断が外れていたと振り返りながら、
  今回も同じ理由で同じ判断を繰り返すのは避ける）。
"""

_HOLDING_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "recommendation": {
            "type": "string",
            "enum": ["売却検討", "保有継続"],
        },
        "reasoning": {
            "type": "string",
            "description": "含み損益・保有期間・ニュースを踏まえた2〜3文の日本語での説明",
        },
        "key_factors": {
            "type": "array",
            "items": {"type": "string"},
            "description": "判断の根拠となった要因の短い箇条書き（2〜4個）",
        },
        "risks": {
            "type": "string",
            "description": "保有継続・売却それぞれの場合に注意すべき点を1文で",
        },
        "reflection": {
            "type": "string",
            "description": "前回分析からの振り返り（初回分析の場合は空文字）",
        },
    },
    "required": ["recommendation", "reasoning", "key_factors", "risks"],
}


def _compute_holding_stats(holding: dict, price_stats: dict | None) -> dict:
    purchase_price = holding.get("purchase_price")
    purchase_date_str = holding.get("purchase_date")
    latest_close = price_stats.get("latest_close") if price_stats else None

    gain_loss_pct = None
    if isinstance(purchase_price, (int, float)) and purchase_price and isinstance(
        latest_close, (int, float)
    ):
        gain_loss_pct = (latest_close / purchase_price - 1) * 100

    holding_days = None
    if purchase_date_str:
        try:
            purchase_date = dt.date.fromisoformat(str(purchase_date_str))
            holding_days = (dt.date.today() - purchase_date).days
        except ValueError:
            holding_days = None

    return {
        "purchase_price": purchase_price,
        "purchase_date": purchase_date_str,
        "latest_close": latest_close,
        "gain_loss_pct": gain_loss_pct,
        "holding_days": holding_days,
    }


def _build_holding_prompt(
    holding: dict,
    price_stats: dict | None,
    news: list[dict],
    macro_news: list[dict] | None,
    holding_stats: dict,
    previous: dict | None = None,
) -> str:
    name = holding["name"]
    symbol = holding["symbol"]
    market = holding.get("market", "")

    def fmt(value):
        return f"{value:+.2f}%" if isinstance(value, (int, float)) else "データなし"

    if price_stats is None:
        price_section = "株価データは取得できませんでした。"
    else:
        price_section = (
            f"直近終値: {price_stats.get('latest_close')}\n"
            f"前日比: {fmt(price_stats.get('change_1d_pct'))}\n"
            f"1週間騰落率: {fmt(price_stats.get('change_1w_pct'))}\n"
            f"1ヶ月騰落率: {fmt(price_stats.get('change_1m_pct'))}\n"
            f"直近20日ボラティリティ: {fmt(price_stats.get('volatility_20d_pct'))}\n"
            f"52週高値からの乖離: {fmt(price_stats.get('off_52w_high_pct'))}\n"
        )

    holding_section = (
        f"購入日: {holding_stats['purchase_date']}\n"
        f"購入価格: {holding_stats['purchase_price']}\n"
        f"保有日数: {holding_stats['holding_days']}日\n"
        f"購入価格からの含み損益: {fmt(holding_stats['gain_loss_pct'])}\n"
    )

    if news:
        news_section = "\n".join(f"- {a['title']}（{a.get('source', '')}）" for a in news)
    else:
        news_section = "関連ニュースは見つかりませんでした。"

    if macro_news:
        macro_section = "\n".join(f"- {a['title']}（{a.get('source', '')}）" for a in macro_news)
    else:
        macro_section = "特筆すべき世界情勢・マクロ経済ニュースはありません。"

    reflection_section = _build_reflection_section(previous, holding_stats.get("latest_close"))

    return f"""\
銘柄: {name}（{symbol}, {market}）

【保有状況】
{holding_section}

【株価データ】
{price_section}

【関連ニュース見出し】
{news_section}

【世界情勢・マクロ経済ニュース】
{macro_section}
{reflection_section}

上記をもとに、指定されたJSONスキーマに従って「保有継続」か「売却検討」かの分析結果を出力してください。
"""


def analyze_holding(
    client: genai.Client,
    holding: dict,
    price_stats: dict | None,
    news: list[dict],
    macro_news: list[dict] | None = None,
    model: str | None = None,
    previous: dict | None = None,
) -> dict:
    """1つの保有銘柄を分析し、結果の辞書を返す。失敗した場合は分析失敗を示す辞書を返す。"""
    model = model or os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
    holding_stats = _compute_holding_stats(holding, price_stats)
    prompt = _build_holding_prompt(holding, price_stats, news, macro_news, holding_stats, previous)

    for attempt in range(2):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=_HOLDING_SYSTEM_INSTRUCTION,
                    response_mime_type="application/json",
                    response_schema=_HOLDING_RESPONSE_SCHEMA,
                ),
            )
            data = json.loads(response.text)
            return {
                **_base_fields(holding),
                **holding_stats,
                "price_stats": price_stats,
                "news": news,
                "analysis_failed": False,
                "reflection": "",
                **data,
            }
        except Exception:
            logger.exception(
                "Gemini分析に失敗しました（試行%d回目）: %s", attempt + 1, holding["symbol"]
            )
            time.sleep(8)

    return {
        **_base_fields(holding),
        **holding_stats,
        "price_stats": price_stats,
        "news": news,
        "analysis_failed": True,
        "recommendation": "分析失敗",
        "reasoning": "AIによる分析中にエラーが発生したため、この銘柄の分析結果はありません。",
        "key_factors": [],
        "risks": "",
        "reflection": "",
    }


def analyze_all_holdings(
    holdings: list[dict],
    price_stats_by_symbol: dict[str, dict | None],
    news_by_symbol: dict[str, list[dict]],
    macro_news: list[dict] | None = None,
    history: dict | None = None,
    group: str = "holding",
) -> list[dict]:
    client = _get_client()
    results = []
    for i, holding in enumerate(holdings):
        if i > 0:
            time.sleep(4)
        symbol = holding["symbol"]
        previous = (history or {}).get(build_key(group, symbol, holding.get("purchase_date")))
        result = analyze_holding(
            client,
            holding,
            price_stats_by_symbol.get(symbol),
            news_by_symbol.get(symbol, []),
            macro_news,
            previous=previous,
        )
        results.append(result)
    return results


def _get_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "環境変数 GEMINI_API_KEY が設定されていません。"
            ".env またはGitHub Secretsを確認してください。"
        )
    return genai.Client(api_key=api_key)


_PASSTHROUGH_FIELDS = ("theme", "risk_level", "nisa_growth_eligible", "amount_invested_jpy")


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
    previous: dict | None = None,
) -> dict:
    """1銘柄を分析し、結果の辞書を返す。失敗した場合は分析失敗を示す辞書を返す。"""
    model = model or os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
    prompt = _build_prompt(ticker, price_stats, news, macro_news, previous)

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
                "reflection": "",
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
        "reflection": "",
    }


def analyze_all(
    tickers: list[dict],
    price_stats_by_symbol: dict[str, dict | None],
    news_by_symbol: dict[str, list[dict]],
    macro_news: list[dict] | None = None,
    history: dict | None = None,
    group: str = "watchlist",
) -> list[dict]:
    client = _get_client()
    results = []
    for i, ticker in enumerate(tickers):
        if i > 0:
            # 無料枠のレート制限（1分あたりのリクエスト数）を超えないための間隔
            time.sleep(4)
        symbol = ticker["symbol"]
        previous = (history or {}).get(build_key(group, symbol))
        result = analyze_ticker(
            client,
            ticker,
            price_stats_by_symbol.get(symbol),
            news_by_symbol.get(symbol, []),
            macro_news,
            previous=previous,
        )
        results.append(result)
    return results
