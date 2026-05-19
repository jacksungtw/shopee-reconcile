#!/usr/bin/env bash
# 部署後端對端冒煙測試
# 用法：
#   ./smoke_test.sh                            # 測 localhost:8787
#   ./smoke_test.sh https://your.url.com KEY   # 測遠端 + 帶 API key

set -e

BASE="${1:-http://localhost:8787}"
API_KEY="${2:-}"

echo "===== Shopee 對帳 API 冒煙測試 ====="
echo "目標: ${BASE}"
echo ""

# ----- 1. 健康檢查 -----
echo "[1/5] 健康檢查 GET /"
curl -fsS "${BASE}/" | python3 -m json.tool
echo ""

# ----- 2. 上傳網頁 -----
echo "[2/5] 上傳網頁 GET /upload-ui"
status=$(curl -fsS -o /tmp/_ui.html -w "%{http_code}" "${BASE}/upload-ui")
if [ "$status" = "200" ] && grep -q "Shopee 對帳" /tmp/_ui.html; then
  echo "  ✓ HTML 載入正常 ($(wc -c < /tmp/_ui.html) bytes)"
else
  echo "  ✗ 失敗: HTTP ${status}"
  exit 1
fi
echo ""

# ----- 3. 產假資料 -----
echo "[3/5] 產生假資料"
TMPDIR=$(mktemp -d)
cd "$(dirname "$0")/.."
python3 gen_test_data.py > /dev/null
cp _test_data/Order.completed.20260301_20260331.xlsx "${TMPDIR}/test.xlsx"
cp _test_data/紙本對帳_115年3月.csv "${TMPDIR}/paper.csv"
echo "  ✓ ${TMPDIR}/test.xlsx + paper.csv"
echo ""

# ----- 4. 上傳檔案 -----
echo "[4/5] 上傳 Excel + CSV"
KEY_PARAM=""
[ -n "$API_KEY" ] && KEY_PARAM="-F api_key=${API_KEY}"

resp1=$(curl -fsS -X POST "${BASE}/upload" \
  -F "file=@${TMPDIR}/test.xlsx" ${KEY_PARAM})
EXCEL_ID=$(echo "$resp1" | python3 -c "import sys,json;print(json.load(sys.stdin)['file_id'])")
echo "  ✓ Excel file_id: ${EXCEL_ID}"

resp2=$(curl -fsS -X POST "${BASE}/upload" \
  -F "file=@${TMPDIR}/paper.csv" ${KEY_PARAM})
CSV_ID=$(echo "$resp2" | python3 -c "import sys,json;print(json.load(sys.stdin)['file_id'])")
echo "  ✓ CSV file_id:   ${CSV_ID}"
echo ""

# ----- 5. 對帳 -----
echo "[5/5] 呼叫 /reconcile"
PAYLOAD=$(cat <<EOF
{
  "file_ids": ["${EXCEL_ID}"],
  "paper_csv_id": "${CSV_ID}",
  "month": 3,
  "year": 115${API_KEY:+,"api_key":"${API_KEY}"}
}
EOF
)
result=$(curl -fsS -X POST "${BASE}/reconcile" \
  -H "Content-Type: application/json" \
  -d "${PAYLOAD}")

echo "$result" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f'  訂單筆數: {d[\"order_count\"]}')
print(f'  Excel 合計: {d[\"excel_total\"]:,.0f}')
print(f'  紙本合計:   {d[\"paper_total\"]:,.0f}')
print(f'  差額:       {d[\"diff\"]:+,.0f}')
print(f'  吻合度:     {d[\"match_ratio_percent\"]:.2f}%')
print(f'  Typo:       {d[\"typo_count\"]} 筆')
print()
print('  下載連結:')
for k, v in d['downloads'].items():
    print(f'    {k}: {v}')
"

# 清理
rm -rf "${TMPDIR}"
echo ""
echo "===== 全部測試通過 ====="
