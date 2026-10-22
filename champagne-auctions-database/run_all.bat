@echo off
rem Meno memoria per ogni programma Python: numpy/pandas usano 1 thread di calcolo
rem invece di uno per core (prima la RAM finiva: "OpenBLAS error: Memory allocation").
set OPENBLAS_NUM_THREADS=1
set OMP_NUM_THREADS=1
set MKL_NUM_THREADS=1
setlocal enabledelayedexpansion

echo 🍾 Avvio Catawiki Elite Dashboard...

:: Sblocca i file per prevenire blocchi di Smart App Control
echo [!] Sblocco file di sistema per Windows Smart App Control...
powershell -Command "Get-ChildItem -Path . -Recurse | Unblock-File"

:: Avvio Backend in una nuova finestra (da /backend directory)
:: Installazione dipendenze se necessario
echo [1/4] Verifica dipendenze (Pandas/Numpy)...
echo Questa operazione potrebbe richiedere 1-2 minuti. Attendi...
.venv\Scripts\python -m pip install -r backend\requirements.txt

:: Sblocca i file per prevenire blocchi di Smart App Control sulle nuove librerie
echo [!] Sblocco file di sistema per Windows Smart App Control...
powershell -Command "Get-ChildItem -Path . -Recurse | Unblock-File"

:: Avvio Backend
echo.
echo [2/4] Avvio API Backend (FastAPI) su Porta 8001...
start "Catawiki Backend Champagne" cmd /k "cd backend && ..\.venv\Scripts\python -m uvicorn main:app --reload --host 127.0.0.1 --port 8001"

:: Attesa per il backend di avviarsi
timeout /t 2 /nobreak

:: Avvio Frontend in una nuova finestra
echo [2/4] Avvio Frontend (Vite/React)...
start "Catawiki Frontend" cmd /k "cd frontend && npm run dev -- --clearScreen false"

:: Avvio Tunnel per Accesso Remoto in una nuova finestra
echo [3/4] Avvio Accesso Remoto (Localtunnel)...
start "Catawiki Remote Tunnel" cmd /k "cd frontend && node start_tunnel.js"

:: Avvio Bot Telegram in una nuova finestra
echo [4/4] Avvio Telegram Bot Listener...
start "Catawiki Telegram Bot" cmd /k "cd scraper && ..\.venv\Scripts\python telegram_bot.py"
:: Avvio Scheduler Automatico in una nuova finestra
echo [5/5] Avvio Scheduler Automatico (03:00 / 17:00)...
start "Catawiki Scheduler Champagne" cmd /k "cd scraper && ..\.venv\Scripts\python scraper.py"

echo.
echo ✅ Dashboard avviata!
echo 📊 Frontend: http://localhost:3000
echo 📡 Backend API: http://localhost:8001
echo 🕒 Scheduler: Attivo (03:00 e 17:00)
echo.
pause

echo.
echo ✅ Dashboard in fase di avvio!
echo.
echo 🌐 Backend API: http://127.0.0.1:8001
echo 📊 Dashboard UI: http://localhost:3000
echo.
echo Premi un tasto per chiudere questo script (i server rimarranno attivi nelle loro finestre).
pause