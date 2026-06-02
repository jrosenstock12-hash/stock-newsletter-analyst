#!/bin/bash
cd "$(dirname "$0")/.."
source .venv/bin/activate
python3 -c "
from analyze.llm import test_openai_connection
print('Testing OpenAI...')
print('Result:', test_openai_connection())
"
