# 社内申請ポータル

GitHub CopilotとVS Codeで、既存アプリの理解・要件整理・実装・テスト・レビューを
体験するための、**架空データだけを使うローカル研修用アプリ**です。
アプリ本体の実行に、Azure、Azure DevOps、GitHubのリモート、外部AI APIは必要ありません。
Copilotそのものをオフラインで使えるという意味ではありません。

> このリポジトリは、Privateのサンプルアプリです。`main` は絞り込み未実装の初期アプリです。
> 部署・状態の絞り込みの完成例は `workshop/filtering.patch` にあります。
> ホスト上で実行する場合は、clone後に `uv sync --locked` から始めてください。
> Dev Containerでは依存関係を自動で準備します。初回の依存取得には
> `pypi.org` と `files.pythonhosted.org` への接続が必要です。

## 技術選定と設計

**Python＋Flask＋SQLite＋Jinja2**を選びました。小規模な一覧・入力フォームには
大規模SPAの利点が小さく、Pythonなら業務処理とテストを同じ言語で追えます。
SQLiteはPython標準ライブラリに含まれ、DBサーバーの準備も不要です。
JavaScriptは配色の切り替えだけで、アプリの操作は通常のリンクとフォームで動きます。

Python 3.14を既定とし、3.13も対象にしています。依存関係は`uv.lock`で固定します。
実行時の直接依存はFlaskのみです。開発用にpytest、Ruff、mypyを使います。

| 画面・操作 | 内容 |
| --- | --- |
| 申請一覧 | 新しい日時から表示。総数・状態別件数は全申請の集計 |
| 申請詳細 | 件名、申請者、担当部署、種別、内容、状態、日時 |
| 新規申請 | 入力検証後、「確認待ち」として保存 |
| 状態変更 | 確認待ちから承認済み／差し戻しへ。一度処理した申請は変更不可 |
| JSON API | 一覧・詳細の読み取り専用。画面の一覧と同じ取得処理 |

申請は、ID・件名（1〜80文字）・架空の申請者名（1〜40文字）・担当部署・種別・
内容（10〜1000文字）・状態・作成日時を持ちます。
部署は開発部／営業部／管理部／デザイン部、種別は備品購入／研修参加／在宅勤務です。
名前や文章の前後の空白は除きます。日時はUTCで保存し、画面では日本時間を表示します。

初期アプリでは**部署・状態の絞り込みを実装していません**。
対応していない検索条件を指定すると400を返し、無視して全件を返すことはありません。
完成例は別の差分に分離しています。通常のアプリに故障fixtureは含めていません。

## インストールと起動

### ホスト上で実行する場合

Pythonとuvが必要です。完成例の差分適用と差分の自動テストにはGitも使います。
依存の取得先は公開PyPIです。初回は`pypi.org`と`files.pythonhosted.org`への接続が必要です。
インストール後、アプリの操作・テストに外部接続は必要ありません。
以下はPowerShellで、`request-portal`フォルダー内から実行する例です。

```powershell
uv sync --locked
uv run --locked python -m request_portal serve --port 8765
```

ブラウザーで <http://127.0.0.1:8765/requests> を開きます。
最初の起動で、`instance\portal-demo.sqlite3`に架空データ12件を作成します。
以後の起動では既存の申請を維持します。確認待ち5件、承認済み4件、差し戻し3件です。
停止は、起動したターミナルで **Ctrl+C** を押します。
ポートが使用中なら、`--port 8766`など、空いている番号を指定してください。

開発サーバーを使いますが、デバッガーと自動再読み込みは有効にしていません。
コードを変更したら、一度停止して起動し直してください。
再起動によりフォームの確認用トークンが変わるため、開いた入力画面は再読み込みします。

### Dev Containerで実行する場合

CodespacesとローカルのVS Codeで、同じ開発環境を利用できます。
Python 3.14、uv、Gitをコンテナー内に用意し、アプリと開発用の依存関係は
作成時の`uv sync --locked`で準備します。準備後にアプリを自動起動し、応答可能に
なるまでDev Containerの起動完了を待ちます。

| ファイル | 責務 |
| --- | --- |
| `.devcontainer\Dockerfile` | Pythonと開発ツールのイメージ。uvはバージョンを固定 |
| `.devcontainer\compose.yaml` | 単一コンテナーのビルド、ソースのマウント、実行ユーザー、環境変数 |
| `.devcontainer\devcontainer.json` | VS Code／Codespacesとの連携、拡張機能、依存の初期化、ポート転送 |

**VS Code（ローカル）**では、DockerとDev Containers拡張が必要です。
WindowsではLinuxコンテナーを実行できるDocker Desktopなどを使います。
ホスト側にPythonやuvをインストールする必要はありません。
cloneしたフォルダーをVS Codeで開き、コマンドパレットから
**Dev Containers: Reopen in Container**を実行してください。

