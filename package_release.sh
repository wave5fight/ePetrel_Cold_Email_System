#!/usr/bin/env bash
set -euo pipefail

PACKAGE_NAME="ePetrel-cold-email-system-mac-windows"
DIST_DIR="dist"
PACKAGE_DIR="${DIST_DIR}/${PACKAGE_NAME}"
ZIP_PATH="${DIST_DIR}/${PACKAGE_NAME}.zip"

required_paths=(
  ".env.example"
  "Doc"
  "database/__init__.py"
  "database/db_manager.py"
  "modules"
  "python_env"
  "static"
  "templates"
  "config.py"
  "requirements.txt"
  "README.md"
  "README_ZH.md"
  "start.bat"
  "start_mac.command"
  "web_app.py"
)

for path in "${required_paths[@]}"; do
  if [ ! -e "${path}" ]; then
    echo "[ERROR] Missing required release path: ${path}" >&2
    exit 1
  fi
done

if [ ! -f "python_env/python.exe" ]; then
  echo "[ERROR] python_env must contain the Windows Python executable: python_env/python.exe" >&2
  exit 1
fi

python_dll="$(find python_env -maxdepth 1 -type f -name 'python3[0-9][0-9].dll' -print -quit)"
if [ -z "${python_dll}" ]; then
  echo "[ERROR] python_env must contain a Windows python3xx.dll runtime." >&2
  exit 1
fi
python_abi="$(basename "${python_dll}" .dll | sed 's/^python//')"

bad_non_windows_ext="$(find python_env -type f \( -name "*.so" -o -name "*.dylib" \) -print | sed -n '1,20p')"
if [ -n "${bad_non_windows_ext}" ]; then
  echo "[ERROR] python_env contains non-Windows compiled Python extensions:" >&2
  echo "${bad_non_windows_ext}" >&2
  echo >&2
  echo "Rebuild python_env on a real Windows machine, then package again." >&2
  echo "Do not install dependencies into python_env from macOS/Linux." >&2
  exit 1
fi

bad_python_abi="$(find python_env -type f \( -name "*.pyd" -o -name "*.so" \) -print \
  | grep -E "cpython-|cp[0-9][0-9][0-9]" \
  | grep -Ev "(cpython-${python_abi}|cp${python_abi}|abi3)" \
  | sed -n '1,20p' || true)"
if [ -n "${bad_python_abi}" ]; then
  echo "[ERROR] python_env contains compiled packages for the wrong Python ABI." >&2
  echo "Expected Python ABI: ${python_abi}" >&2
  echo "${bad_python_abi}" >&2
  echo >&2
  echo "Rebuild python_env with the same Windows Python runtime that is bundled in python_env/." >&2
  exit 1
fi

if [ -d "python_env/Lib/site-packages/bin" ]; then
  echo "[ERROR] python_env/Lib/site-packages/bin exists, which usually means dependencies were installed on macOS/Linux." >&2
  echo "Rebuild python_env on Windows before packaging." >&2
  exit 1
fi

mkdir -p "${DIST_DIR}"
rm -rf "${PACKAGE_DIR}" "${ZIP_PATH}"
mkdir -p "${PACKAGE_DIR}/database"

cp -R .env.example Doc modules python_env static templates config.py requirements.txt README.md README_ZH.md start.bat start_mac.command web_app.py "${PACKAGE_DIR}/"
cp database/__init__.py database/db_manager.py "${PACKAGE_DIR}/database/"

chmod +x "${PACKAGE_DIR}/start_mac.command"

find "${PACKAGE_DIR}" -name "__pycache__" -type d -prune -exec rm -rf {} +
find "${PACKAGE_DIR}" -name "*.pyc" -type f -delete
find "${PACKAGE_DIR}" -name ".DS_Store" -type f -delete
find "${PACKAGE_DIR}" -name "*.log" -type f -delete

if [ -e "${PACKAGE_DIR}/.env" ]; then
  echo "[ERROR] .env should not be included in release package." >&2
  exit 1
fi
if [ -e "${PACKAGE_DIR}/database/storage.db" ] || [ -e "${PACKAGE_DIR}/database/.epetrel_secret.key" ]; then
  echo "[ERROR] Sensitive local database files should not be included in release package." >&2
  exit 1
fi

(cd "${DIST_DIR}" && zip -qr "${PACKAGE_NAME}.zip" "${PACKAGE_NAME}")

echo "Release package created:"
echo "${ZIP_PATH}"
