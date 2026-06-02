#!/bin/bash
# Restart the app cleanly (kills stale Streamlit servers only)
cd "$(dirname "$0")"

for port in 8501 8502 8503; do
  pid=$(lsof -tiTCP:$port -sTCP:LISTEN 2>/dev/null)
  if [ -n "$pid" ]; then
    echo "Stopping old server on port $port (PID $pid)..."
    kill -9 $pid 2>/dev/null
  fi
done

sleep 1
source .venv/bin/activate
echo ""
echo "Starting fresh at http://localhost:8503"
echo "Press Ctrl+C to stop"
echo ""
streamlit run app.py