**Codespaces**では、GitHubのリポジトリ画面の**Code → Codespaces**から、
この設定を含むブランチを選んで開きます。Codespacesの利用権限と課金設定を確認してください。
既存のCodespaceへ設定を追加した場合は、**Codespaces: Rebuild Container**を実行します。

Dev Containerの起動が完了したら、画面は**Ports**タブに表示された転送先のURLから
開いてください。
アプリはコンテナー内の`127.0.0.1:8765`だけで待ち受けます。
Composeの`ports`によるホストへの公開や、`0.0.0.0`への変更は行いません。
Codespacesの**Port Visibility**は**Private**を維持してください。
アプリに認証がないため、Publicや組織共有へ変更しないでください。
Codespaces内では、`CODESPACE_NAME`、`GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN`、
起動ポートから組み立てた自分の転送先Hostだけを、localhostに加えて許可します。
ローカル実行のHost制限は変更しません。
Dev Containerを停止するとアプリも停止します。コードを変更した場合はDev Containerを
再起動してください。

Linux用の仮想環境は`/home/vscode/.venv`に作成し、ホスト側の`.venv`とは共有しません。
Python／Pylance／Ruff拡張もこの環境に合わせて設定します。
コンテナーを再作成した場合は依存を再準備します。定義を変更した場合は
ローカルでは**Dev Containers: Rebuild Container**、Codespacesでは
**Codespaces: Rebuild Container**を実行してください。

専用デモDBは、マウントされたワークスペースの`instance/portal-demo.sqlite3`に保存します。
ワークスペースが残る停止・再起動・コンテナー再作成では申請データを維持します。
**Codespace自体を削除すると、ワークスペース内のDBも保持されません。**

初回はMCRのイメージ、拡張機能、公開PyPIのuvと依存を取得するため、外部接続が必要です。
これはアプリの操作に外部APIを使うという意味ではありません。
コンテナー内でも、次のコマンドで回帰テストと静的確認を実行できます。

```bash
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy
```

### データの準備とリセット

初期化だけ行う場合は次のコマンドを使います。既存データは上書きしません。

```powershell
uv run --locked python -m request_portal seed
```

作成した申請や状態変更を取り消し、架空データ12件へ戻す場合は、サーバーを停止して
次のコマンドを実行します。**専用DBの申請がすべて削除されます。**

```powershell
uv run --locked python -m request_portal reset-demo --confirm request-portal-demo
```

リセット対象のパスは固定です。DB内の専用マーカーも確認し、別のDBや識別情報が
違うファイルは変更せずエラーにします。フォルダーやDBファイル自体は削除しません。
この操作はコードを初期状態へ戻すものではありません。

## テストと静的確認

テストは毎回一時ディレクトリの専用DBを使い、起動中アプリのデータを変更しません。

```powershell
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy
```

初回取得が済んだ環境では、`uv run --locked --offline pytest -q`のように、
キャッシュ済みの依存だけを使って再実行できます。未準備の端末へオフラインで
インストールできるという意味ではありません。

### 実ブラウザーでの確認（任意）

Windowsにインストール済みのMicrosoft Edgeを使う反復確認も用意しています。
この確認はWindowsのホスト上で実行してください。Dev Container内にはEdgeを追加しません。
ブラウザー確認用の依存は任意の`browser`グループに分け、アプリの実行には使いません。
別のターミナルでポータルを起動し、初期データ12件の状態で実行してください。
この確認は**専用デモDBへ架空申請を2件追加し、承認と差し戻しを行います**。

```powershell
$env:UV_PROJECT_ENVIRONMENT = ".venv-browser"
uv sync --locked --group browser
uv run --locked --group browser python tools\verify_browser.py --stage starter --output .\browser-checks
Remove-Item Env:\UV_PROJECT_ENVIRONMENT
```

完成例では`--stage reference`を指定します。一覧・詳細・フォーム・エラー、
明暗の配色、375px幅、Tab／Enter／矢印キーでの操作を確認し、スクリーンショットと
JSONレポートを保存します。終了後はサーバーを停止し、必要なら専用データをリセットします。
ブラウザー本体のダウンロードや外部ページへのアクセスは行いません。

### Python 3.13での確認

既定の`.venv`を上書きしないよう環境を分けます。

```powershell
$env:UV_PROJECT_ENVIRONMENT = ".venv313"
uv sync --locked --python 3.13
uv run --locked --python 3.13 pytest -q
Remove-Item Env:\UV_PROJECT_ENVIRONMENT
```

## 演習の開始点

配布された状態が**初期アプリ**です。画面上部と`/healthz`の`stage: starter`で確認できます。
部署・状態による絞り込みを、画面とバックエンドの両方へ追加してください。
作成・詳細・状態変更は、変更前から動く機能として回帰確認に使います。

