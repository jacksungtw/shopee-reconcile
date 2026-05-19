# -*- coding: utf-8 -*-
"""
Shopee 對帳 FastAPI 服務 — 給 Chatbot UI 當 Tool 用

啟動：
  pip install fastapi uvicorn python-multipart
  uvicorn api_server:app --host 0.0.0.0 --port 8787

文件：
  http://localhost:8787/docs        Swagger UI
  http://localhost:8787/openapi.json OpenAPI schema（給 Chatbot UI 用）
"""
import os
import sys
import uuid
import tempfile
import shutil
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Header, Request
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# 引入主對帳邏輯
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shopee_reconcile import reconcile, load_paper_data

# ===== 設定 =====
STORAGE_DIR = Path(os.environ.get("STORAGE_DIR", tempfile.gettempdir())) / "shopee_reconcile_api"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8787")
API_KEY = os.environ.get("API_KEY", "").strip()  # 可選 API Key 保護

app = FastAPI(
    title="Shopee 對帳工具 API",
    description="Shopee 月結對帳與工程師獎金統計。給 Chatbot UI / Claude / 任意 LLM 當 Tool 呼叫。",
    version="1.0.0",
    servers=[{"url": PUBLIC_BASE_URL, "description": "Default"}],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===== 共用 =====
def _check_key(*candidates):
    """檢查 API key（接受多種來源：header / query / body）"""
    if not API_KEY:
        return  # 未設定 API_KEY 表示不啟用驗證
    for c in candidates:
        if c and c == API_KEY:
            return
    raise HTTPException(status_code=401, detail="Invalid or missing api_key")


def _save_uploads(files: List[UploadFile], session_dir: Path) -> List[Path]:
    saved = []
    for f in files:
        target = session_dir / f.filename
        with open(target, "wb") as out:
            shutil.copyfileobj(f.file, out)
        saved.append(target)
    return saved


# ===== Models =====
class UploadResp(BaseModel):
    file_id: str = Field(..., description="檔案 ID，後續對帳請帶這個 ID")
    filename: str
    size_bytes: int


class ReconcileReq(BaseModel):
    file_ids: List[str] = Field(..., description="先用 /upload 取得的檔案 ID 清單")
    month: Optional[int] = Field(None, description="目標月份 1-12（不填則從檔名偵測）")
    year: int = Field(115, description="民國年（預設 115）")
    paper_csv_id: Optional[str] = Field(None, description="紙本對帳 CSV 的 file_id（可選）")
    api_key: Optional[str] = None


class DailyRow(BaseModel):
    day: int
    excel_count: int
    excel_amount: float
    paper_amount: float
    diff: float
    status: str


class ReconcileResp(BaseModel):
    target_month: str
    order_count: int
    excel_total: float
    paper_total: float
    diff: float
    match_ratio_percent: float
    typo_count: int
    big_diff_days: List[int]
    daily: List[DailyRow]
    downloads: dict = Field(..., description="輸出檔案的下載 URL")
    summary_markdown: str = Field(..., description="可直接貼到 chatbot 的文字摘要")


# ===== Endpoints =====
@app.get("/", summary="健康檢查")
def root():
    return {"service": "shopee-reconcile-api", "version": "1.0.0",
            "docs": f"{PUBLIC_BASE_URL}/docs",
            "upload_ui": f"{PUBLIC_BASE_URL}/upload-ui"}


UPLOAD_UI_HTML = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Shopee 對帳 — 檔案上傳</title>
<style>
:root { --c1:#1F4E78; --c2:#F4B084; --c3:#FFE699; --bg:#f5f7fa; }
*{box-sizing:border-box}
body{font-family:"Microsoft JhengHei","Segoe UI",sans-serif;background:var(--bg);
     margin:0;padding:20px;color:#222}
.wrap{max-width:780px;margin:0 auto}
h1{color:var(--c1);font-size:22px;margin:0 0 6px}
.sub{color:#666;font-size:13px;margin-bottom:18px}
.card{background:#fff;border-radius:10px;padding:18px;margin-bottom:14px;
      box-shadow:0 2px 6px rgba(0,0,0,.06)}
.drop{border:2px dashed #aac;border-radius:10px;padding:38px 16px;text-align:center;
      background:#fafbfd;cursor:pointer;transition:.2s}
.drop:hover,.drop.over{background:#eef3fa;border-color:var(--c1)}
.drop p{margin:0;color:#557}
input[type=file]{display:none}
.kv{display:grid;grid-template-columns:130px 1fr auto;gap:6px 12px;
    align-items:center;padding:10px;border-bottom:1px solid #eee;font-size:14px}
.kv:last-child{border:none}
.kv .lbl{color:#778}
.kv .val{font-family:Consolas,monospace;background:#f4f6fa;padding:4px 8px;
         border-radius:4px;word-break:break-all}
.btn{background:var(--c1);color:#fff;border:none;padding:8px 16px;border-radius:6px;
     cursor:pointer;font-size:13px}
.btn:hover{opacity:.9}
.btn.sm{padding:4px 10px;font-size:12px}
.btn.gh{background:#888}
.snip{background:#1e2733;color:#cfe;padding:12px 14px;border-radius:6px;
      font-family:Consolas,monospace;font-size:13px;white-space:pre-wrap;
      word-break:break-all;line-height:1.55}
.snip .k{color:#fc6}
.note{font-size:12px;color:#789;margin-top:8px}
.lbl-tag{display:inline-block;background:var(--c3);padding:2px 8px;
         border-radius:3px;font-size:11px;color:#664}
.lbl-tag.csv{background:#cde}
.tip{background:#fff8e6;border-left:3px solid var(--c2);padding:10px 14px;
     font-size:13px;color:#665}
.empty{color:#aab;text-align:center;padding:14px;font-size:13px}
</style>
</head>
<body>
<div class="wrap">
  <h1>Shopee 對帳 · 檔案上傳</h1>
  <div class="sub">拖入 Excel + 紙本 CSV → 取得 file_id → 貼到 Chatbot UI 對話框</div>

  <div class="card">
    <div id="drop" class="drop" onclick="document.getElementById('fi').click()">
      <p>📎 把 Excel (.xlsx) 與紙本 CSV 拖到這裡</p>
      <p style="font-size:12px;color:#99a;margin-top:6px">或點此選檔案</p>
    </div>
    <input type="file" id="fi" multiple accept=".xlsx,.xls,.csv">
  </div>

  <div class="card">
    <h3 style="margin:0 0 10px;font-size:15px;color:var(--c1)">已上傳檔案</h3>
    <div id="list" class="empty">尚未上傳檔案</div>
  </div>

  <div class="card" id="snipCard" style="display:none">
    <h3 style="margin:0 0 8px;font-size:15px;color:var(--c1)">複製這段到 Chatbot UI 對話框</h3>
    <div class="tip">直接告訴 Assistant：「請用以下 file_id 對帳」並貼上下方文字</div>
    <div style="margin-top:10px">
      <div class="snip" id="snip"></div>
      <div style="margin-top:8px;display:flex;gap:8px">
        <button class="btn" onclick="copySnip()">📋 複製</button>
        <button class="btn gh" onclick="clearAll()">🗑️ 清空重來</button>
      </div>
    </div>
  </div>
</div>

<script>
const drop = document.getElementById('drop');
const fi = document.getElementById('fi');
const list = document.getElementById('list');
const snipCard = document.getElementById('snipCard');
const snipEl = document.getElementById('snip');
let uploaded = [];  // [{file_id, filename, type}]

['dragenter','dragover'].forEach(e => drop.addEventListener(e, ev => {
  ev.preventDefault(); drop.classList.add('over');
}));
['dragleave','drop'].forEach(e => drop.addEventListener(e, ev => {
  ev.preventDefault(); drop.classList.remove('over');
}));
drop.addEventListener('drop', ev => uploadFiles(ev.dataTransfer.files));
fi.addEventListener('change', () => uploadFiles(fi.files));

async function uploadFiles(files) {
  for (const f of files) {
    const fd = new FormData();
    fd.append('file', f);
    const res = await fetch('/upload', {method:'POST', body:fd});
    if (!res.ok) { alert('上傳失敗: ' + f.name); continue; }
    const data = await res.json();
    const isCSV = f.name.toLowerCase().endsWith('.csv');
    uploaded.push({file_id:data.file_id, filename:data.filename, type:isCSV?'csv':'excel'});
  }
  render();
}

function render() {
  if (uploaded.length === 0) {
    list.className = 'empty'; list.innerHTML = '尚未上傳檔案';
    snipCard.style.display = 'none'; return;
  }
  list.className = '';
  list.innerHTML = uploaded.map((u,i) => `
    <div class="kv">
      <span class="lbl">${u.type==='csv'?'<span class="lbl-tag csv">紙本</span>':'<span class="lbl-tag">Excel</span>'}</span>
      <span>${u.filename}<br><span class="val">${u.file_id}</span></span>
      <button class="btn sm gh" onclick="removeFile(${i})">×</button>
    </div>
  `).join('');

  const excels = uploaded.filter(u=>u.type==='excel');
  const csv = uploaded.find(u=>u.type==='csv');
  if (excels.length === 0) { snipCard.style.display = 'none'; return; }

  let txt = '請對帳：\\n';
  txt += `file_ids: [${excels.map(e=>'"'+e.file_id+'"').join(', ')}]\\n`;
  if (csv) txt += `paper_csv_id: "${csv.file_id}"\\n`;
  txt += `(月份從檔名自動偵測，民國年 115)`;
  snipEl.textContent = txt;
  snipCard.style.display = 'block';
}

function removeFile(i) { uploaded.splice(i,1); render(); }
function clearAll() { uploaded = []; render(); }
function copySnip() {
  navigator.clipboard.writeText(snipEl.textContent).then(()=>{
    const old = event.target.textContent;
    event.target.textContent = '✅ 已複製！';
    setTimeout(()=>event.target.textContent=old, 1500);
  });
}
</script>
</body>
</html>
"""


@app.get("/upload-ui", response_class=HTMLResponse, summary="上傳網頁（給人類用）")
def upload_ui():
    """簡單的 HTML 上傳介面，方便師父拖檔取得 file_id 後貼到 Chatbot UI。"""
    return UPLOAD_UI_HTML


@app.post("/upload", response_model=UploadResp, summary="上傳檔案（Excel 或 CSV）")
async def upload(file: UploadFile = File(..., description="Excel (.xlsx) 或紙本 CSV"),
                 api_key: Optional[str] = Form(None),
                 x_api_key: Optional[str] = Header(None)):
    """先上傳檔案，取得 file_id，再呼叫 /reconcile。"""
    _check_key(api_key, x_api_key)
    file_id = uuid.uuid4().hex[:12]
    session_dir = STORAGE_DIR / file_id
    session_dir.mkdir(exist_ok=True)
    target = session_dir / file.filename
    with open(target, "wb") as out:
        shutil.copyfileobj(file.file, out)
    return UploadResp(file_id=file_id, filename=file.filename,
                      size_bytes=target.stat().st_size)


@app.post("/reconcile", response_model=ReconcileResp, summary="對帳（用已上傳的 file_id）")
def do_reconcile(req: ReconcileReq, x_api_key: Optional[str] = Header(None)):
    """主對帳端點：給 file_ids + month，回傳對帳結果 JSON + 下載 URL。"""
    _check_key(req.api_key, x_api_key)

    # 解出 Excel 路徑
    excel_paths = []
    for fid in req.file_ids:
        d = STORAGE_DIR / fid
        if not d.exists():
            raise HTTPException(404, f"file_id 不存在：{fid}")
        for f in d.iterdir():
            if f.suffix.lower() in (".xlsx", ".xls"):
                excel_paths.append(str(f))
    if not excel_paths:
        raise HTTPException(400, "沒找到任何 Excel 檔（請先 /upload）")

    # 推測月份
    import re
    month = req.month
    if month is None:
        months = []
        for p in excel_paths:
            m = re.search(r"(\d{4})(\d{2})\d{2}", os.path.basename(p))
            if m:
                months.append(int(m.group(2)))
        month = max(months) if months else 3

    # 結果輸出目錄
    job_id = uuid.uuid4().hex[:12]
    out_dir = STORAGE_DIR / "_out" / job_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # 紙本資料
    paper = {}
    if req.paper_csv_id:
        d = STORAGE_DIR / req.paper_csv_id
        csv_files = [f for f in d.iterdir() if f.suffix.lower() == ".csv"]
        if csv_files:
            csv_target = out_dir / f"紙本對帳_{req.year}年{month}月.csv"
            shutil.copy(csv_files[0], csv_target)
            paper = load_paper_data(out_dir, req.year, month)

    # 跑對帳（呼叫主程式邏輯，但要捕捉結果，所以這裡用簡化版重新跑）
    result = _run_reconcile_capture(excel_paths, req.year, month, out_dir, paper)

    # 建構下載 URL
    downloads = {}
    for f in out_dir.iterdir():
        if f.suffix == ".xlsx":
            downloads[f.name] = f"{PUBLIC_BASE_URL}/download/{job_id}/{f.name}"

    # Markdown 摘要（給 chatbot 直接貼）
    md = _build_markdown(result, downloads)

    return ReconcileResp(
        target_month=f"{req.year}年{month}月",
        order_count=result["order_count"],
        excel_total=result["excel_total"],
        paper_total=result["paper_total"],
        diff=result["diff"],
        match_ratio_percent=result["match_ratio"],
        typo_count=result["typo_count"],
        big_diff_days=result["big_diff_days"],
        daily=[DailyRow(**r) for r in result["daily"]],
        downloads=downloads,
        summary_markdown=md,
    )


@app.get("/download/{job_id}/{filename}", summary="下載對帳結果檔")
def download(job_id: str, filename: str):
    path = STORAGE_DIR / "_out" / job_id / filename
    if not path.exists():
        raise HTTPException(404, "檔案不存在")
    return FileResponse(path, filename=filename)


# ===== 內部：跑對帳並捕捉結果 =====
def _run_reconcile_capture(excel_paths, year, month, out_dir, paper):
    import pandas as pd
    import re as re_
    from shopee_reconcile import (
        read_excel_auto, parse_invoice_day, detect_typo, compute_bonus,
        style_workbook, safe_path,
        COL_ORDER_ID, COL_STATUS, COL_BUYER_PAID, COL_NOTE, COL_RETURN_QTY,
    )

    dfs = []
    for f in excel_paths:
        d = read_excel_auto(f)
        d["_source_file"] = os.path.basename(f)
        dfs.append(d)
    df = pd.concat(dfs, ignore_index=True)
    df[COL_BUYER_PAID] = pd.to_numeric(df[COL_BUYER_PAID], errors="coerce").fillna(0)
    if COL_RETURN_QTY in df.columns:
        df[COL_RETURN_QTY] = pd.to_numeric(df[COL_RETURN_QTY], errors="coerce").fillna(0)

    done = df[df[COL_STATUS].astype(str).str.startswith("已完成")].copy()
    done = done.drop_duplicates(subset=[COL_ORDER_ID], keep="first")
    done["_invoice_day"] = done[COL_NOTE].apply(lambda v: parse_invoice_day(v, year, month))
    target = done[done["_invoice_day"].notna()].copy()
    target["_invoice_day"] = target["_invoice_day"].astype(int)

    daily_agg = target.groupby("_invoice_day").agg(
        c=(COL_ORDER_ID, "count"), s=(COL_BUYER_PAID, "sum")).reset_index()
    all_days = sorted(set(daily_agg["_invoice_day"].tolist()) | set(paper.keys()))
    daily = []
    big_diff = []
    for d in all_days:
        row = daily_agg[daily_agg["_invoice_day"] == d]
        cnt = int(row["c"].iloc[0]) if not row.empty else 0
        amt = float(row["s"].iloc[0]) if not row.empty else 0
        p = paper.get(d, 0)
        diff = amt - p if p else 0
        status = "OK"
        if paper:
            if abs(diff) > 3000:
                status = "★大"
                big_diff.append(d)
            elif abs(diff) > 500:
                status = "★"
        daily.append({"day": d, "excel_count": cnt, "excel_amount": amt,
                     "paper_amount": p, "diff": diff, "status": status})

    typo_count = sum(1 for _, r in target.iterrows()
                     if detect_typo(r[COL_NOTE], year, month))

    excel_total = float(target[COL_BUYER_PAID].sum())
    paper_total = sum(paper.values())
    match_ratio = (1 - abs(excel_total - paper_total) / paper_total) * 100 if paper_total else 100.0

    # 順便寫出檔案（直接呼叫主程式的 reconcile）
    reconcile(excel_paths, year, month, out_dir, paper)

    return {
        "order_count": len(target),
        "excel_total": excel_total,
        "paper_total": paper_total,
        "diff": excel_total - paper_total,
        "match_ratio": match_ratio,
        "typo_count": typo_count,
        "big_diff_days": big_diff,
        "daily": daily,
    }


def _build_markdown(r, downloads):
    md = []
    md.append(f"## 對帳結果")
    md.append(f"- **訂單筆數**：{r['order_count']:,}")
    md.append(f"- **Excel 合計**：{r['excel_total']:,.0f} 元")
    if r["paper_total"]:
        md.append(f"- **紙本合計**：{r['paper_total']:,.0f} 元")
        md.append(f"- **差額**：{r['diff']:+,.0f} 元（吻合度 {r['match_ratio']:.2f}%）")
    md.append(f"- **Typo 修正**：{r['typo_count']} 筆")
    if r["big_diff_days"]:
        md.append(f"- **差異日**（>3000）：{', '.join(f'{d}日' for d in r['big_diff_days'])}")
    md.append("")
    md.append("### 下載報表")
    for name, url in downloads.items():
        md.append(f"- [{name}]({url})")
    return "\n".join(md)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8787))
    uvicorn.run(app, host="0.0.0.0", port=port)
