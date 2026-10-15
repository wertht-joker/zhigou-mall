@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ==========================================================
echo   企业知识库 · 一键启动
echo ==========================================================

REM ---------- 1. 启动依赖容器（PostgreSQL / Redis / Milvus）----------
echo [1/4] 启动依赖容器...
docker compose up -d postgres redis milvus
if errorlevel 1 (
    echo [失败] Docker 启动失败，请先确认 Docker Desktop 正在运行。
    pause
    exit /b 1
)

REM ---------- 2. 定位 Python 解释器（绝对路径，避免工作目录影响）----------
set "PY=%CD%\backend\venv\Scripts\python.exe"
if not exist "%PY%" set "PY=%CD%\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
echo [2/4] Python 解释器: %PY%

REM ---------- 3. 准备 .env ----------
if not exist "backend\.env" (
    copy "backend\.env.example" "backend\.env" >nul
    echo [提示] 未找到 backend\.env，已从 .env.example 复制，请填入 DEEPSEEK_API_KEY 后重启。
)

REM ---------- 4. 各开一个窗口启动后端与前端 ----------
echo [3/4] 启动后端 http://localhost:8000 ...
pushd "%~dp0backend"
start "kb-backend" cmd /k "%PY% -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
popd

echo [4/4] 启动前端 http://localhost:5173 ...
pushd "%~dp0frontend"
start "kb-frontend" cmd /k "npm run dev"
popd

echo.
echo 已启动。后端首次启动约需 20-30 秒（自动跑迁移 + 载体模型加载）。
echo   [- 就绪探针] http://localhost:8000/api/v1/health/ready
echo   [- 接口文档] http://localhost:8000/docs
echo   [- 前端页面] http://localhost:5173
echo   默认账号: admin / admin123（租户编码留空 = 默认租户）
echo.
pause
