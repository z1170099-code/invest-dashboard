"""株を買ったときに config/portfolio.yaml へ保有銘柄を追記するための補助スクリプト。

使い方（例）:
    python add_holding.py --symbol AAPL --amount 3000
    python add_holding.py --symbol 7011.T --amount 5000 --date 2026-07-24

symbol・amount（投資額,円）以外は省略可能。
name・market・theme は watchlist.yaml / candidate_pool.yaml に同じsymbolがあれば自動で補う。
purchase_price は直近の確定終値をyfinanceから自動取得する（当日終値がまだ確定していない
場合は、取得できた直近の終値を使い、その旨をコメントに残す）。

portfolio.yamlには手書きのコメントが多数あるため、YAMLとして読み込んで書き直す（＝
コメントが消える）のではなく、既存の書式に合わせたテキストブロックをファイル末尾に
そのまま追記する。
"""

import argparse
import datetime as dt
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from fetch_prices import fetch_price_stats

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

_ROOT = Path(__file__).resolve().parent.parent
_PORTFOLIO_PATH = _ROOT / "config" / "portfolio.yaml"
_CANDIDATE_POOL_PATH = _ROOT / "config" / "candidate_pool.yaml"
_WATCHLIST_PATH = _ROOT / "config" / "watchlist.yaml"
_JST = ZoneInfo("Asia/Tokyo")


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _lookup_known(symbol: str) -> dict:
    """candidate_pool.yaml / watchlist.yaml から name・market・theme の手がかりを探す。"""
    for c in _load_yaml(_CANDIDATE_POOL_PATH).get("candidates", []):
        if c.get("symbol") == symbol:
            return {"name": c.get("name"), "market": c.get("market"), "theme": c.get("theme")}
    for t in _load_yaml(_WATCHLIST_PATH).get("tickers", []):
        if t.get("symbol") == symbol:
            return {"name": t.get("name"), "market": t.get("market"), "theme": None}
    return {}


def _infer_market(symbol: str) -> str:
    return "JP" if symbol.upper().endswith(".T") else "US"


def _format_price(price: float, market: str) -> str:
    # 既存の登録内容に合わせ、日本株は整数円、それ以外は小数第2位まで表記する。
    return str(round(price)) if market == "JP" else f"{price:.2f}"


def add_holding(
    symbol: str, name: str, market: str, amount_jpy: int, theme: str, purchase_date: str
) -> str:
    stats = fetch_price_stats(symbol)
    if not stats or stats.get("latest_close") is None:
        raise RuntimeError(f"{symbol} の株価が取得できませんでした。ティッカーコードを確認してください。")

    price = stats["latest_close"]
    price_date = stats.get("latest_date")
    price_str = _format_price(price, market)
    theme = theme or "未分類"

    if price_date == purchase_date:
        note = "当日終値を取得単価として使用"
    else:
        note = f"直近の確定終値（{price_date}終値）を取得単価として使用"
    comment = f"単元未満株を{amount_jpy:,}円分購入。{note}。実際の約定価格が分かり次第、要修正"

    block = (
        f'\n  - symbol: "{symbol}"\n'
        f'    name: "{name}"\n'
        f'    market: "{market}"\n'
        f'    purchase_date: "{purchase_date}"\n'
        f"    purchase_price: {price_str}  # {comment}\n"
        f'    theme: "{theme}"\n'
        f"    amount_invested_jpy: {amount_jpy}\n"
    )

    with _PORTFOLIO_PATH.open("a", encoding="utf-8") as f:
        f.write(block)

    return (
        f"portfolio.yamlに追加しました: {name}（{symbol}） "
        f"購入日={purchase_date} 取得単価={price_str}（{price_date}終値） "
        f"投資額={amount_jpy:,}円 テーマ={theme}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="保有銘柄をconfig/portfolio.yamlに追加する")
    parser.add_argument("--symbol", required=True, help='ティッカーコード（例: "AAPL", "7203.T"）')
    parser.add_argument("--amount", type=int, required=True, help="投資額（円）")
    parser.add_argument("--name", help="表示名（省略時はwatchlist/candidate_poolから自動取得を試みる）")
    parser.add_argument("--market", help='"JP"/"US"等（省略時はsymbolから自動判定）')
    parser.add_argument("--theme", help="テーマ名（省略時はcandidate_poolから自動取得、無ければ未分類）")
    parser.add_argument("--date", help="購入日 YYYY-MM-DD（省略時は今日の日付）")
    args = parser.parse_args()

    known = _lookup_known(args.symbol)
    name = args.name or known.get("name")
    if not name:
        parser.error(f"{args.symbol} の表示名が見つかりませんでした。--name で指定してください。")
    market = args.market or known.get("market") or _infer_market(args.symbol)
    theme = args.theme or known.get("theme")
    purchase_date = args.date or dt.datetime.now(tz=_JST).date().isoformat()

    print(add_holding(args.symbol, name, market, args.amount, theme, purchase_date))


if __name__ == "__main__":
    main()
