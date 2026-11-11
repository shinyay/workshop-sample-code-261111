#!/usr/bin/env bash
set -euo pipefail

readonly port=8765
readonly log_file=/tmp/request-portal.log

if curl --fail --silent "http://127.0.0.1:${port}/healthz" >/dev/null; then
  exit 0
fi

uv run --locked python -m request_portal serve --port "${port}" >"${log_file}" 2>&1 &
server_pid=$!

for _ in {1..50}; do
  if curl --fail --silent "http://127.0.0.1:${port}/healthz" >/dev/null; then
    exit 0
  fi
  if ! kill -0 "${server_pid}" 2>/dev/null; then
    cat "${log_file}" >&2
    exit 1
  fi
  sleep 0.2
done

cat "${log_file}" >&2
echo "社内申請ポータルの起動確認がタイムアウトしました。" >&2
exit 1