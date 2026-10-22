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

:: Controllo se esiste la venv del backend whisky
if not exist "backend\venv" (
    echo [ERR] Venv non trovata: crea backend\venv (vedi README, Installazione).
    pause
    exit /b
)

:: Installazione dipendenze se necessario
echo [1/4] Verifica dipendenze (Pandas/Numpy)...
echo Questa operazione potrebbe richiedere 1-2 minuti. Attendi...
backend\venv\Scripts\python -m pip install -r backend\requirements.txt

:: Sblocca i file per prevenire blocchi di Smart App Control sulle nuove librerie
echo [!] Sblocco file di sistema per Windows Smart App Control...
powershell -Command "Get-ChildItem -Path . -Recurse | Unblock-File"

:: Avvio Backend
echo.
echo [2/4] Avvio API Backend (FastAPI) su Porta 8080...
start "Catawiki Backend Whisky" cmd /k "cd backend && venv\Scripts\python -m uvicorn main:app --reload --host 127.0.0.1 --port 8080"

:: Attesa per il backend di avviarsi
timeout /t 2 /nobreak

:: Avvio Frontend in una nuova finestra
echo [2/4] Avvio Frontend (Vite/React)...
start "Catawiki Frontend" cmd /k "cd frontend && npm run dev -- --port 3001 --clearScreen false"

:: Avvio Tunnel per Accesso Remoto in una nuova finestra
echo [3/4] Avvio Accesso Remoto (Localtunnel)...
start "Catawiki Remote Tunnel" cmd /k "cd frontend && node start_tunnel.js"

:: Avvio Bot Telegram in una nuova finestra
echo [4/4] Avvio Telegram Bot Listener...
start "Catawiki Telegram Bot Whisky" cmd /k "cd scraper && ..\backend\venv\Scripts\python telegram_bot.py"
:: Avvio Scheduler Automatico in una nuova finestra
echo [5/5] Avvio Scheduler Automatico (03:00 / 17:00)...
start "Catawiki Scheduler Whisky" cmd /k "cd scraper && ..\backend\venv\Scripts\python scraper.py"

echo.
echo ✅ Dashboard Whisky avviata!
echo 📊 Frontend: http://localhost:3001
echo 📡 Backend API: http://localhost:8080
echo 🕒 Scheduler: Attivo (03:00 e 17:00)
echo.
pause

echo Premi un tasto per chiudere questo script (i server rimarranno attivi nelle loro finestre).
pause