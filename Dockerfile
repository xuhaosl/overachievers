# ---------- 阶段一：构建前端 ----------
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------- 阶段二：Python 运行时 ----------
FROM python:3.12-slim
WORKDIR /app

# 构建号（git 提交号），由 CI 注入，用于应用内「检查更新」
ARG APP_VERSION=dev
ENV APP_VERSION=$APP_VERSION

ENV TZ=Asia/Shanghai \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/app/data

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY --from=frontend-build /app/frontend/dist/ ./backend/static/

RUN mkdir -p /app/data
VOLUME /app/data
EXPOSE 8100

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8100"]
