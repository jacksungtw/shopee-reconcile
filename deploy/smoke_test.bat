@echo off
chcp 65001 >nul
setlocal

set "BASE=%~1"
if "%BASE%"=="" set "BASE=http://localhost:8787"

echo ====== Shopee 對帳 API 冒煙測試 ======
echo 目標: %BASE%
echo.

echo [1/3] 健康檢查
curl -fsS "%BASE%/" || (echo X 失敗 & exit /b 1)
echo.
echo.

echo [2/3] /upload-ui 網頁
curl -fsS -o nul -w "HTTP %%{http_code}  Size: %%{size_download}\n" "%BASE%/upload-ui"
echo.

echo [3/3] 完整流程 (跑 Python 版測試)
cd /d "%~dp0\.."
python deploy\smoke_test.py "%BASE%"
endlocal