> 申請が増え、一覧から処理すべきものを探しにくくなっています。
> 担当部署と申請状態で絞り込めるようにしてください。
> 既存機能を維持し、ローカルで動作とテストを確認してください。

| 受け入れ条件 | 確認する内容 |
| --- | --- |
| 指定なし／空文字 | 全申請を表示 |
| 部署のみ／状態のみ | 指定した値と一致する申請だけを表示 |
| 部署＋状態 | **両方を満たす申請だけ**を表示。ORではない |
| 該当なし | 0件と説明を表示し、条件を解除できる |
| 不正な値・条件の重複・未対応のキー | 400と説明。SQL文字列へ入力を直接連結しない |
| UIとAPI | 同じ条件・同じ結果。件数も実際の結果に一致 |
| 条件を解除 | 全件表示へ戻る。入力した条件を画面で確認できる |
| 既存機能 | 詳細、作成、状態変更、入力検証、全申請の集計を維持 |

APIの部署コードは`engineering`／`sales`／`corporate`／`design`、
状態コードは`pending`／`approved`／`rejected`です。
一覧は`GET /api/requests`、詳細は`GET /api/requests/1`。
一覧のJSONは`{"items": [...], "count": 12}`で、`count`は表示対象件数です。
完成例では`GET /api/requests?department=engineering&status=pending`を使えます。
`scoutTheme=light`／`dark`は配色確認用で、検索条件ではありません。

### 講師用の完成例

`workshop\filtering.patch`は、初期アプリへ適用できる完成例です。
アプリを丸ごと複製せず、取得処理・一覧画面・テストの変更だけを持ちます。
**参加者の実装へ上書き適用しないでください。**
作業前の別コピーを使い、サーバーを停止してから実行します。
Gitは差分の適用に使うだけで、リポジトリ作成・リモート接続は不要です。
`-c`の指定は、このコマンドだけ改行をLFに保つためのものです。
個人や組織のGit設定は変更しません。

```powershell
git -c core.autocrlf=false -c core.eol=lf apply --check workshop\filtering.patch
git -c core.autocrlf=false -c core.eol=lf apply workshop\filtering.patch
uv run --locked pytest -q
uv run --locked python -m request_portal serve --port 8765
```

画面上部が「完成例」、`/healthz`が`stage: reference`になります。
初期状態へ戻すときは、完成例以外の変更がないコピーで、先に確認します。

```powershell
git -c core.autocrlf=false -c core.eol=lf apply --reverse --check workshop\filtering.patch
git -c core.autocrlf=false -c core.eol=lf apply --reverse workshop\filtering.patch
uv run --locked pytest -q
```

確認が失敗したら適用を中止します。`git reset`や未コミット変更の一括破棄は使いません。
逆適用は完成例のコード差分だけを戻し、申請データは変更しません。

## Copilotへのコンテキストの渡し方

`AGENTS.md`に、変更対象を探すための短い地図と維持する条件をまとめました。
プロジェクト全体や依存の全文を毎回渡さず、要件・対象ファイル・対応するテストから始めます。
完成例は答え合わせ用で、参加者の実装中は参照しません。

例：まず「部署と状態の絞り込みを追加したい。対象ファイルと確認事項だけを整理して」
と依頼し、条件を確定してから実装へ進みます。実装後は結果・差分・失敗したテストを渡します。
出力を短くするだけでなく、不要な探索ややり直しを減らす観点で振り返ります。
利用量の計測器やAI APIはアプリに組み込んでいません。削減率は未測定です。

ワークショップの設計・解説資料は、題材アプリとは分けて
[教材リポジトリ](https://github.com/shinyay/github-copilot-agentic-workshop-with-token-economy)で管理しています。
[モデル選択の解説](https://github.com/shinyay/github-copilot-agentic-workshop-with-token-economy/blob/main/docs/reference/model-selection.md)と
[Token Economy実践ガイド](https://github.com/shinyay/github-copilot-agentic-workshop-with-token-economy/blob/main/docs/reference/token-economy.md)の閲覧には、教材リポジトリへのアクセス権限が必要です。

## 本番システムとの境界

認証、利用者ごとの権限、監査証跡、通知、添付、金額、複数段階の承認、
差し戻し後の編集・再申請、ページ分割、バックアップ運用は対象外です。
申請者を自由入力し、誰でも状態を変更できるため、実際の業務には利用できません。
`serve`はループバックアドレスだけを使います。外部公開しないでください。

フォームの確認用トークン、HTMLの自動エスケープ、Host検証、CSP、入力上限、
SQLのプレースホルダーは備えますが、本番向けの安全性や完全なオフライン動作を保証するものではありません。
TerraformやAzure Pipelinesの定義作成は別の教材範囲で、ここには含めていません。
