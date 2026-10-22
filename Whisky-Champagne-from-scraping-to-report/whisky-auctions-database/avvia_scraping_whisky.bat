@echo off
rem Avvia una sessione di scraping whisky sul backend (porta 8080) gia acceso.
cd /d "%~dp0"
for /l %%i in (1,1,3) do (
  curl -s -o nul --max-time 20 http://127.0.0.1:8080/api/scraper/status && goto avvia
  timeout /t 2 /nobreak >nul
)
echo Il backend whisky (porta 8080) non risponde: avvialo con run_all.bat e riprova.
pause
exit /b 1
:avvia
echo Backend whisky attivo. Avvio la sessione di scraping...
curl -s -X POST http://127.0.0.1:8080/api/scraper/start
echo.
echo Fatto. Questa finestra si chiude tra 10 secondi.
timeout /t 10 >nul
