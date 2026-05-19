#!/usr/bin/env bash
# Hetzner lab-agent 部署腳本
# 用法：在 lab-agent 上跑此 script，會：
#  1. clone/pull repo
#  2. 建立 .env（含密碼、API_KEY、PUBLIC_BASE_URL）
#  3. docker compose up -d
#  4. （選用）Tailscale Funnel 對外公開
#
# 假設 lab-agent 已有：docker、git、tailscale

set -e

REPO_URL="https://github.com/jacksungtw/shopee-reconcile.git"
DEPLOY_DIR="${HOME}/shopee-reconcile"
PORT=8787

# --- 1. 取得程式 ---
if [ -d "${DEPLOY_DIR}/.git" ]; then
  echo "[1/4] git pull..."
  cd "${DEPLOY_DIR}" && git pull
else
  echo "[1/4] git clone..."
  git clone "${REPO_URL}" "${DEPLOY_DIR}"
  cd "${DEPLOY_DIR}"
fi

# --- 2. 環境變數 ---
if [ ! -f .env ]; then
  echo "[2/4] 建立 .env（首次部署）"
  cat > .env <<EOF
# Shopee Excel 解密密碼
SHOPEE_PASSWORD=your_password_here

# Chatbot UI 呼叫 API 用的金鑰（自行生成隨機字串，建議 32 字以上）
API_KEY=$(openssl rand -hex 24)

# 對外網址（由 Tailscale Funnel / Cloudflare Tunnel / nginx 提供）
PUBLIC_BASE_URL=https://reconcile.lab-agent.ts.net
EOF
  echo "  → 已生成 .env，請依需要修改 PUBLIC_BASE_URL"
else
  echo "[2/4] .env 已存在，跳過"
fi

# --- 3. 啟動容器 ---
echo "[3/4] docker compose up -d --build"
docker compose up -d --build

# --- 4. 健康檢查 ---
echo "[4/4] 等待服務啟動..."
sleep 6
if curl -fs "http://localhost:${PORT}/" > /dev/null; then
  echo ""
  echo "===== 部署成功 ====="
  curl -s "http://localhost:${PORT}/"
  echo ""
  echo ""
  echo "本機網址：http://localhost:${PORT}"
  echo "API 文件：http://localhost:${PORT}/docs"
  echo "上傳介面：http://localhost:${PORT}/upload-ui"
  echo ""
  echo "API_KEY（給 Chatbot UI 設 Tool 用）："
  grep API_KEY .env
else
  echo "[ERROR] 健康檢查失敗，請查 logs："
  docker compose logs --tail=30
  exit 1
fi

# --- 選用：Tailscale Funnel 對外 ---
if command -v tailscale &>/dev/null; then
  echo ""
  read -p "是否啟用 Tailscale Funnel 對外公開？(y/N) " yn
  if [ "$yn" = "y" ] || [ "$yn" = "Y" ]; then
    sudo tailscale funnel --bg --https=443 "http://localhost:${PORT}"
    echo "  → 已啟用，公開網址："
    tailscale funnel status
  fi
fi
