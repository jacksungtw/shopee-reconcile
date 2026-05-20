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


APP_HTML = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Shopee 月結對帳</title>
<style>
:root{--c1:#1F4E78;--c2:#F4B084;--c3:#FFE699;--ok:#2e7d32;--bg:#f5f7fa}
*{box-sizing:border-box}
body{font-family:"Microsoft JhengHei","Segoe UI",sans-serif;background:var(--bg);
     margin:0;padding:20px;color:#222}
.wrap{max-width:860px;margin:0 auto}
h1{color:var(--c1);font-size:23px;margin:0 0 4px}
.sub{color:#667;font-size:13px;margin-bottom:18px}
.card{background:#fff;border-radius:10px;padding:20px;margin-bottom:14px;
      box-shadow:0 2px 6px rgba(0,0,0,.06)}
.drop{border:2px dashed #aac;border-radius:10px;padding:40px 16px;text-align:center;
      background:#fafbfd;cursor:pointer;transition:.2s}
.drop:hover,.drop.over{background:#eef3fa;border-color:var(--c1)}
.drop p{margin:0;color:#557}
input[type=file]{display:none}
.row{display:flex;gap:12px;align-items:center;margin:12px 0;flex-wrap:wrap}
.row label{font-size:14px;color:#556}
select,input[type=number]{padding:6px 10px;border:1px solid #ccd;border-radius:6px;font-size:14px}
.filelist{margin:10px 0}
.fitem{display:flex;justify-content:space-between;align-items:center;
       padding:8px 10px;border-bottom:1px solid #eee;font-size:14px}
.fitem:last-child{border:none}
.tag{display:inline-block;padding:2px 8px;border-radius:3px;font-size:11px;margin-right:8px}
.tag.xls{background:var(--c3);color:#664}
.tag.csv{background:#cde;color:#246}
.btn{background:var(--c1);color:#fff;border:none;padding:11px 26px;border-radius:7px;
     cursor:pointer;font-size:15px;font-weight:bold}
.btn:hover{opacity:.92}
.btn:disabled{background:#aab;cursor:not-allowed}
.btn.sm{padding:4px 10px;font-size:12px;background:#999;font-weight:normal}
.result{display:none}
.kpi{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:14px 0}
.kpi .box{background:#f4f7fb;border-radius:8px;padding:12px 14px;text-align:center}
.kpi .box .v{font-size:22px;font-weight:bold;color:var(--c1)}
.kpi .box .l{font-size:12px;color:#778;margin-top:3px}
.kpi .box.good .v{color:var(--ok)}
.kpi .box.warn .v{color:#c0392b}
table{width:100%;border-collapse:collapse;font-size:13px;margin-top:8px}
th,td{padding:6px 8px;border:1px solid #e3e8ef;text-align:center}
th{background:var(--c1);color:#fff}
tr.big td{background:#fdecea}
tr.star td{background:#fff8e6}
.dl a{display:inline-block;margin:4px 8px 4px 0;padding:8px 14px;background:var(--ok);
      color:#fff;text-decoration:none;border-radius:6px;font-size:13px}
.dl a:hover{opacity:.9}
.spinner{display:none;text-align:center;padding:30px;color:#667}
.spinner.on{display:block}
.err{display:none;background:#fdecea;color:#c0392b;padding:12px 16px;border-radius:8px;
     margin-top:10px;font-size:14px}
.hint{font-size:12px;color:#8a93a0;margin-top:6px}
</style>
</head>
<body>
<div class="wrap">
  <h1>Shopee 月結對帳</h1>
  <div class="sub">拖入訂單 Excel（可多個）+ 紙本日結 CSV → 一鍵對帳，自動產出報表</div>

  <div class="card">
    <div id="drop" class="drop" onclick="document.getElementById('fi').click()">
      <p>📎 把 Excel (.xlsx) 與紙本 CSV 拖到這裡</p>
      <p style="font-size:12px;color:#99a;margin-top:6px">或點此選檔案（可一次多選）</p>
    </div>
    <input type="file" id="fi" multiple accept=".xlsx,.xls,.csv">
    <div id="filelist" class="filelist"></div>
    <div class="row">
      <label>月份（留空自動偵測）：
        <select id="month">
          <option value="">自動</option>
        </select>
      </label>
      <label>民國年：<input type="number" id="year" value="115" style="width:80px"></label>
      <button class="btn" id="go" onclick="run()" disabled>開始對帳</button>
    </div>
    <div class="hint">※ 加密 Excel 會自動解密；同一訂單只算一次；退貨自動排除</div>
  </div>

  <div class="spinner card" id="spinner">⏳ 對帳中，請稍候…（首次約 10 秒）</div>
  <div class="err card" id="err"></div>

  <div class="card result" id="result">
    <h2 style="margin:0 0 6px;color:var(--c1);font-size:18px" id="rtitle"></h2>
    <div class="kpi" id="kpi"></div>
    <div class="dl" id="dl"></div>
    <h3 style="margin:18px 0 4px;font-size:15px;color:var(--c1)">逐日對帳</h3>
    <div style="overflow-x:auto"><table id="daily"></table></div>
  </div>
</div>

<script>
let files = [];
const drop=document.getElementById('drop'), fi=document.getElementById('fi'),
      flist=document.getElementById('filelist'), go=document.getElementById('go');
const msel=document.getElementById('month');
for(let m=1;m<=12;m++){const o=document.createElement('option');o.value=m;o.textContent=m+'月';msel.appendChild(o);}

['dragenter','dragover'].forEach(e=>drop.addEventListener(e,ev=>{ev.preventDefault();drop.classList.add('over')}));
['dragleave','drop'].forEach(e=>drop.addEventListener(e,ev=>{ev.preventDefault();drop.classList.remove('over')}));
drop.addEventListener('drop',ev=>addFiles(ev.dataTransfer.files));
fi.addEventListener('change',()=>addFiles(fi.files));

function addFiles(fl){
  for(const f of fl) files.push(f);
  render();
}
function render(){
  if(files.length===0){flist.innerHTML='';go.disabled=true;return;}
  flist.innerHTML=files.map((f,i)=>{
    const csv=f.name.toLowerCase().endsWith('.csv');
    return `<div class="fitem"><span><span class="tag ${csv?'csv':'xls'}">${csv?'紙本':'Excel'}</span>${f.name}</span>
            <button class="btn sm" onclick="rm(${i})">移除</button></div>`;
  }).join('');
  go.disabled = !files.some(f=>!f.name.toLowerCase().endsWith('.csv'));
}
function rm(i){files.splice(i,1);render();}

async function run(){
  document.getElementById('result').style.display='none';
  document.getElementById('err').style.display='none';
  document.getElementById('spinner').classList.add('on');
  go.disabled=true;
  try{
    // 1. 逐一上傳
    const excelIds=[]; let csvId=null;
    for(const f of files){
      const fd=new FormData(); fd.append('file',f);
      const r=await fetch('/upload',{method:'POST',body:fd});
      if(!r.ok) throw new Error('上傳失敗: '+f.name);
      const d=await r.json();
      if(f.name.toLowerCase().endsWith('.csv')) csvId=d.file_id;
      else excelIds.push(d.file_id);
    }
    // 2. 對帳
    const body={file_ids:excelIds};
    if(csvId) body.paper_csv_id=csvId;
    const mv=document.getElementById('month').value;
    if(mv) body.month=parseInt(mv);
    body.year=parseInt(document.getElementById('year').value)||115;
    const r2=await fetch('/app/reconcile',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    if(!r2.ok){const t=await r2.text();throw new Error('對帳失敗 ('+r2.status+'): '+t);}
    const res=await r2.json();
    showResult(res);
  }catch(e){
    document.getElementById('err').textContent='❌ '+e.message;
    document.getElementById('err').style.display='block';
  }finally{
    document.getElementById('spinner').classList.remove('on');
    go.disabled=false;
  }
}

function showResult(res){
  document.getElementById('rtitle').textContent='✅ '+res.target_month+' 對帳完成';
  const ratio=res.match_ratio_percent;
  const ratioClass = ratio>=95?'good':'warn';
  const kpi=[
    ['訂單筆數',res.order_count.toLocaleString(),''],
    ['Excel 合計','$'+Math.round(res.excel_total).toLocaleString(),''],
    ['紙本合計','$'+Math.round(res.paper_total).toLocaleString(),''],
    ['差額',(res.diff>=0?'+':'')+Math.round(res.diff).toLocaleString(),''],
    ['吻合度',ratio.toFixed(2)+'%',ratioClass],
    ['Typo 修正',res.typo_count+' 筆',res.typo_count>0?'warn':''],
  ];
  document.getElementById('kpi').innerHTML=kpi.map(k=>
    `<div class="box ${k[2]}"><div class="v">${k[1]}</div><div class="l">${k[0]}</div></div>`).join('');
  document.getElementById('dl').innerHTML=Object.entries(res.downloads).map(
    ([n,u])=>`<a href="${u}" target="_blank">📥 ${n}</a>`).join('');
  // 逐日表
  let html='<tr><th>日期</th><th>Excel筆數</th><th>Excel金額</th><th>紙本金額</th><th>差額</th><th>狀態</th></tr>';
  for(const d of res.daily){
    const cls=d.status==='★大'?'big':(d.status==='★'?'star':'');
    html+=`<tr class="${cls}"><td>${d.day}日</td><td>${d.excel_count}</td>
           <td>${Math.round(d.excel_amount).toLocaleString()}</td>
           <td>${Math.round(d.paper_amount).toLocaleString()}</td>
           <td>${(d.diff>=0?'+':'')+Math.round(d.diff).toLocaleString()}</td>
           <td>${d.status}</td></tr>`;
  }
  document.getElementById('daily').innerHTML=html;
  document.getElementById('result').style.display='block';
}
</script>
</body>
</html>
"""


@app.get("/app", response_class=HTMLResponse, summary="對帳網頁（整合式，給人類用）")
def app_ui():
    """一站式對帳網頁：拖檔 → 自動對帳 → 顯示結果 + 下載。"""
    return APP_HTML


@app.post("/app/reconcile", response_model=ReconcileResp, summary="網頁專用對帳端點")
def app_reconcile(req: ReconcileReq, x_api_key: Optional[str] = Header(None)):
    """與 /reconcile 相同邏輯，路徑在 /app 下方便 Caddy 自動注入 API key。"""
    return do_reconcile(req, x_api_key)


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

    # 找出紙本 CSV（順便用它的檔名偵測月份，最準）
    import re
    csv_src = None
    csv_month = None
    if req.paper_csv_id:
        d = STORAGE_DIR / req.paper_csv_id
        csv_files = [f for f in d.iterdir() if f.suffix.lower() == ".csv"]
        if csv_files:
            csv_src = csv_files[0]
            # 從檔名抓「X月」或「115年X月」
            mm = re.search(r"(\d{1,2})\s*月", csv_src.name)
            if mm:
                csv_month = int(mm.group(1))

    # 決定目標月份：
    #   1) 使用者明確指定 → 最優先
    #   2) 紙本 CSV 檔名（如「紙本對帳_115年3月.csv」）→ 次之（最貼合對帳意圖）
    #   3) Excel 檔名最大月份 → 最後備援
    month = req.month
    if month is None:
        month = csv_month
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
    if csv_src is not None:
        csv_target = out_dir / f"紙本對帳_{req.year}年{month}月.csv"
        shutil.copy(csv_src, csv_target)
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
