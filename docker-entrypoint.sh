#!/bin/sh
# Container entrypoint. Normally the image runs as the unprivileged user
# sylvex (Dockerfile USER) and this only execs the command. When Railway
# starts the API as root (RAILWAY_RUN_UID=0, needed because volumes are
# mounted root-owned), it prepares the erasure journal directory on the
# volume for sylvex and then drops to sylvex for the actual process.
set -eu
if [ "$(id -u)" = "0" ]; then
  if ! command -v setpriv >/dev/null 2>&1; then
    echo "SYLVEX_ENTRYPOINT: setpriv missing; refusing to run the service as root" >&2
    exit 1
  fi
  if [ -n "${SYLVEX_ERASURE_JOURNAL_DIR:-}" ]; then
    case "$SYLVEX_ERASURE_JOURNAL_DIR" in
      /*) ;;
      *) echo "SYLVEX_ENTRYPOINT: journal path must be absolute" >&2; exit 1 ;;
    esac
    if [ -L "$SYLVEX_ERASURE_JOURNAL_DIR" ]; then
      echo "SYLVEX_ENTRYPOINT: journal path is a symlink" >&2; exit 1
    fi
    mkdir -p "$SYLVEX_ERASURE_JOURNAL_DIR"
    chown 10001:10001 "$SYLVEX_ERASURE_JOURNAL_DIR"
    chmod 700 "$SYLVEX_ERASURE_JOURNAL_DIR"
  fi
  export HOME=/home/sylvex USER=sylvex LOGNAME=sylvex
  echo "SYLVEX_ENTRYPOINT: journal prepared; dropping to uid 10001" >&2
  exec setpriv --reuid=10001 --regid=10001 --clear-groups -- "$@"
fi
exec "$@"
