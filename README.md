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
   「①AIによる売買サマリー」「②AIの的中率」「③暗号資産」「④保有銘柄の売却タイミング」
   「⑤世界情勢・マクロ経済ニュース」「⑥自分の銘柄ランキング」
   「⑦世界情勢から注目したハイリスク・テーマ銘柄」の構成になる
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

普段は毎日朝9:30（JST）に自動実行されます。時間を変更したい場合は
`.github/workflows/daily-report.yml` 内の `cron` の値を編集してください
（UTC時刻で指定する点に注意）。

**注意:** GitHub Actionsの `schedule` は「指定した時刻ちょうどに必ず実行される」もの
ではなく、GitHub全体の混雑状況によって数分〜数時間遅れることがあります
（GitHub公式のドキュメントにも明記されている既知の仕様です）。決まった時刻に
確実に更新したい場合は、後述の「決まった時刻に確実に更新したい場合」を参照してください。

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

各銘柄に任意項目 `theme`（テーマ名の自由記述）と `amount_invested_jpy`（その購入で実際に
投資した円換算金額）を追加すると、「保有銘柄の売却タイミング」セクションの冒頭に
**テーマ別配分**（投資額の何%がどのテーマに偏っているか）が表示されます。「買うべき/減らすべき」
といった判断は表示せず、あくまで現状を数字で確認するための機能です。`amount_invested_jpy` を
入力していない銘柄は、この集計から除外されます。

同じセクションには**NISA成長投資枠の使用状況**（概算）も表示されます。`amount_invested_jpy`が
入力されている保有銘柄をすべて「NISA成長投資枠で購入したもの」とみなし、年間枠（¥2,400,000）と
生涯投資枠（¥12,000,000）に対してどれだけ使っているかを表示します。このアプリに登録した
購入情報だけに基づく概算のため、正式な消化額は必ず証券会社側の画面で確認してください。
一般口座（NISA以外）での購入が混ざる場合は、この集計が実態と一致しないのでご注意ください。

### 株を買ったときの登録を楽にする

`portfolio.yaml` を手で編集する代わりに、`scripts/add_holding.py` を使うとコマンド1つで
登録できます。銘柄コードと投資額（円）だけ指定すれば、直近の終値をyfinanceから自動取得し、
`config/watchlist.yaml`・`config/candidate_pool.yaml` に同じ銘柄があれば表示名・テーマも
自動で補ってくれます。

```powershell
cd scripts
python add_holding.py add --symbol AAPL --amount 3000
```

日付・表示名・市場区分・テーマを指定したい場合は、それぞれ `--date`・`--name`・`--market`・
`--theme` で上書きできます（例: `python add_holding.py add --symbol 7011.T --amount 5000 --date 2026-07-24`）。
実行すると `config/portfolio.yaml` の末尾に新しい保有銘柄が追記されます（既存のコメントは
消えません）。追記後の内容を確認してからGitHubにpushしてください。

売却した場合は `remove` サブコマンドで削除できます（同じ銘柄を複数回買っている場合は
`--date` で購入日を指定して絞り込んでください）。

```powershell
python add_holding.py remove --symbol AAPL --date 2026-07-22
```

### サイト（GitHub Issue）から登録・削除する

ターミナルを使わずスマホのブラウザからでも登録・削除できるように、GitHubのIssueフォームを
用意しています。リポジトリの `Issues` タブ →`New issue` から

- **保有銘柄の追加**: 買ったときに使う。銘柄コードと投資額を入力するだけでOK
- **保有銘柄の削除（売却済み）**: 売ったときに使う。銘柄コードを入力するだけでOK

を選んで送信すると、GitHub Actionsが自動で `config/portfolio.yaml` を更新し、結果を
Issueへのコメントで知らせてIssueを自動的にクローズします。この処理はリポジトリ所有者
本人が作成したIssueにのみ反応します（このリポジトリはPublicなので、他人が同じ操作を
できないようにするための制限です）。

---

## AIの的中率について

レポート上部の「AIの的中率」セクションでは、AIが過去に出した「買い候補」「売り候補」
「売却検討」の判定が、その後実際に当たっていたかを自動で検証・集計しています。

- 判定を出した日から**7日後**の株価と比較し、判定の方向（上昇を期待/下落を期待）と
  実際の値動きの符号が一致していれば「的中」、逆であれば「不的中」とします
- 変化率が±1%以内の小さな動きは「様子見扱い」として、的中率の集計からは除外します
  （ノイズのような小さな値動きだけで的中・不的中を決めないため）
- 「様子見」「保有継続」（方向性を示さない判定）は、そもそも検証対象にしていません
- 判定から7日経つまでは「検証待ち」として扱われ、まだ的中率には反映されません
- この機能はAI自身の判断の信頼性を確認するためのものであり、個別銘柄の
  売買を推奨するものではありません

