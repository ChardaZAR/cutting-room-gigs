@echo off
cd /d "%~dp0"
echo Starting Cutting Room Gigs Live Board on http://localhost:8080 ...
start "" "http://localhost:8080"
python server.py
