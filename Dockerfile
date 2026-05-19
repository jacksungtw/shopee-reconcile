FROM python:3.12-slim

WORKDIR /app

# 安裝 LibreOffice 用不到，輕量 image
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shopee_reconcile.py api_server.py ./

# 資料持久化目錄
RUN mkdir -p /data/uploads /data/jobs
ENV STORAGE_ROOT=/data
ENV PORT=8787
ENV PUBLIC_BASE_URL=""

EXPOSE 8787

CMD ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "8787"]
