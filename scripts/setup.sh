#!/bin/bash
set -e
cd "$(dirname "$0")/.."

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env — add your OPENAI_API_KEY"
fi

echo "Setup complete. Run: ./scripts/start.sh"
