#!/bin/bash

echo "🍾 Avvio Catawiki Elite Dashboard (Mac)..."

# Verifica ambiente virtuale Python
if [ ! -d ".venv" ]; then
    echo "[!] Virtual Environment non trovato. Creazione in corso..."
    python3 -m venv .venv
fi

# 1. Installazione dipendenze Backend
echo "[1/4] Verifica dipendenze (Pandas/Numpy)..."
.venv/bin/python -m pip install -r backend/requirements.txt

# 2. Avvio Backend
echo "[2/4] Avvio API Backend (FastAPI) su Porta 8001..."
(cd backend && ../.venv/bin/python -m uvicorn main:app --reload --host 127.0.0.1 --port 8001) &
BACKEND_PID=$!

sleep 2

# 3. Avvio Frontend
echo "[3/4] Verifica pacchetti Frontend e Avvio (Vite/React)..."
(cd frontend && npm install && npm run dev -- --clearScreen false) &
FRONTEND_PID=$!

# 4. Avvio Tunnel
echo "[4/4] Avvio Accesso Remoto (Localtunnel)..."
(cd frontend && node start_tunnel.js) &
TUNNEL_PID=$!

# 5. Avvio Bot Telegram (Opzionale, si consiglia di controllare se c'è connessione)
echo "[5/5] Avvio Telegram Bot e Scheduler..."
(cd scraper && ../.venv/bin/python telegram_bot.py) &
BOT_PID=$!

(cd scraper && ../.venv/bin/python scraper.py) &
SCHEDULER_PID=$!

echo ""
echo "✅ Dashboard avviata con successo in background!"
echo "📊 Frontend: http://localhost:3000"
echo "📡 Backend API: http://127.0.0.1:8001"
echo ""
echo "Premi CTRL+C qui per chiudere TUTTI i server contemporaneamente."

# Cattura la chiusura dello script per killare tutti i processi figli
trap "echo 'Chiusura dei server...'; kill $BACKEND_PID $FRONTEND_PID $TUNNEL_PID $BOT_PID $SCHEDULER_PID; exit" INT
wait
