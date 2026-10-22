@echo off
rem Meno memoria per ogni programma Python: numpy/pandas usano 1 thread di calcolo
rem invece di uno per core (prima la RAM finiva: "OpenBLAS error: Memory allocation").
set OPENBLAS_NUM_THREADS=1
set OMP_NUM_THREADS=1
set MKL_NUM_THREADS=1
rem Avvia lo scheduler whisky (sessioni 03:00 e 17:00) con il codice aggiornato.
cd /d "%~dp0"
start "Catawiki Scheduler Whisky" cmd /k "cd scraper && ..\backend\venv\Scripts\python scraper.py"
