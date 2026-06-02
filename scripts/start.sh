#!/bin/bash
cd "$(dirname "$0")/.."

for port in 8501 8502 8503; do
  pid=$(lsof -tiTCP:$port -sTCP:LISTEN 2>/dev/null)
  if [ -n "$pid" ]; then
    echo "Stopping process on port $port (PID $pid)..."
    kill -9 $pid 2>/dev/null || true
  fi
done

source .venv/bin/activate
echo "Starting at http://localhost:8503"
exec streamlit run app.py --server.port 8503
