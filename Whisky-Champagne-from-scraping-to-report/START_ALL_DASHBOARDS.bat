@echo off
rem Meno memoria per ogni programma Python: numpy/pandas usano 1 thread di calcolo
rem invece di uno per core (prima la RAM finiva: "OpenBLAS error: Memory allocation").
set OPENBLAS_NUM_THREADS=1
set OMP_NUM_THREADS=1
set MKL_NUM_THREADS=1
setlocal enabledelayedexpansion

echo --- STARTING CATAWIKI ELITE DASHBOARDS (WHISKY AND CHAMPAGNE) ---
echo.

:: Sblocca i file per prevenire blocchi di Smart App Control
echo [!] Sblocco file di sistema per Windows Smart App Control...
powershell -Command "Get-ChildItem -Path '%~dp0.' -Recurse | Unblock-File"

:: --- WHISKY PROJECT ---
echo [1/2] Avvio Progetto WHISKY (Port 8080/3001)...
cd /d "%~dp0whisky-auctions-database"
start "Whisky - Startup" cmd /c "run_all.bat"

:: Attesa per evitare sovrapposizioni eccessive
timeout /t 5 /nobreak

:: --- CHAMPAGNE PROJECT ---
echo [2/2] Avvio Progetto CHAMPAGNE (Port 8001/3000)...
cd /d "%~dp0champagne-auctions-database"
start "Champagne - Startup" cmd /c "run_all.bat"

echo.
echo === Tutte le procedure sono state avviate correttamente! ===
echo Controlla le finestre nere aperte sul desktop per i log dei server.
echo.
pause