データは `data/track_record.json` に保存されます。過去の全件を保持すると
ファイルが際限なく増え続けてしまうため、確定した結果は種別ごとの件数にのみ
集計し、個別の履歴は直近20件分だけを保持する設計になっています。

---

## 「売却検討」のメール通知について

保有銘柄が**新たに**「売却検討」と判定されたとき、Gmail経由でメール通知を送る機能です。
「前回はそうではなかったが今回そうなった」銘柄だけが対象で、既に売却検討のまま
何日も経過している銘柄については毎日は通知しません（同じ内容を送り続けて
煩わしくならないようにするためです）。

設定は任意です。設定しなくてもアプリ本体（レポート生成）には影響しません。

### 設定手順

1. 通知の送信元にするGmailアカウントで、[Googleアカウントのアプリパスワード発行ページ](https://myaccount.google.com/apppasswords)
   にアクセスし、新しいアプリパスワード（16桁の英数字）を発行する
   （2段階認証が有効になっている必要があります）
2. リポジトリの `Settings` → `Secrets and variables` → `Actions` → `New repository secret`
   から、以下を登録する

   | Name | Secret |
   |---|---|
   | `GMAIL_ADDRESS` | 送信元のGmailアドレス |
   | `GMAIL_APP_PASSWORD` | 手順1で発行したアプリパスワード |
   | `NOTIFY_TO_EMAIL` | 通知を受け取りたいメールアドレス（省略時は`GMAIL_ADDRESS`宛） |

ローカルで試したい場合は、`.env` に同じ変数名で追記してください。
未設定の場合は通知処理が自動的にスキップされ、エラーにはなりません。

的中率は表示するだけでなく、判定タイプごとに**5件以上**確定した時点から、
AIへのプロンプトにも「あなたの過去の『買い候補』判定はX件中Y件的中しています」
という形で渡され、次回以降の判断（スコアの付け方・確信度）に反映されます。
1つの銘柄について前回の判断だけを振り返る既存の「反省機能」とは別に、
判定タイプ全体としての傾向をAI自身にフィードバックする仕組みです。
件数がまだ少ないうちはノイズが大きいため、5件未満の判定タイプはプロンプトに含めません。

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

## 決まった時刻に確実に更新したい場合（外部cronサービスとの連携）

GitHub Actionsの `schedule` は遅延することがあるため、「毎朝9:30ちょうどに必ず
更新してほしい」場合は、無料の外部cronサービス（[cron-job.org](https://cron-job.org)）
からGitHubに「今すぐ実行して」と直接命令を送る方法があります。GitHub側の
混雑状況に左右されず、指定時刻ぴったりに実行されます。

**この設定にはあなた自身のGitHubアカウントで発行するトークンを使うため、
以下の手順はご自身で行ってください（私が代行することはできません）。**

### 1. GitHubで、このリポジトリ専用のアクセストークンを発行する

1. GitHubの [Fine-grained personal access tokens](https://github.com/settings/personal-access-tokens/new) のページを開く
2. `Token name` に分かりやすい名前（例: `invest-dashboard-cron`）を入力
3. `Expiration` は任意の期限（90日など。切れたら作り直せばOK）
4. `Repository access` で `Only select repositories` を選び、このリポジトリ
   （`invest-dashboard`）だけを選択する
5. `Permissions` → `Repository permissions` → `Actions` を `Read and write` に設定
6. `Generate token` をクリックし、表示されたトークン（`github_pat_...` で始まる文字列）を
   **その場でコピーして控えておく**（後から二度と表示されません）

### 2. cron-job.orgに登録する

1. [cron-job.org](https://cron-job.org) で無料アカウントを作成する
2. ログイン後、`CREATEJOB` から新しいジョブを作成する
3. 以下の内容を設定する：

   | 項目 | 値 |
   |---|---|
   | Title | `invest-dashboard daily trigger` |
   | Address (URL) | `https://api.github.com/repos/z1170099-code/invest-dashboard/actions/workflows/daily-report.yml/dispatches` |
   | Request method | `POST` |
   | Schedule | 毎日 9:30（タイムゾーンをAsia/Tokyoに設定できる場合はそれを選択。UTCしか選べない場合は0:30 UTCを指定） |

4. `Advanced` タブ（または `Headers` / `Body` 設定欄）で以下を追加：

   **Headers:**
   ```
   Authorization: Bearer <手順1でコピーしたトークン>
   Accept: application/vnd.github+json
   Content-Type: application/json
   ```

   **Body (JSON):**
   ```json
   {"ref":"main"}
   ```

5. 保存し、`Test run`（テスト実行）ボタンがあれば一度試してみる
6. GitHubリポジトリの `Actions` タブで、`Daily Investment Report` が実行されていれば成功

既存の `schedule`（GitHub側のcron設定）はそのまま残しておいて問題ありません。
仮に両方が近い時間に実行されても、変更がなければ自動コミットは発生しない
（`git diff --cached --quiet` でスキップされる）ため、二重更新の心配はありません。

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
