# AI投資分析ダッシュボード（個人用）

自分で指定した銘柄について、株価の動きと関連ニュースをGemini APIで分析し、
「買い候補・様子見・売り候補」のスコア付きランキングとして毎日自動更新するWebサイトです。

**このサイトは投資助言ではありません。** あくまで個人の判断材料を整理するための
参考ツールです。最終的な投資判断は必ず自己責任で行ってください。

---

## 全体の仕組み

1. `config/watchlist.yaml` に登録した銘柄（自分専用）、`config/candidate_pool.yaml`
   に登録したテーマ別のハイリスク候補銘柄、`config/portfolio.yaml` に登録した
   「実際に購入した銘柄」について、株価（yfinance）と関連ニュース
   （Google News RSS検索）、世界情勢・マクロ経済ニュースを取得する
2. Gemini APIがそれらを読み、銘柄ごとにスコア・推奨・理由（保有銘柄の場合は
   購入価格からの含み損益や保有日数も踏まえた「保有継続 / 売却検討」の判断）を生成する
   （世界情勢・マクロ経済ニュースも判断材料としてプロンプトに含めている）
3. 結果を `docs/index.html` という1枚のHTMLファイルにまとめる。レポートは
   「①AIによる売買サマリー」「②保有銘柄の売却タイミング」「③世界情勢・マクロ経済ニュース」
   「④自分の銘柄ランキング」「⑤世界情勢から注目したハイリスク・テーマ銘柄」の構成になる
4. GitHub Actionsが平日朝に自動でこの一連の処理を実行し、`docs/index.html` を
   自動更新・push する
5. GitHub Pagesがその `docs/index.html` を常時公開する（＝あなた専用のWebサイトになる）

サーバーを自分で借りたり動かし続けたりする必要はありません。すべて無料の仕組みで完結します。

---

## ステップ1: ローカルで動作確認する

まずは自分のPC上で正しく動くか確認します。

```powershell
cd invest-dashboard
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

次に `.env.example` をコピーして `.env` を作成します。

```powershell
copy .env.example .env
```

`.env` を開いて `GEMINI_API_KEY` に、後述の手順で取得したAPIキーを貼り付けてください。

準備ができたら実行します。

```powershell
cd scripts
python main.py
```

正常に終われば `docs/index.html` が生成されます。ブラウザでダブルクリックして開き、
レポートが表示されるか確認してください。

---

## ステップ2: Gemini APIキーを取得する

1. [Google AI Studio](https://aistudio.google.com/apikey) にGoogleアカウントでログインする
2. 「Create API key」からAPIキーを新規発行する
3. 発行されたキーを `.env` の `GEMINI_API_KEY` に貼り付ける

無料枠には1分あたり・1日あたりのリクエスト数上限がありますが、
「銘柄10〜20件を1日1回分析する」用途であれば通常は十分に収まります。
上限の詳細は [Gemini APIの料金ページ](https://ai.google.dev/pricing) で最新情報を確認してください。

---

## ステップ3: GitHubリポジトリを作成してpushする

1. [github.com](https://github.com) で新しいリポジトリを作成する（Public推奨。
   Privateだと後述のGitHub Pagesが無料では使えない場合があります）
2. このフォルダ（`invest-dashboard`）をpushする

```powershell
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<あなたのユーザー名>/<リポジトリ名>.git
git push -u origin main
```

**注意:** `.env` は `.gitignore` で除外されているのでpushされません
（APIキーが誤って公開される心配はありません）。

---

## ステップ4: GitHub SecretsにAPIキーを登録する

GitHub Actions（自動実行の仕組み）がAPIキーを使えるようにします。

1. GitHub上のリポジトリページで `Settings` タブを開く
2. 左メニューの `Secrets and variables` → `Actions` を開く
3. `New repository secret` をクリック
4. Name: `GEMINI_API_KEY`、Secret: 取得したAPIキーの値、を入力して保存

---

## ステップ5: GitHub Pagesを有効化する

1. リポジトリの `Settings` → `Pages` を開く
2. `Source` を `Deploy from a branch` にする
3. `Branch` を `main`、フォルダを `/docs` に設定して保存する

数分後、`https://<あなたのユーザー名>.github.io/<リポジトリ名>/` でサイトが公開されます。
このURLを知っている人は誰でも閲覧できる状態になる点に注意してください
（検索エンジンには基本的に載りませんが、非公開ではありません）。

