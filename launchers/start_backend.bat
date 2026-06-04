@echo off
setlocal
cd /d "%~dp0.."
for /f "usebackq eol=# tokens=1,* delims==" %%A in ("package_config\app.env") do (
  if not "%%~A"=="" set "%%~A=%%~B"
)
if not defined PORTAL_SQLITE_PATH set PORTAL_SQLITE_PATH=runtime_data\portal\portal.db
if not defined VCOMS_DB_PATH set VCOMS_DB_PATH=runtime_data\smartvcoms\vcoms.db
if not defined VCOMS_STATUS_PATH set VCOMS_STATUS_PATH=runtime_data\smartvcoms\status\vcoms_sync_status.json
if not defined PORTAL_AUTH_MODE set PORTAL_AUTH_MODE=AD
py -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
endlocal
