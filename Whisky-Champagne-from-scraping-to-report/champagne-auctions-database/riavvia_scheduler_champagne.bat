@echo off
rem Meno memoria per ogni programma Python: numpy/pandas usano 1 thread di calcolo
rem invece di uno per core (prima la RAM finiva: "OpenBLAS error: Memory allocation").
set OPENBLAS_NUM_THREADS=1
set OMP_NUM_THREADS=1
set MKL_NUM_THREADS=1
rem Avvia lo scheduler champagne (sessioni 03:00 e 17:00) con il codice aggiornato.
cd /d "%~dp0"
start "Catawiki Scheduler Champagne" cmd /k "cd scraper && ..\.venv\Scripts\python scraper.py"
