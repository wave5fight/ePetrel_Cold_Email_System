#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

APP_HOST="127.0.0.1"
APP_PORT="8000"
APP_URL="http://${APP_HOST}:${APP_PORT}"
VENV_DIR="epetrelcodemailenv"
DEPS_MARKER="${VENV_DIR}/.epetrel_deps_ready"

clear
echo "=========================================="
echo "  ePetrel Cold Email System - macOS"
echo "=========================================="
echo

if ! command -v python3 >/dev/null 2>&1; then
  echo "[ERROR] python3 was not found."
  echo "Please install Python 3.10 or newer from https://www.python.org/downloads/."
  echo
  read -r -p "Press Enter to close..."
  exit 1
fi

if [ ! -f "web_app.py" ]; then
  echo "[ERROR] web_app.py was not found."
  echo "Please run this file from the ePetrel project folder."
  echo
  read -r -p "Press Enter to close..."
  exit 1
fi

if [ ! -d "templates" ] || [ ! -d "static" ]; then
  echo "[ERROR] templates/ or static/ folder is missing."
  echo
  read -r -p "Press Enter to close..."
  exit 1
fi

mkdir -p database logs

if [ ! -d "${VENV_DIR}" ]; then
  echo "First launch: creating local Python environment..."
  python3 -m venv "${VENV_DIR}"
fi

source "${VENV_DIR}/bin/activate"

if [ ! -f "${DEPS_MARKER}" ]; then
  echo "Installing Python dependencies. This needs internet on first launch..."
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
  touch "${DEPS_MARKER}"
fi

echo
echo "Starting local server at ${APP_URL}"
echo "Keep this Terminal window open while using ePetrel."
echo

(sleep 2 && open "${APP_URL}") >/dev/null 2>&1 &

python -m uvicorn web_app:app --host "${APP_HOST}" --port "${APP_PORT}"

echo
echo "ePetrel has stopped. If this was unexpected, check the error message above."
read -r -p "Press Enter to close..."
