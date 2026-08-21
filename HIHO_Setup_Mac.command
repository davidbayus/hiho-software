#!/bin/bash
# ============================================================
#  HIHO MOCAP — One-Click Python Environment Setup (Mac)
#  Double-click this file. If macOS blocks it, right-click
#  the file and choose "Open" instead.
# ============================================================
set -e

echo ""
echo "=== HIHO Mocap — Python Environment Setup ==="
echo ""
echo "This will take a few minutes. Leave this window open."
echo ""

# --- Step 1: install uv if it isn't already installed ---
if ! command -v uv >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/uv" ]; then
    echo "[1/3] Installing uv (Python environment manager)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
else
    echo "[1/3] uv already installed — skipping."
fi
export PATH="$HOME/.local/bin:$PATH"

# --- Step 2: create the environment with Python 3.11 ---
echo ""
echo "[2/3] Creating Python 3.11 environment at ~/freemocap-env ..."
uv venv "$HOME/freemocap-env" --python 3.11

# --- Step 3: install FreeMoCap ---
echo ""
echo "[3/3] Installing FreeMoCap (this is the slow part, be patient)..."
uv pip install --python "$HOME/freemocap-env/bin/python" "freemocap==1.8.2"

# --- Done ---
echo ""
echo "============================================================"
echo "  DONE!"
echo ""
echo "  Now open Blender and go to:"
echo "  Edit > Preferences > Add-ons > HIHO Mocap"
echo ""
echo "  Set 'FreeMoCap environment' to:"
echo ""
echo "  $HOME/freemocap-env/bin/python"
echo ""
echo "  (The path above is copied to your clipboard already.)"
echo "============================================================"
echo ""
printf "%s" "$HOME/freemocap-env/bin/python" | pbcopy
read -p "Press Enter to close this window..."
