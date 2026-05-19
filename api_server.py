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

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse
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
def _check_key(api_key: Optional[str]):
    if API_KEY and api_key != API_KEY:
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
            "docs": f"{PUBLIC_BASE_URL}/docs"}


@app.post("/upload", response_model=UploadResp, summary="上傳檔案（Excel 或 CSV）")
async def upload(file: UploadFile = File(..., description="Excel (.xlsx) 或紙本 CSV"),
                 api_key: Optional[str] = Form(None)):
    """先上傳檔案，取得 file_id，再呼叫 /reconcile。"""
    _check_key(api_key)
    file_id = uuid.uuid4().hex[:12]
    session_dir = STORAGE_DIR / file_id
    session_dir.mkdir(exist_ok=True)
    target = session_dir / file.filename
    with open(target, "wb") as out:
        shutil.copyfileobj(file.file, out)
    return UploadResp(file_id=file_id, filename=file.filename,
                      size_bytes=target.stat().st_size)


@app.post("/reconcile", response_model=ReconcileResp, summary="對帳（用已上傳的 file_id）")
def do_reconcile(req: ReconcileReq):
    """主對帳端點：給 file_ids + month，回傳對帳結果 JSON + 下載 URL。"""
    _check_key(req.api_key)

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
