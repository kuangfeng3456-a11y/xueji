@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

set PORT=8000
if not "%~1"=="" set PORT=%~1

echo [1/4] 检查题库服务 tikuAdapter...
set "TIKU_DIR=%~dp0external\tikuAdapter"
set "TIKU_EXE=%TIKU_DIR%\tikuAdapter.exe"
netstat -ano | findstr /R /C:":8060 .*LISTENING" >nul 2>&1
if not errorlevel 1 (
  echo 题库已在 8060 端口运行
) else (
  if not exist "%TIKU_EXE%" (
    echo 未找到 tikuAdapter.exe，出题将回退到模型或内置题库。
  ) else (
    echo 正在启动题库服务...
    start "tikuAdapter" /MIN /D "%TIKU_DIR%" tikuAdapter.exe
    powershell -NoProfile -Command "for ($i=0; $i -lt 20; $i++) { Start-Sleep -Milliseconds 500; try { $r = Invoke-WebRequest -Uri http://127.0.0.1:8060 -UseBasicParsing -TimeoutSec 1; if ($r.StatusCode -eq 200) { exit 0 } } catch {} }; exit 1"
    if errorlevel 1 (
      echo 题库启动超时，请稍后打开 http://127.0.0.1:8060 检查
    ) else (
      echo 题库已启动：http://127.0.0.1:8060
    )
  )
)

if not exist "frontend\dist\index.html" (
  echo [2/4] 构建前端...
  pushd frontend
  call npm install --no-audit --no-fund
  if errorlevel 1 goto :error
  call npm run build
  if errorlevel 1 goto :error
  popd
) else (
  echo [2/4] 前端已构建，跳过
)

echo [3/4] 安装后端依赖...
python -m pip install -r backend\requirements.txt -q
if errorlevel 1 goto :error

echo [4/4] 初始化演示数据并启动...
cd backend
python -m app.seed
python run.py --port %PORT%
goto :eof

:error
echo 启动失败，请检查上方错误信息。
exit /b 1
