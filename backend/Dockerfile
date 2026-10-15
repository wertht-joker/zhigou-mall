# 后端镜像：FastAPI + 本地 BGE 模型（CPU 推理）
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/.cache/huggingface

WORKDIR /app

# 先装依赖（利用层缓存），curl 供健康检查使用
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

# 上传目录（compose 里会挂卷覆盖）
RUN mkdir -p /app/uploads

EXPOSE 8000

# 就绪探针：/health/ready 会检查 database / milvus / redis 等依赖
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/v1/health/ready || exit 1

# 启动前先迁移库结构（幂等），再拉起 uvicorn
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
