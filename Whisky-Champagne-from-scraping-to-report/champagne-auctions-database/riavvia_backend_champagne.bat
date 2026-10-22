@echo off
rem Meno memoria per ogni programma Python: numpy/pandas usano 1 thread di calcolo
rem invece di uno per core (prima la RAM finiva: "OpenBLAS error: Memory allocation").
set OPENBLAS_NUM_THREADS=1
set OMP_NUM_THREADS=1
set MKL_NUM_THREADS=1
rem Avvia una sessione di scraping champagne. Se il backend (porta 8001) non e attivo, lo avvia prima.
cd /d "%~dp0"
curl -s -o nul http://127.0.0.1:8001/api/scraper/status
if not errorlevel 1 goto avvia
echo Backend non attivo: lo avvio...
start "Catawiki Backend Champagne" cmd /k "cd backend && ..\.venv\Scripts\python -m uvicorn main:app --reload --host 127.0.0.1 --port 8001"
set /a TENTATIVI=0
:attesa
timeout /t 3 /nobreak >nul
set /a TENTATIVI+=1
curl -s -o nul http://127.0.0.1:8001/api/scraper/status
if not errorlevel 1 goto avvia
if %TENTATIVI% lss 40 goto attesa
echo Il backend non risponde: controlla la finestra "Catawiki Backend Champagne".
pause
exit /b 1
:avvia
echo Backend attivo. Avvio la sessione di scraping...
curl -s -X POST http://127.0.0.1:8001/api/scraper/start
echo.
echo Fatto. Questa finestra si chiude tra 10 secondi.
timeout /t 10 >nul
