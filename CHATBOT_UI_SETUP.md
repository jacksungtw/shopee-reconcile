# 把對帳工具接上 Chatbot UI

讓 Chatbot UI 的 Assistant 直接呼叫對帳工具，使用者用對話完成對帳。

---

## 架構

```
[Chatbot UI / Railway]
       ↓ HTTP
[FastAPI 對帳服務]  ← 本 repo 的 api_server.py
       ↓
[shopee_reconcile.py]  ← 對帳邏輯
```

---

## 一、啟動 API 服務

### 本機測試

```bash
pip install fastapi uvicorn python-multipart pandas openpyxl msoffcrypto-tool
python api_server.py
# 開 http://localhost:8787/docs 看 Swagger
```

### 部署到 Hetzner / Railway / 任何雲

```bash
# 環境變數
export SHOPEE_PASSWORD=your_password   # Excel 解密密碼
export PUBLIC_BASE_URL=https://your-domain.com   # 對外網址
export API_KEY=your_secret_key         # 可選，保護 API
export STORAGE_DIR=/data/recon         # 檔案儲存路徑

uvicorn api_server:app --host 0.0.0.0 --port 8787
```

### Docker（推薦）

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install fastapi uvicorn python-multipart pandas openpyxl msoffcrypto-tool
ENV PYTHONUTF8=1
EXPOSE 8787
CMD ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "8787"]
```

部署後請確認可以打到：
- `https://your-domain.com/` → 回 JSON
- `https://your-domain.com/openapi.json` → OpenAPI schema
- `https://your-domain.com/docs` → Swagger UI

---

## 二、Chatbot UI 註冊 Tool

### 步驟 1：開 Chatbot UI 的 Tools 頁面
左側選單 → **Tools** → **New Tool**

### 步驟 2：填寫 Tool 設定

| 欄位 | 內容 |
|---|---|
| **Name** | `Shopee 對帳` |
| **Description** | `Shopee 月結對帳：上傳 Excel + 紙本 CSV，回傳對帳結果與下載連結` |
| **URL** | `https://your-domain.com/openapi.json` |
| **Custom Headers** | `{"X-API-Key": "your_secret_key"}` （如有設 API_KEY） |
| **Schema** | 貼上 `/openapi.json` 內容（或讓 UI 自動 fetch） |

### 步驟 3：設定 Assistant

到 **Assistants** → 新建一個專屬對帳的 Assistant（建議命名 `無雲 · Shopee 對帳`）：

**System Prompt 範本：**
```
你是 Shopee 對帳助理。當使用者要對帳時，請：
1. 引導使用者用 /upload 端點上傳 Excel 與紙本 CSV
2. 取得 file_id 後，呼叫 /reconcile 端點
3. 把回傳的 summary_markdown 直接顯示給使用者
4. 提醒下載連結

若使用者沒提供紙本 CSV，paper_csv_id 留空即可（仍可跑只是不對紙本）。
```

**Tools**：勾選剛剛建立的「Shopee 對帳」

---

## 三、實際對話範例

```
[師父]
   幫我對 3 月的帳

[Assistant]
   好的，請先上傳 Shopee 訂單 Excel（拖到對話框即可）。
   如果有紙本日結 CSV 也一併上傳。

[師父]
   [拖上 Order.completed.20260301_20260331.xlsx]
   [拖上 紙本對帳_115年3月.csv]

[Assistant 自動執行]
   1. 呼叫 POST /upload 兩次，取得兩個 file_id
   2. 呼叫 POST /reconcile，傳 file_ids + month=3
   3. 拿到結果 markdown

[Assistant 回覆]
   ## 對帳結果（範例數字）
   - 訂單筆數：1,234
   - Excel 合計：1,234,567 元
   - 紙本合計：1,230,000 元
   - 差額：+4,567 元（吻合度 99.5%）
   - Typo 修正：3 筆
   - 差異日：差額 > 3000 的日子會列出

   ### 下載報表
   - [對帳表_115年3月.xlsx](https://your-domain.com/download/xxx/對帳表.xlsx)
   - [工程師獎金_115年3月.xlsx](...)
```

---

## 四、限制與注意

### Chatbot UI 對檔案的處理
Chatbot UI 的 file upload 預設是給 RAG 用的（向量化），**不會自動轉成 multipart 傳給 Tool**。
要實現「拖檔即對帳」有兩條路：

**A. 訓練使用者先去 Web UI 上傳**
   - 給師父一個簡單 web 介面（例如 `/upload-ui`）
   - 拿到 file_id 後貼到 chatbot 對話：「對帳 file_id=abc123,def456 month=3」
   - Chatbot 收到指令就呼叫 `/reconcile`

**B. 修改 Chatbot UI 後端**
   - Fork 一份 chatbot UI 加 file→multipart 邏輯
   - 較複雜，不建議

**推薦：A 方案。** 弟子可以另外寫一個 `/upload-ui` 簡單 HTML 上傳頁。

### 安全
- 強烈建議設 `API_KEY`
- `PUBLIC_BASE_URL` 用 HTTPS（Cloudflare Tunnel / Caddy / Nginx）
- `STORAGE_DIR` 定期清理（避免堆積）

---

## 五、Quick Test

```bash
# 1. 啟動 API
python api_server.py

# 2. 上傳 Excel
curl -F "file=@Order.completed.20260301_20260331.xlsx" \
     http://localhost:8787/upload
# → {"file_id":"abc123","filename":"...","size_bytes":12345}

# 3. 上傳紙本 CSV
curl -F "file=@紙本對帳_115年3月.csv" \
     http://localhost:8787/upload
# → {"file_id":"def456","filename":"..."}

# 4. 對帳
curl -X POST http://localhost:8787/reconcile \
     -H "Content-Type: application/json" \
     -d '{"file_ids":["abc123"],"month":3,"paper_csv_id":"def456"}'
# → 完整對帳結果 JSON
```
