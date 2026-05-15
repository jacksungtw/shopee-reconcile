# Shopee 月結對帳工具

把 Shopee 下載的「Order.completed」Excel 拖到 `對帳工具.bat` 上，自動產出三份報表：

1. **逐日對帳表** — Excel vs 紙本日結逐日比對，標出差異大的日子
2. **差異日明細** — 差額 > 3000 的日子，逐筆訂單明細
3. **工程師獎金統計** — 從備註解析支數/金額，依規則算當月獎金

---

## 功能

- 自動解密 Shopee 加密 Excel（密碼放 `.env`）
- 月份從檔名自動偵測（`20260301_20260331` → 3月）
- 多檔合併（2 月 + 3 月一起拖，跨月訂單也算得到）
- Typo 容錯：`1153.X` / `113.3.X+ZM` 自動修正為 `115.3.X`
- 備註格式解析：
  - A 類（支數比例）：`E=1,S=2,B=2`
  - B 類（固定金額）：`E=1*600,S=1*600`
  - 三段式：`115.3.5 ZM123456|E=1*100,S=2*200|5`
  - 容錯：`S600` → `S=1*600`、`S1*130` → `S=1*130`
- 紙本日結 CSV 對照（找不到也能跑，只少對帳那段）

---

## 安裝

需要 Python 3.8+。

```bash
pip install pandas openpyxl msoffcrypto-tool
```

複製 `.env.example` 為 `.env`，填入 Excel 解密密碼：

```
SHOPEE_PASSWORD=your_password_here
```

---

## 使用

### 最簡單：拖檔

把 Shopee 下載的 Excel 拖到 `對帳工具.bat` 上即可。

### 命令列

```bash
python shopee_reconcile.py Order.completed.20260301_20260331.xlsx
python shopee_reconcile.py 2月.xlsx 3月.xlsx --month=3 --year=115
```

選項：

- `--month=N` 指定月份（不指定就從檔名抓）
- `--year=N` 民國年（預設 115）
- `--out=路徑` 輸出目錄（預設與輸入同目錄）

### 紙本對帳（選用）

在 Excel 同目錄放一個 CSV，命名 `紙本對帳_115年X月.csv`：

```csv
日,金額
2,177031
3,69435
4,113716
```

腳本會自動讀進來逐日比對。

---

## 一鍵驗證環境

雙擊 `一鍵測試.bat`：

1. 自動產生 33 筆假訂單 + 21 天假紙本
2. 跑完整對帳流程
3. 應該看到「**吻合度 100.00%**」

看到 100% → 環境正常。

---

## 檔案結構

```
shopee-reconcile/
├── shopee_reconcile.py       # 主程式
├── gen_test_data.py          # 假資料產生器
├── 對帳工具.bat               # 拖檔入口
├── 一鍵測試.bat                # 環境驗證
├── 使用說明.txt               # 詳細操作手冊
├── .env.example              # 密碼範本
├── .gitignore
└── README.md
```

---

## 獎金計算規則

- **銷售獎金** = 訂單金額 × 1%
- **維修獎金** = 支數 × 80 元
- **總獎金** = 銷售獎金 + 維修獎金

同一訂單只取第一筆可解析的備註；退貨訂單（退貨數量 > 0）自動排除。

---

## 安全提醒

- `.env` 已在 `.gitignore`，不會進版控
- 真實 `Order.completed.*.xlsx` 與紙本 CSV 也已被 ignore
- 公開分享前請確認沒有營業數據外洩

---

## 授權

MIT
