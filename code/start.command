#!/bin/bash
# YamProduktion starten – Doppelklick im Finder genügt.
# Beim ersten Start wird eine eigene Python-Umgebung angelegt (dauert 1–2 Minuten, braucht Internet).

cd "$(dirname "$0")" || exit 1
VENV=".venv"

meldung() { osascript -e "display dialog \"$1\" with title \"YamProduktion\" buttons {\"OK\"} default button 1" >/dev/null 2>&1; echo "$1"; }

# Passendes Python suchen: mindestens 3.10, mit funktionierendem sqlite3 und venv.
# Anaconda wird bewusst zuletzt probiert (bringt auf dem Mac manchmal ein defektes SQLite mit).
finde_python() {
  for kandidat in /opt/homebrew/bin/python3 /usr/local/bin/python3 \
                  /Library/Frameworks/Python.framework/Versions/Current/bin/python3 \
                  "$(command -v python3)" /usr/bin/python3; do
    [ -x "$kandidat" ] || continue
    case "$kandidat" in *conda*) continue ;; esac
    if "$kandidat" -c 'import sys, sqlite3, venv; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
      echo "$kandidat"; return 0
    fi
  done
  for kandidat in "$HOME"/anaconda3/bin/python3 "$HOME"/miniconda3/bin/python3; do
    [ -x "$kandidat" ] && "$kandidat" -c 'import sys, sqlite3, venv; sqlite3.connect(":memory:").execute("select 1"); sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null && { echo "$kandidat"; return 0; }
  done
  return 1
}

if [ ! -x "$VENV/bin/python" ]; then
  PY="$(finde_python)" || {
    meldung "Kein passendes Python gefunden (mindestens Version 3.10). Bitte Python von python.org installieren oder im Terminal: brew install python – danach erneut starten."
    exit 1
  }
  echo "Lege Python-Umgebung an mit $PY …"
  "$PY" -m venv "$VENV" || { meldung "Die Python-Umgebung konnte nicht angelegt werden."; exit 1; }
fi

# Pakete installieren, wenn neu oder wenn sich requirements.txt geändert hat
STEMPEL="$VENV/.requirements.md5"
AKTUELL="$(md5 -q requirements.txt 2>/dev/null || md5sum requirements.txt | cut -d' ' -f1)"
if [ ! -f "$STEMPEL" ] || [ "$(cat "$STEMPEL")" != "$AKTUELL" ]; then
  echo "Installiere benötigte Pakete (einmalig) …"
  "$VENV/bin/python" -m pip install --upgrade pip -q
  if "$VENV/bin/python" -m pip install -r requirements.txt -q; then
    echo "$AKTUELL" > "$STEMPEL"
  else
    meldung "Die Pakete konnten nicht installiert werden. Besteht eine Internetverbindung? Dann bitte erneut starten."
    exit 1
  fi
fi

PYTHONPATH="src" exec "$VENV/bin/python" -m yamproduktion
