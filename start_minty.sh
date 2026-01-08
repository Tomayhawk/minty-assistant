#!/bin/bash

sleep 10

cd "$(dirname "$0")"

if [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "Error: Virtual environment 'venv' not found."
    exit 1
fi

exec python3 main.py
