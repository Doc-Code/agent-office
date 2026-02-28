#!/usr/bin/env bash
# Agent Office — one-command startup
# Usage: ./scripts/start.sh
#
# Starts all 3 services:
#   - Backend (FastAPI :8000)
#   - Frontend (Next.js :3000)
#   - PTY Sidecar (Express :8001)
#
# Uses tmux if available, otherwise runs in background with output to /tmp/

set -euo pipefail
cd "$(dirname "$0")/.."

ROOT_DIR=$(pwd)

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}Agent Office — Starting all services${NC}"
echo ""

# Check dependencies
if ! command -v uv &> /dev/null; then
    echo "ERROR: uv not found. Install: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

if ! command -v node &> /dev/null; then
    echo "ERROR: node not found. Install Node.js first."
    exit 1
fi

# Install deps if needed
if [ ! -d "backend/.venv" ]; then
    echo -e "${YELLOW}Installing backend dependencies...${NC}"
    cd backend && uv sync && cd ..
fi

if [ ! -d "frontend/node_modules" ]; then
    echo -e "${YELLOW}Installing frontend dependencies...${NC}"
    cd frontend && npm install && cd ..
fi

if [ ! -d "pty-sidecar/node_modules" ]; then
    echo -e "${YELLOW}Installing PTY sidecar dependencies...${NC}"
    cd pty-sidecar && npm install && cd ..
fi

# Use tmux if available
if command -v tmux &> /dev/null; then
    SESSION="agent-office"

    if tmux has-session -t "$SESSION" 2>/dev/null; then
        echo -e "${YELLOW}Session already running. Attaching...${NC}"
        tmux attach -t "$SESSION"
        exit 0
    fi

    tmux new-session -d -s "$SESSION" -n backend
    tmux send-keys -t "$SESSION:backend" "cd $ROOT_DIR/backend && make dev" Enter

    tmux new-window -t "$SESSION" -n frontend
    tmux send-keys -t "$SESSION:frontend" "cd $ROOT_DIR/frontend && make dev" Enter

    tmux new-window -t "$SESSION" -n pty-sidecar
    tmux send-keys -t "$SESSION:pty-sidecar" "cd $ROOT_DIR/pty-sidecar && npx tsx src/index.ts" Enter

    tmux select-window -t "$SESSION:backend"

    echo -e "${GREEN}All services started in tmux session '${SESSION}'${NC}"
    echo ""
    echo -e "  ${BLUE}Backend:${NC}     http://localhost:8000"
    echo -e "  ${BLUE}Frontend:${NC}    http://localhost:3000"
    echo -e "  ${BLUE}PTY Sidecar:${NC} http://localhost:8001"
    echo ""
    echo -e "  Attach: ${YELLOW}tmux attach -t ${SESSION}${NC}"
    echo -e "  Stop:   ${YELLOW}tmux kill-session -t ${SESSION}${NC}"
else
    # Fallback: background processes
    echo -e "${YELLOW}tmux not found, using background processes${NC}"

    cd "$ROOT_DIR/backend" && make dev > /tmp/agent-office-backend.log 2>&1 &
    echo "  Backend PID: $!"

    cd "$ROOT_DIR/frontend" && make dev > /tmp/agent-office-frontend.log 2>&1 &
    echo "  Frontend PID: $!"

    cd "$ROOT_DIR/pty-sidecar" && npx tsx src/index.ts > /tmp/agent-office-sidecar.log 2>&1 &
    echo "  PTY Sidecar PID: $!"

    echo ""
    echo -e "${GREEN}Services starting in background.${NC}"
    echo -e "  Logs: /tmp/agent-office-*.log"
    echo -e "  Stop: kill the PIDs above or use: pkill -f 'agent-office'"
fi
