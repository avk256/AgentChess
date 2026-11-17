#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONPATH="$PWD/backend${PYTHONPATH:+:$PYTHONPATH}"
exec python -m uvicorn app:app --app-dir backend --host 127.0.0.1 --port 8000
