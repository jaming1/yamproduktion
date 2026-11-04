#!/bin/bash
# Alle Tests ausführen (Rechnungen, Projektdatei, PDF, Oberfläche mit Screenshots).
cd "$(dirname "$0")" || exit 1
[ -x .venv/bin/python ] || { echo "Bitte zuerst start.command einmal ausführen."; exit 1; }
.venv/bin/python -m pip install -q pytest
.venv/bin/python -m pytest -q
echo; echo "Screenshots liegen in tests/screenshots/"
