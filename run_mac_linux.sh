#!/bin/bash
echo "Připravuji prostředí pro S&P 500 Radar..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
