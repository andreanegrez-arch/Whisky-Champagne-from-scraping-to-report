@echo off
rem Nomi estesi degli imbottigliatori nel backend e nel database whisky.
rem Se il backend sta facendo scraping, aspetta che finisca prima di applicare.
title Aggiornamento nomi bottlers
cd /d "%~dp0"
backend\venv\Scripts\python applica_nomi_bottlers.py
echo.
echo Questa finestra si chiude tra 30 secondi.
timeout /t 30 >nul
