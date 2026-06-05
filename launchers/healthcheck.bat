@echo off
setlocal
cd /d "%~dp0.."
for /f "usebackq eol=# tokens=1,* delims==" %%A in ("package_config\app.env") do (
  if not "%%~A"=="" set "%%~A=%%~B"
)
if not defined VCOMS_DB_PATH set VCOMS_DB_PATH=runtime_data\smartvcoms\vcoms.db
if not defined VCOMS_STATUS_PATH set VCOMS_STATUS_PATH=runtime_data\smartvcoms\status\vcoms_sync_status.json
python backend\modules\smartvcoms\health\vcoms_healthcheck.py --db %VCOMS_DB_PATH% --status %VCOMS_STATUS_PATH%
endlocal
