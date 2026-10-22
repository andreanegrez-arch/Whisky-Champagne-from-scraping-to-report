@echo off
rem Imbottigliatori: aggiunge la colonna e la compila per tutti i lotti whisky (copia di sicurezza automatica).
cd /d "%~dp0"
backend\venv\Scripts\python backend\aggiorna_imbottigliatori.py --applica
echo.
pause
