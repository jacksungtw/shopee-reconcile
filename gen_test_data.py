# -*- coding: utf-8 -*-
"""產生測試假資料：模擬 Shopee 訂單 Excel + 紙本對帳 CSV"""

import os
import random
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

OUT_DIR = Path(__file__).parent / "_test_data"
OUT_DIR.mkdir(exist_ok=True)

TARGET_YEAR = 115
TARGET_MONTH = 3
PASSWORD = "your_password_here"  # 測試用 placeholder，實際密碼放 .env

# ---- 紙本對帳 CSV ----
paper_days = {
    3: 69435, 4: 113716, 5: 81378, 6: 88955,
    9: 131138, 10: 80907, 11: 95177, 12: 79469,
    13: 64303, 16: 130976, 17: 75603, 18: 81542,
    19: 57955, 20: 68116, 23: 123981, 24: 86418,
    25: 90408, 26: 61318, 27: 46618, 30: 115324,
    31: 67809,
}
paper_df = pd.DataFrame([
    {"日": d, "金額": a} for d, a in sorted(paper_days.items())
])
paper_path = OUT_DIR / f"紙本對帳_{TARGET_YEAR}年{TARGET_MONTH}月.csv"
paper_df.to_csv(paper_path, index=False, encoding="utf-8-sig")
print(f"[OK] 紙本對帳: {paper_path} ({len(paper_df)} 天)")

# ---- 模擬 Shopee 訂單 ----
VALID_CODES = ["B", "E", "J", "K", "P", "S"]

def make_orders():
    orders = []
    oid_base = 25030100000
    base_date = datetime(2026, 3, 1)

    def add(day, note, amount, status="已完成", return_qty=0, qty=1):
        nonlocal oid_base
        oid_base += 1
        order_dt = base_date + timedelta(days=day - 1)
        orders.append({
            "訂單編號": str(oid_base),
            "訂單狀態": status,
            "數量": qty,
            "買家總支付金額": amount,
            "備註": note,
            "退貨數量": return_qty,
            "訂單成立日期": order_dt.strftime("%Y-%m-%d"),
            "訂單完成時間": (order_dt + timedelta(days=3)).strftime("%Y-%m-%d %H:%M"),
            "實際出貨時間": (order_dt + timedelta(days=1)).strftime("%Y-%m-%d %H:%M"),
        })

    # ==== 標準格式 A類 ====
    add(3, f"{TARGET_YEAR}.{TARGET_MONTH}.3 ZM111111|E=2,S=3|5", 69435, qty=5)

    # ==== Typo 1153.X ====
    add(4, f"{TARGET_YEAR}{TARGET_MONTH}.4 ZM222222|E=1*600,S=1*800,B=1*500", 113716, qty=3)

    # ==== Typo 113.3.X with ZM ====
    add(5, f"113.{TARGET_MONTH}.5 ZM333333|E=1,S=1,J=1", 81378, qty=3)

    # ==== 標準格式 B類 ====
    add(6, f"{TARGET_YEAR}.{TARGET_MONTH}.6 ZM444444|S=2*900,P=1*700", 88955, qty=3)

    # ==== 多筆同日 ====
    add(9, f"{TARGET_YEAR}.{TARGET_MONTH}.9 ZM555555|B=3", 65569, qty=3)
    add(9, f"{TARGET_YEAR}.{TARGET_MONTH}.9 ZM555556|K=2", 65569, qty=2)

    # ==== A類多工程師 ====
    add(10, f"{TARGET_YEAR}.{TARGET_MONTH}.10 ZM777777|E=1,S=2,B=1", 80907, qty=4)

    # ==== B類含退貨 ====
    add(11, f"{TARGET_YEAR}.{TARGET_MONTH}.11 ZM888888|E=1*300,S=2*400", 95177, qty=3, return_qty=1)

    # ==== 容錯 S600 ====
    add(12, f"{TARGET_YEAR}.{TARGET_MONTH}.12 ZM999999|S600,E=1*400", 79469, qty=2)

    # ==== 容錯 S1*130 ====
    add(13, f"{TARGET_YEAR}.{TARGET_MONTH}.13 ZM000001|S1*130,B=2", 64303, qty=3)

    # ==== 無分配 (bonus 跳過，但不影響對帳) ====
    add(16, f"{TARGET_YEAR}.{TARGET_MONTH}.16 ZMAABBBB", 130976, qty=2)

    # ==== 多行備註 ====
    add(17, f"{TARGET_YEAR}.{TARGET_MONTH}.17 ZMACCCCC\nE=1*450\nS=2*400", 75603, qty=3)

    # ==== 發票後分配 (| 分配在前) ====
    add(18, f"E=2,S=1|{TARGET_YEAR}.{TARGET_MONTH}.18 ZMADDDDD", 81542, qty=3)

    # ==== 三段式 ====
    add(19, f"{TARGET_YEAR}.{TARGET_MONTH}.19 ZMAEEEEE|E=1*200,B=2*350|7", 57955, qty=3)

    # ==== 標準日期含空白 ====
    add(20, f"{TARGET_YEAR}. {TARGET_MONTH}.20 ZMAFFFFF|P=1,S=2", 68116, qty=3)

    # ==== 非目標月訂單（應被排除）====
    add(23, f"114.{TARGET_MONTH}.23 ZMAGGGGG|E=1,S=1", 50000)
    add(23, f"115.2.23 ZMAGGGHH|E=1,S=1", 50000)

    # ==== 大量標準訂單（對應紙本各日）====
    for day, paper_amt in [(23, 123981), (24, 86418), (25, 90408),
                            (26, 61318), (27, 46618), (30, 115324), (31, 67809)]:
        n = random.randint(2, 3)
        amounts = [paper_amt // n] * n
        amounts[-1] += paper_amt - sum(amounts)
        for i in range(n):
            engs = random.sample(VALID_CODES, random.randint(1, 2))
            alloc = ",".join(f"{e}={random.randint(1, 3)}" for e in engs)
            add(day, f"{TARGET_YEAR}.{TARGET_MONTH}.{day} ZM{random.randint(100000, 999999)}|{alloc}",
                amounts[i], qty=sum(1 for _ in engs) * random.randint(1, 3))

    return pd.DataFrame(orders)


df = make_orders()

# 西元年檔名讓自動月份偵測生效 (2026=115年)
xlsx_path = OUT_DIR / f"Order.completed.2026{TARGET_MONTH:02d}01_2026{TARGET_MONTH:02d}31.xlsx"
df.to_excel(xlsx_path, index=False, engine="openpyxl")
print(f"[OK] 測試 Excel: {xlsx_path} ({len(df)} 筆)")

print(f"\n測試資料就緒！共 {len(df)} 筆模擬訂單")
print(f"\n涵蓋情境：")
print(f"  標準發票日期、Typo(1153.X/113.3.X+ZM)")
print(f"  A類(支數比例) / B類(固定金額)")
print(f"  退貨、多行備註、三段式備註")
print(f"  容錯(S600/S1*130)、非目標月(排除)")
print(f"  紙本對帳 ({len(paper_df)} 天)")
