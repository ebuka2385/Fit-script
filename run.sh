#!/bin/bash

# Kill any running instances first
pkill -f "python3 app.py" 2>/dev/null
sleep 0.5

if ! command -v uv &> /dev/null; then
    echo "uv not found. Install it: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

echo ""
echo "  Starting FitScript on two ports..."
echo ""

PORT=8000 uv run python3 app.py &
PID1=$!

PORT=8001 uv run python3 app.py &
PID2=$!

sleep 1

echo "  Account 1  →  http://localhost:8000"
echo "  Account 2  →  http://localhost:8001"
echo ""
echo "  Both instances share the same database."
echo "  Log in with different accounts on each port."
echo ""
echo "  Press Ctrl+C to stop both."
echo ""

trap "echo ''; echo '  Stopping both instances...'; kill $PID1 $PID2 2>/dev/null; exit 0" INT TERM
wait $PID1 $PID2
