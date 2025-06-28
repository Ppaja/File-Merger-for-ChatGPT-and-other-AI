@echo off
title Immersion Hub
echo Starte Immersion Hub...
:: Aktiviere die virtuelle Umgebung und starte das Hauptskript
call venv\Scripts\activate.bat
python extractor.py
echo.
echo Das Programm wurde beendet. Du kannst das Fenster jetzt schliessen.
exit