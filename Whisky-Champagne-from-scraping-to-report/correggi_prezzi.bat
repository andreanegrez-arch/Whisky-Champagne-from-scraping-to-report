@echo off
rem Corregge prezzi ed esiti gia' salvati nei database whisky e champagne.
rem PRIMA chiudi le finestre di backend e scheduler (whisky e champagne).
rem Fa un backup dei database. Con --prova scrive solo il report.
cd /d "%~dp0"
whisky-auctions-database\backend\venv\Scripts\python.exe correggi_prezzi.py %*
echo.
pause
