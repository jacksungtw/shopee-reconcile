# -*- coding: utf-8 -*-
"""跨平台冒煙測試（Windows/Linux 通用）

用法：
  python deploy/smoke_test.py                          # 測 localhost:8787
  python deploy/smoke_test.py https://your.url.com     # 測遠端
  python deploy/smoke_test.py https://your.url.com KEY # 帶 API key
"""
import sys
import json
import subprocess
import tempfile
import shutil
from pathlib import Path

import urllib.request
import urllib.error


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8787"
    api_key = sys.argv[2] if len(sys.argv) > 2 else None

    print(f"===== Shopee 對帳 API 冒煙測試 =====")
    print(f"目標: {base}\n")

    # 1. 健康檢查
    print("[1/4] 健康檢查 GET /")
    try:
        with urllib.request.urlopen(f"{base}/") as r:
            data = json.loads(r.read())
            print(f"  ✓ {data.get('service')} v{data.get('version')}")
    except Exception as e:
        print(f"  ✗ 失敗: {e}")
        sys.exit(1)

    # 2. 上傳網頁
    print("\n[2/4] 上傳網頁 GET /upload-ui")
    try:
        with urllib.request.urlopen(f"{base}/upload-ui") as r:
            html = r.read().decode("utf-8")
            assert "Shopee 對帳" in html
            print(f"  ✓ HTML 載入 ({len(html)} bytes)")
    except Exception as e:
        print(f"  ✗ 失敗: {e}")
        sys.exit(1)

    # 3. 產假資料 + 上傳
    print("\n[3/4] 產生假資料並上傳")
    repo = Path(__file__).resolve().parent.parent
    result = subprocess.run([sys.executable, "gen_test_data.py"],
                           cwd=repo, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ✗ 產假資料失敗: {result.stderr}")
        sys.exit(1)

    excel = repo / "_test_data" / "Order.completed.20260301_20260331.xlsx"
    csv = repo / "_test_data" / "紙本對帳_115年3月.csv"

    excel_id = _upload(base, excel, api_key)
    csv_id = _upload(base, csv, api_key)
    print(f"  ✓ Excel: {excel_id}")
    print(f"  ✓ CSV:   {csv_id}")

    # 4. 對帳
    print("\n[4/4] 呼叫 /reconcile")
    payload = {
        "file_ids": [excel_id],
        "paper_csv_id": csv_id,
        "month": 3, "year": 115,
    }
    if api_key:
        payload["api_key"] = api_key

    req = urllib.request.Request(
        f"{base}/reconcile",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(f"  ✗ HTTP {e.code}: {e.read().decode()}")
        sys.exit(1)

    print(f"  訂單筆數:   {d['order_count']}")
    print(f"  Excel 合計: {d['excel_total']:,.0f}")
    print(f"  紙本合計:   {d['paper_total']:,.0f}")
    print(f"  差額:       {d['diff']:+,.0f}")
    print(f"  吻合度:     {d['match_ratio_percent']:.2f}%")
    print(f"  Typo:       {d['typo_count']} 筆")
    print("\n  下載連結:")
    for k, v in d['downloads'].items():
        print(f"    {k}: {v}")

    # 驗收條件
    assert d['match_ratio_percent'] == 100.0, "吻合度不是 100%"
    assert d['order_count'] > 0, "訂單筆數為 0"
    print("\n===== 全部測試通過 ✅ =====")


def _upload(base, filepath, api_key):
    """multipart 上傳"""
    import uuid
    boundary = f"----boundary{uuid.uuid4().hex}"
    fname = filepath.name

    body = b""
    body += f"--{boundary}\r\n".encode()
    body += f'Content-Disposition: form-data; name="file"; filename="{fname}"\r\n'.encode("utf-8")
    body += b"Content-Type: application/octet-stream\r\n\r\n"
    body += filepath.read_bytes()
    body += b"\r\n"
    if api_key:
        body += f"--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="api_key"\r\n\r\n'
        body += api_key.encode()
        body += b"\r\n"
    body += f"--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        f"{base}/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())["file_id"]


if __name__ == "__main__":
    main()
