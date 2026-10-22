@echo off
rem Meno memoria per ogni programma Python: numpy/pandas usano 1 thread di calcolo
rem invece di uno per core (prima la RAM finiva: "OpenBLAS error: Memory allocation").
set OPENBLAS_NUM_THREADS=1
set OMP_NUM_THREADS=1
set MKL_NUM_THREADS=1
rem Riavvia il bot Telegram whisky con il codice aggiornato (log silenzioso).
rem Prima chiudi la finestra "Catawiki Telegram Bot Whisky" se e' aperta.
cd /d "%~dp0"
start "Catawiki Telegram Bot Whisky" cmd /k "cd scraper && ..\backend\venv\Scripts\python telegram_bot.py"
