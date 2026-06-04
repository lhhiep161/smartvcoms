@echo off
setlocal
cd /d "%~dp0.."
for /f "usebackq eol=# tokens=1,* delims==" %%A in ("package_config\app.env") do (
  if not "%%~A"=="" set "%%~A=%%~B"
)
if not defined PORTAL_SQLITE_PATH set PORTAL_SQLITE_PATH=runtime_data\portal\portal.db
if not defined VCOMS_DB_PATH set VCOMS_DB_PATH=runtime_data\smartvcoms\vcoms.db
if not defined VCOMS_STATUS_PATH set VCOMS_STATUS_PATH=runtime_data\smartvcoms\status\vcoms_sync_status.json
if not defined VCOMS_OUTLOOK_FOLDER set VCOMS_OUTLOOK_FOLDER=VCOMS
if not defined VCOMS_WATCH_INTERVAL_SECONDS set VCOMS_WATCH_INTERVAL_SECONDS=15
if not defined PORTAL_AUTH_MODE set PORTAL_AUTH_MODE=AD

start "SmartVCOMS Backend" cmd /k py -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
start "SmartVCOMS Outlook Watcher" cmd /k py backend\modules\smartvcoms\runner\vcoms_today_full_runner.py --watch --interval %VCOMS_WATCH_INTERVAL_SECONDS% --reader-today-only --process-scope today --rebuild-case-state-v2 --db %VCOMS_DB_PATH%

echo Started backend and Outlook watcher.
echo Frontend is served from backend at: http://localhost:8000
echo Auth mode: %PORTAL_AUTH_MODE%
echo Watcher runs every %VCOMS_WATCH_INTERVAL_SECONDS% seconds and only processes today's data.
endlocal
