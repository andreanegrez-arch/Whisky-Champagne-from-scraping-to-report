@echo off
rem Esporta whisky e champagne in CSV per Power BI (lotti + lotti ritirati).
rem Prima chiudi i CSV se sono aperti in Excel.
set OPENBLAS_NUM_THREADS=1
cd /d "%~dp0.."
python export_powerbi\export_powerbi.py %*
echo.
pause
