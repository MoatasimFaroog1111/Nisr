#!/bin/sh
set -eu

prepare_runtime_dir() {
    dir="$1"
    mkdir -p "$dir"
    chown -R nisr:nisr "$dir"
    chmod u+rwx "$dir"
}

if [ "$(id -u)" = "0" ]; then
    prepare_runtime_dir /app/data
    prepare_runtime_dir /app/workspace
    prepare_runtime_dir /app/artifacts
    exec gosu nisr "$@"
fi

exec "$@"
