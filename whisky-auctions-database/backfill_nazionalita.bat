@echo off
rem Meno memoria per ogni programma Python: numpy/pandas usano 1 thread di calcolo
rem invece di uno per core (prima la RAM finiva: "OpenBLAS error: Memory allocation").
set OPENBLAS_NUM_THREADS=1
set OMP_NUM_THREADS=1
set MKL_NUM_THREADS=1
cd /d "%~dp0backend"
echo Recupero nazionalita dei vincitori (whisky). Si puo chiudere in qualsiasi momento: riprende da dove era rimasto.
venv\Scripts\python backfill_nazionalita.py %*
pause
