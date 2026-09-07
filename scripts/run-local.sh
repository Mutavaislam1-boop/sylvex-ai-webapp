#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
# Uses a separate environment; the existing .venv is not overwritten.
if [ ! -x .venv-secure/bin/python ]; then
  echo 'Create .venv-secure with Python 3.12 and install requirements.txt first.' >&2
  exit 1
fi
exec .venv-secure/bin/python -m uvicorn main:app --host 127.0.0.1 --port "${PORT:-8000}"
