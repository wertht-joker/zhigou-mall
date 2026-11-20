@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ==========================================================
echo   智购商城 · 本地一键启动（无需 Docker）
echo ==========================================================

REM ---------- 1. 定位 Python 解释器（绝对路径，避免工作目录影响）----------
REM 优先用项目根目录 .venv（PyCharm/日常开发环境），其次 backend\venv
set "PY=%CD%\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=%CD%\backend\venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
echo [1/3] Python 解释器: %PY%

REM ---------- 2. 准备 .env ----------
if not exist "backend\.env" (
    copy "backend\.env.example" "backend\.env" >nul
    echo [提示] 未找到 backend\.env，已从 .env.example 复制，请填入 DEEPSEEK_API_KEY 后重启。
)

REM ---------- 3. 各开一个窗口启动后端与前端 ----------
echo [2/3] 启动后端 http://localhost:8000 ...
echo        业务库 SQLite + 本地向量库 backend\vector.db，无需启动 Docker
pushd "%~dp0backend"
start "zg-backend" cmd /k "set VECTOR_BACKEND=sqlite&& %PY% -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
popd

echo [3/3] 启动前端 http://localhost:5173 ...
pushd "%~dp0frontend"
start "zg-frontend" cmd /k "npm run dev"
popd

echo.
echo 已启动。后端首次启动约需 20-30 秒（自动跑迁移 + 写入演示数据 + 重建本地向量库）。
echo   [- 就绪探针] http://localhost:8000/api/v1/health/ready
echo   [- 接口文档] http://localhost:8000/docs
echo   [- 前端页面] http://localhost:5173
echo   演示账号: 顾客 demo/demo123  平台管理员 admin/admin123  商家 shop/shop123
echo.
pause
