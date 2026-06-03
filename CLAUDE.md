# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**shopee-reconcile** is a Shopee monthly-settlement reconciliation tool. It reads Shopee `Order.completed` Excel exports, compares them against a paper ledger CSV, and generates three Excel reports: daily reconciliation, gap-day order details, and engineer bonus calculations.

The project has two operating modes:
- **CLI/desktop**: drag-and-drop via `對帳工具.bat`, or `python shopee_reconcile.py`
- **Web API**: FastAPI server (`api_server.py`) at port 8787, designed to be called by Chatbot UI / LLM tools

## Setup

```bash
pip install pandas openpyxl msoffcrypto-tool fastapi "uvicorn[standard]" python-multipart
cp .env.example .env   # then fill in SHOPEE_PASSWORD
```

## Common Commands

**CLI reconciliation:**
```bash
python shopee_reconcile.py Order.completed.20260301_20260331.xlsx
python shopee_reconcile.py 2月.xlsx 3月.xlsx --month=3 --year=115 --out=./output
```

**Run the API server:**
```bash
uvicorn api_server:app --host 0.0.0.0 --port 8787
# Swagger UI: http://localhost:8787/docs
```

**Run with Docker:**
```bash
docker compose up -d --build
```

**Generate test data and verify environment (expects 100% match ratio):**
```bash
python gen_test_data.py
python shopee_reconcile.py _test_data/Order.completed.20260301_20260331.xlsx --month=3 --year=115
```

**Cross-platform API smoke test:**
```bash
python deploy/smoke_test.py                          # test localhost:8787
python deploy/smoke_test.py https://your.url.com KEY # test remote with API key
```

## Architecture

### Core module: `shopee_reconcile.py`

The main reconciliation pipeline in `reconcile()`:
1. Reads and merges one or more Excel files via `read_excel_auto()` (handles msoffcrypto decryption transparently)
2. Filters completed orders for the target month using ROC calendar invoice dates parsed from order notes (`parse_invoice_day()`)
3. Compares daily totals against optional paper ledger CSV (`load_paper_data()`)
4. Computes engineer bonuses via `parse_note()` + `compute_bonus()`
5. Writes three `.xlsx` reports via `style_workbook()`

Key constants in `shopee_reconcile.py`:
- `VALID_CODES = {"B", "E", "J", "K", "P", "S"}` — engineer type codes
- `SALES_BONUS_RATE = 0.01` — 1% of order amount
- `REPAIR_BONUS_PER_UNIT = 80` — NTD per repair unit

### API server: `api_server.py`

FastAPI service that wraps the core module. Imports `reconcile` and `load_paper_data` directly from `shopee_reconcile.py`.

Storage layout:
- Uploads: `STORAGE_DIR/uploads/<uuid>/<original_filename>`
- Job outputs: `STORAGE_DIR/jobs/<job_id>/`
- Configured via `STORAGE_DIR` env var (defaults to `tempfile.gettempdir()`); Docker mounts `/data`

Key endpoints:
- `POST /upload` → returns `file_id`
- `POST /reconcile` → accepts `file_ids` + optional `paper_csv_id`, returns JSON summary + download URLs
- `GET /download/{job_id}/{filename}` → serves generated Excel files
- `GET /app` — full one-page web UI (drag-drop → reconcile → download)

Month auto-detection priority: explicit user input → paper CSV filename (`紙本對帳_115年3月.csv`) → Excel filename (`20260301_20260331`)

### Order note parsing

`parse_note()` handles three formats (from order `備註` column):

| Format | Example | Meaning |
|--------|---------|---------|
| A — unit-share ratio | `E=1,S=2,B=2` | Divide repair units proportionally |
| B — fixed amount per engineer | `E=1*600,S=1*600` | Each engineer gets fixed NTD |
| Three-segment | `115.3.5 ZM123456\|E=1*100,S=2*200\|5` | date, invoice, allocation, total units |

Tolerance patterns handled: `S600` → `S=1*600`, `S1*130` → `S=1*130`.

Invoice date typo correction in `detect_typo()`: `1153.X` / `113.3.X+ZM` → corrected to `115.3.X` (ROC year 115 = 2026 CE).

### Output files

All filenames use ROC year/month, e.g. `_115年3月`:
- `對帳表_115年3月.xlsx` — daily reconciliation + summary + typo list (3 sheets)
- `差異日明細_115年3月.xlsx` — order detail for days with gap > 3000 NTD
- `工程師獎金_115年3月.xlsx` — engineer bonus breakdown

`safe_path()` appends `_2`, `_3`, etc. to avoid overwriting existing files.

## Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `SHOPEE_PASSWORD` | Excel decryption password | read from `.env` |
| `API_KEY` | Optional API protection (header or body) | disabled if empty |
| `PUBLIC_BASE_URL` | Base URL for download links in API responses | `http://localhost:8787` |
| `STORAGE_DIR` / `STORAGE_ROOT` | Directory for uploads and job outputs | system temp dir |
| `PORT` | API server port | `8787` |

Password resolution order in `shopee_reconcile.py`: `SHOPEE_PASSWORD` env var → `.env` file in project root → empty string (works for unencrypted files).

## Data Conventions

- All dates use ROC calendar (民國): year 115 = 2026 CE
- Paper ledger CSV format: two columns `日,金額` (day number, amount); UTF-8 encoded; named `紙本對帳_115年Xm月.csv`
- Shopee Excel required columns: `訂單編號`, `訂單狀態`, `數量`, `買家總支付金額`, `備註`, `退貨數量`
- Orders with `退貨數量 > 0` are excluded from bonus calculation
- Only the first parseable note per order is used for bonus calculation
