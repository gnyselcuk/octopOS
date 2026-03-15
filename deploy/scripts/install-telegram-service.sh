#!/bin/sh

set -eu

MODE="system"
SERVICE_NAME="octopos-telegram.service"
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
ENV_FILE="$PROJECT_ROOT/.env.telegram"

while [ "$#" -gt 0 ]; do
    case "$1" in
        --user)
            MODE="user"
            ;;
        --system)
            MODE="system"
            ;;
        --env-file)
            shift
            ENV_FILE="$1"
            ;;
        *)
            echo "Unknown option: $1" >&2
            echo "Usage: $0 [--user|--system] [--env-file PATH]" >&2
            exit 1
            ;;
    esac
    shift
done

if [ -x "$PROJECT_ROOT/.venv/bin/python" ]; then
    PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN=$(command -v python3)
else
    echo "python3 not found" >&2
    exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
    cp "$PROJECT_ROOT/deploy/systemd/octopos-telegram.env.example" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    echo "Created $ENV_FILE from example. Fill TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_CHAT_IDS first." >&2
    exit 1
fi

if ! grep -Eq '^TELEGRAM_BOT_TOKEN=.+' "$ENV_FILE"; then
    echo "TELEGRAM_BOT_TOKEN is missing in $ENV_FILE" >&2
    exit 1
fi

if ! grep -Eq '^TELEGRAM_ALLOWED_CHAT_IDS=.+' "$ENV_FILE"; then
    echo "TELEGRAM_ALLOWED_CHAT_IDS is missing in $ENV_FILE" >&2
    exit 1
fi

TEMPLATE="$PROJECT_ROOT/deploy/systemd/octopos-telegram.service.template"
TMP_UNIT=$(mktemp)
trap 'rm -f "$TMP_UNIT"' EXIT

SERVICE_USER=$(id -un)

if [ "$MODE" = "user" ]; then
    SERVICE_USER_LINE="# User handled by user systemd"
    WANTED_BY="default.target"
else
    SERVICE_USER_LINE="User=$SERVICE_USER"
    WANTED_BY="multi-user.target"
fi

sed \
    -e "s|__SERVICE_USER_LINE__|$SERVICE_USER_LINE|g" \
    -e "s|__WORKDIR__|$PROJECT_ROOT|g" \
    -e "s|__ENV_FILE__|$ENV_FILE|g" \
    -e "s|__PYTHON_BIN__|$PYTHON_BIN|g" \
    -e "s|__WANTED_BY__|$WANTED_BY|g" \
    "$TEMPLATE" > "$TMP_UNIT"

if [ "$MODE" = "user" ]; then
    UNIT_DIR="$HOME/.config/systemd/user"
    mkdir -p "$UNIT_DIR"
    cp "$TMP_UNIT" "$UNIT_DIR/$SERVICE_NAME"
    systemctl --user daemon-reload
    systemctl --user enable --now "$SERVICE_NAME"
    echo "Installed user service: $UNIT_DIR/$SERVICE_NAME"
    echo "If you want it to survive logout, run: sudo loginctl enable-linger $SERVICE_USER"
else
    if [ "$(id -u)" -ne 0 ]; then
        if ! command -v sudo >/dev/null 2>&1; then
            echo "sudo is required for system service installation" >&2
            exit 1
        fi
        sudo cp "$TMP_UNIT" "/etc/systemd/system/$SERVICE_NAME"
        sudo systemctl daemon-reload
        sudo systemctl enable --now "$SERVICE_NAME"
    else
        cp "$TMP_UNIT" "/etc/systemd/system/$SERVICE_NAME"
        systemctl daemon-reload
        systemctl enable --now "$SERVICE_NAME"
    fi
    echo "Installed system service: /etc/systemd/system/$SERVICE_NAME"
fi

echo "Service installation complete."