---

## ステップ6: 自動実行を試す

1. リポジトリの `Actions` タブを開く
2. `Daily Investment Report` ワークフローを選択
3. `Run workflow` から手動実行してみる
4. 数分後、`docs/index.html` が自動更新され、GitHub Pagesにも反映されることを確認する

普段は平日朝（JST 7時頃）に自動実行されます。時間を変更したい場合は
`.github/workflows/daily-report.yml` 内の `cron` の値を編集してください
（UTC時刻で指定する点に注意）。

---

## 自分の銘柄リストに変更する

`config/watchlist.yaml` を編集してください。銘柄コードの調べ方：

- **日本株**: Yahoo!ファイナンスで証券コードを調べ、末尾に `.T` を付ける（例: `7203.T`）
- **米国株・米国ETF**: ティッカーシンボルをそのまま使う（例: `AAPL`, `VOO`）
- **東証上場ETF**: 日本株と同じく `.T` を付ける（例: `1655.T`）

編集後、ローカルで `python scripts/main.py` を実行して確認するか、
GitHubにpushして次回の自動実行を待てば反映されます。

---

## 保有銘柄の売却タイミング判断について

`config/portfolio.yaml` に、実際に購入した銘柄を登録してください。

```yaml
holdings:
  - symbol: "7203.T"
    name: "トヨタ自動車"
    market: "JP"
    purchase_date: "2026-04-10"   # 購入日 (YYYY-MM-DD)
    purchase_price: 2950           # 購入時の価格（1株あたり）
```

- 登録すると、購入価格からの含み損益（％）・保有日数・株価の動き・関連ニュース・
  世界情勢を踏まえて、AIが「保有継続」か「売却検討」かを判断し、レポート上部の
  「保有銘柄の売却タイミング」セクションに表示します
- 同じ銘柄を複数回に分けて買った場合は、購入ごとに別の項目として追加してください
  （symbolが重複してもかまいません）
- 特に目標利確ラインや損切りラインは設定していません（AIが総合的に判断する方式）。
  もし「+20%で利確検討」のような自分のルールを反映させたくなったら、いつでも追加できます
- 何も登録していない場合、このセクションには案内メッセージのみが表示されます

---

## ハイリスク・テーマ銘柄の候補プールについて

`config/candidate_pool.yaml` は、`watchlist.yaml` とは別枠の「世界情勢的に注目度が
上がっているかもしれない、自分では気づいていないハイリスク銘柄」の候補リストです。
半導体・防衛・AI・資源・暗号資産・国内小型成長株といったテーマ別に、実在するティッカーを
あらかじめ登録してあります。AIが銘柄コードを自由に作ることはなく、必ずこのリストの中から
分析します（存在しない銘柄を誤って提示してしまうリスクを避けるためです）。

- 候補を追加・削除したい場合は、`candidate_pool.yaml` を直接編集してください
- 銘柄数を増やすとGemini APIの呼び出し回数が増える点に注意してください
- 各候補には `nisa_growth_eligible`（NISA成長投資枠の対象になりやすいかの目安）を
  設定していますが、正式な対象可否は必ず証券会社側で確認してください
- レポート上では「注目テーマ銘柄（ハイリスク候補）」という別セクションに、通常の
  銘柄ランキングとは明確に分けて表示され、専用の注意書きが常に添えられます

---

## トラブルシューティング

- **`GEMINI_API_KEY が設定されていません` エラー**: `.env` の内容、またはGitHub Secretsの
  登録名が `GEMINI_API_KEY` になっているか確認してください。
- **特定の銘柄だけ「データ取得失敗」になる**: 銘柄コードが間違っている可能性があります。
  Yahoo!ファイナンスで実際のティッカー表記を確認してください。
- **Gemini APIのエラー（レート制限など）**: 無料枠の上限に達している可能性があります。
  銘柄数を減らすか、時間を置いて再実行してください。
- **GitHub Actionsが失敗する**: `Actions` タブの実行ログでエラー内容を確認できます。
  多くの場合、Secretsの設定漏れが原因です。
