#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
#  Doomsday Prep — macOS launcher
#  Double-click this file (or run it in Terminal) to start the full stack.
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
FRONTEND_URL="http://localhost:3000"
BACKEND_URL="http://localhost:8000"

cd "$APP_DIR"

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║          DOOMSDAY PREP — Starting stack          ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# ── Preflight checks ─────────────────────────────────────────────────────────

if ! command -v docker &>/dev/null; then
  echo "❌  Docker not found. Install Docker Desktop first."
  echo "    https://www.docker.com/products/docker-desktop/"
  read -n 1 -s -r -p "Press any key to exit..."
  exit 1
fi

if ! docker info &>/dev/null; then
  echo "❌  Docker daemon is not running. Start Docker Desktop and try again."
  read -n 1 -s -r -p "Press any key to exit..."
  exit 1
fi

if [ ! -f "$APP_DIR/.env" ]; then
  echo "⚠️   No .env file found — copying from .env.example"
  if [ -f "$APP_DIR/.env.example" ]; then
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    echo "    ✓ Created .env — edit it to add your API keys before using all features."
  else
    echo "❌  .env.example not found either. Cannot continue."
    read -n 1 -s -r -p "Press any key to exit..."
    exit 1
  fi
fi

# ── Start Docker Compose ──────────────────────────────────────────────────────

echo "▶  Starting services (postgres, redis, backend, frontend)..."
echo "   This may take a minute on first run (image build)."
echo ""

docker compose up --build -d

echo ""
echo "⏳  Waiting for services to become healthy..."

# Wait for backend
BACKEND_READY=false
for i in $(seq 1 30); do
  if curl -sf "$BACKEND_URL/health" &>/dev/null; then
    BACKEND_READY=true
    break
  fi
  sleep 2
  printf "."
done
echo ""

if [ "$BACKEND_READY" = false ]; then
  echo "⚠️   Backend did not respond after 60s — it may still be starting."
  echo "    Check logs with:  docker compose logs backend"
fi

# Wait for frontend
FRONTEND_READY=false
for i in $(seq 1 20); do
  if curl -sf "$FRONTEND_URL" &>/dev/null; then
    FRONTEND_READY=true
    break
  fi
  sleep 2
  printf "."
done
echo ""

# ── Open browser ──────────────────────────────────────────────────────────────

if [ "$FRONTEND_READY" = true ]; then
  echo "✅  Stack is up!"
  echo ""
  echo "   Frontend : $FRONTEND_URL"
  echo "   Backend  : $BACKEND_URL"
  echo "   API docs : $BACKEND_URL/docs"
  echo ""
  open "$FRONTEND_URL"
else
  echo "⚠️   Frontend did not respond yet — opening anyway..."
  echo ""
  echo "   Frontend : $FRONTEND_URL  (may take another few seconds)"
  echo "   Backend  : $BACKEND_URL"
  echo "   API docs : $BACKEND_URL/docs"
  echo ""
  open "$FRONTEND_URL"
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  To stop:    docker compose down"
echo "  To restart: docker compose restart"
echo "  Logs:       docker compose logs -f"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Press any key to close this window (stack keeps running in background)"
read -n 1 -s -r
