# このアプリを変更するとき

架空の社内申請ポータルを使う研修用アプリです。Python 3.14、Flask、SQLite、
サーバー側HTMLで構成します。Node.js、外部API、クラウド、認証サービスは不要です。

## 必要な場所から読む

| 関心事 | ファイル |
| --- | --- |
| 業務用の値、入力検証 | `request_portal\domain.py` |
| HTTP、フォーム、JSON API | `request_portal\__init__.py` |
| SQL、初期化、架空データのリセット | `request_portal\storage.py` |
| 固定の架空データ | `request_portal\demo_data.py` |
| 一覧、詳細、新規申請 | `request_portal\templates\list.html` / `detail.html` / `new.html` |
| 共通画面と見た目 | `request_portal\templates\base.html` / `request_portal\static\portal.css` |
| 回帰確認 | `tests\test_portal.py` / `test_storage.py` / `test_cli.py` |
| 任意の実ブラウザー確認 | `tools\verify_browser.py` |
| 演習の受け入れ条件・利用手順 | `README.md` |
| 講師用の完成例 | `workshop\filtering.patch`（参加者の作業中は読まない） |

最初に変更対象と対応するテストを確認し、必要になった場所だけ追加で読みます。
`.venv`、`uv.lock`、`instance`、キャッシュの内容を一括で読み込まないでください。
トークン削減率や品質改善率を測定せずに主張しないでください。

## 維持する条件

- 日本語の画面、コードの英語識別子、パラメーター化したSQLを維持します。
- 入力不正は画面またはJSONで説明し、正常な結果として扱いません。
- 一覧・詳細・作成・状態変更の回帰テストを残します。処理済みの申請は変更しません。
- UIとJSON APIの一覧は同じ取得処理を使います。組み合わせ条件はANDです。
- 本物の個人情報・機密情報、秘密情報、外部送信機能を追加しません。
- `serve`は`127.0.0.1`のみです。認証がないため外部公開しません。
- リセットは識別済みの専用DBだけを対象にします。削除範囲を広げません。
- 初期アプリと完成例を明示し、通常のアプリに意図的なバグを残しません。
- 小さな変更に新しいフレームワークや依存を追加しません。

## 確認コマンド

アプリのルートで、変更に対応するテストから実行します。

```powershell
uv run --locked pytest tests\test_portal.py -q
uv run --locked ruff check .
uv run --locked mypy
```

全体の確認は `uv run --locked pytest -q` です。実行失敗や未確認の範囲は明記します。
