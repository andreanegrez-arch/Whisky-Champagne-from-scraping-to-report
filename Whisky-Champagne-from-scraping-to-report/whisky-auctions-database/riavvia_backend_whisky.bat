@echo off
rem Meno memoria per ogni programma Python: numpy/pandas usano 1 thread di calcolo
rem invece di uno per core (prima la RAM finiva: "OpenBLAS error: Memory allocation").
set OPENBLAS_NUM_THREADS=1
set OMP_NUM_THREADS=1
set MKL_NUM_THREADS=1
rem Avvia il backend whisky (porta 8080) se non e' gia' acceso, poi una sessione di scraping.
cd /d "%~dp0"
for /l %%i in (1,1,3) do (
  curl -s -o nul --max-time 20 http://127.0.0.1:8080/api/scraper/status && goto avvia
  timeout /t 2 /nobreak >nul
)
echo Backend whisky non attivo: lo avvio...
start "Catawiki Backend Whisky" cmd /k "cd backend && venv\Scripts\python -m uvicorn main:app --reload --host 127.0.0.1 --port 8080"
set /a TENTATIVI=0
:attesa
timeout /t 3 /nobreak >nul
set /a TENTATIVI+=1
curl -s -o nul --max-time 20 http://127.0.0.1:8080/api/scraper/status
if not errorlevel 1 goto avvia
if %TENTATIVI% lss 40 goto attesa
echo Il backend non risponde: controlla la finestra "Catawiki Backend Whisky".
pause
exit /b 1
:avvia
echo Backend whisky attivo. Avvio la sessione di scraping...
curl -s -X POST http://127.0.0.1:8080/api/scraper/start
echo.
echo Fatto. Questa finestra si chiude tra 10 secondi.
timeout /t 10 >nul
