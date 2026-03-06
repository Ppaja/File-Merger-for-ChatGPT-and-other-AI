@echo off
title File Merger
echo Starte File Merger...
:: Aktiviere die virtuelle Umgebung und starte das Hauptskript
call venv\Scripts\activate.bat
start /b pythonw extractor.py
exit