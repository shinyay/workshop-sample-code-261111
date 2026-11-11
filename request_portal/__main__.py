import argparse
import io
import os
import re
import sqlite3
import sys
from collections.abc import Sequence

from werkzeug.serving import make_server

from . import create_app
from .storage import DEFAULT_DATABASE, initialize, list_requests, reset_demo


def _port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("ポート番号は整数で指定してください。") from error
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("ポート番号は1〜65535で指定してください。")
    return port


def _codespaces_host(port: int) -> str | None:
    if os.environ.get("CODESPACES") != "true":
        return None
    name = os.environ.get("CODESPACE_NAME", "")
    domain = os.environ.get("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN", "")
    host = f"{name}-{port}.{domain}"
    if (
        not name
        or not domain
        or "." in name
        or len(host) > 253
        or any(
            re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?", label) is None
            for label in host.split(".")
        )
    ):
        raise ValueError(
            "Codespacesの転送先情報が不正です。"
            "CODESPACE_NAMEとGITHUB_CODESPACES_PORT_FORWARDING_DOMAINを確認してください。"
        )
    return host


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="架空の社内申請ポータル（ローカル研修専用）")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="127.0.0.1で起動します。公開用ではありません。")
    serve.add_argument("--port", type=_port, default=8765)
    commands.add_parser("seed", help="専用データベースを初期化します。既存の申請は変更しません。")
    reset = commands.add_parser(
        "reset-demo", help="専用DBの申請を削除し、架空データ12件に戻します。"
    )
    reset.add_argument("--confirm", choices=["request-portal-demo"], required=True)
    args = parser.parse_args(argv)

    try:
        if args.command == "seed":
            initialize(DEFAULT_DATABASE)
            print(f"デモデータ: {DEFAULT_DATABASE} ({len(list_requests(DEFAULT_DATABASE))}件)")
        elif args.command == "reset-demo":
            reset_demo(DEFAULT_DATABASE)
            print(f"専用デモデータを12件に戻しました: {DEFAULT_DATABASE}")
        else:
            forwarded_host = _codespaces_host(args.port)
            app = create_app()
            if forwarded_host is not None:
                app.config["TRUSTED_HOSTS"].append(forwarded_host)
            with make_server("127.0.0.1", args.port, app, threaded=True) as server:
                print(f"社内申請ポータル: http://127.0.0.1:{args.port}/requests", flush=True)
                print(
                    "架空データのみ入力してください。停止するには Ctrl+C を押してください。",
                    flush=True,
                )
                try:
                    server.serve_forever()
                except KeyboardInterrupt:
                    print("\nサーバーを停止しました。")
    except (OSError, sqlite3.Error, ValueError) as error:
        parser.exit(1, f"起動またはデータ操作に失敗しました: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
