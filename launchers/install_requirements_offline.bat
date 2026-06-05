@echo off
setlocal
cd /d "%~dp0.."

if exist wheelhouse (
  python -m pip install --no-index --find-links wheelhouse -r requirements.txt
  goto :eof
)

if exist offline_packages (
  python -m pip install --no-index --find-links offline_packages -r requirements.txt
  goto :eof
)

echo Khong tim thay thu muc wheelhouse hoac offline_packages.
echo Hay chuan bi cac file .whl offline truoc khi cai tren may chu khong co internet.
exit /b 1
