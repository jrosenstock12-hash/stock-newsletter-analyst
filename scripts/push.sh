#!/bin/bash
set -e
cd "$(dirname "$0")/.."
git add -A
git status
git diff --cached --quiet && echo "Nothing to commit" && exit 0
git commit -m "${1:-Update stock-newsletter-analyst}"
git push origin main
echo "Pushed to origin/main"
