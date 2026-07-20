# Shopee 待出貨工程師分配規則 v127

更新日期：2026-07-20

這份文件整理 `Order.toship.*.xlsx` 待出貨訂單分配規則，用於產生「原來分配格式交接版」。

> 注意：Excel 解密密碼不要寫進公開 repo。請由 `.env` 或本機設定提供，例如 `SHOPEE_PASSWORD`。

---

## 固定輸出格式

輸出活頁簿必須包含以下工作表，順序固定：

1. 摘要
2. 分配總表
3. P
4. E
5. B
6. S
7. J
8. K
9. 1000以下
10. 未分配
11. 直列表
12. orders
13. 說明

分配用工作表固定 11 欄：

```text
訂單編號
商品名稱
商品選項名稱
標準型號
記憶體GB
金額
數量
最晚出貨日期
到期等級
分配工程師
分配依據
```

`orders` 工作表必須同步更新欄位：

```text
成交手續費規則名稱
```

---

## 分配優先順序

```text
最新人工指定
>
商品選項名稱防呆
>
機型固定規則
>
品牌延伸規則
>
價格規則
>
未分配
```

驗證要求：

```text
未分配 = 0
orders 成交手續費規則名稱不可空白
各工程師分頁筆數需與摘要一致
```

---

## iPhone 防呆規則

商品名稱與商品選項名稱衝突時，以商品選項名稱優先。

```text
iPhone 6 / i Phone 6      -> B
iPhone 6s / i Phone 6s    -> P
iPhone 6 Plus             -> E
iPhone 6s Plus            -> S
iPhone 7                  -> J
iPhone 7 Plus             -> S
iPhone 8 / i8             -> J
iPhone XR                 -> E
iPhone X / XS / 11        -> K
iPhone SE / 5s            -> K
iPhone 4 / iPhone 5       -> K
```

---

## 最新人工指定規則

### ASUS / 平板

```text
X00ID     -> E
X00QD     -> E
X017DA    -> E
TF103C    -> E
Z380KL    -> E
Z300C     -> E
Z301ML    -> E
Z01RD     -> E
ME310T    -> E
A001      -> E
Max Pro   -> E
S7        -> E
X00PD     -> K
ZD552KL   -> K
Z012DA    -> K
ZE554KL   -> K
T00P      -> 1000以下
```

### Sony

```text
XA1 Ultra        -> E
Z5P / Z5 Premium -> E
XZ1              -> P
XZP / XZ Premium -> S
XZs              -> S
F5321            -> S
Sony Xperia XZ   -> K
Sony C3          -> 1000以下
Sony XA Ultra    -> 1000以下
```

### Samsung

```text
Tab A7          -> E
A22 64G         -> P
A50             -> P
A60             -> P
A80             -> P
A73 5G          -> B
A78             -> B
A31             -> B
A77             -> B
A73 / A73S      -> 1000以下
S6 Edge         -> 1000以下
Note3 / Note 3  -> 1000以下
S3              -> 1000以下
```

### OPPO

```text
Reno 10x -> B
Reno 8   -> B
Reno 4   -> B
Reno Z   -> B
Reno 6   -> B
R15      -> B
A53      -> B
A55      -> B
AX5s     -> E
AX5      -> S
R9 / R9 Plus / R11s / R11s Plus / F1 / F1f -> 1000以下
```

### Xiaomi / Redmi / POCO

```text
POCO              -> E
紅米7             -> E
紅米 Note 7       -> E
Mi 6              -> J
MI 6              -> J
MIX 3             -> J
小米 Max 3        -> J
紅米 Note 5       -> J
紅米 Note 9 Pro   -> J
紅米 Note 9T      -> J
紅米 Note 11      -> J
紅米 Note 12      -> J
小米 Max          -> 1000以下
小米紅米4.7       -> 1000以下
Note 2            -> 1000以下
```

### Huawei

```text
Huawei / 華為 -> B
Mate 10 Pro   -> B
Mate 20       -> B
Mate 20 Pro   -> B
P30           -> B
```

### Vivo / Realme / Sugar / HTC

```text
Y12 / Y12s       -> S
Y20s             -> S
Y21              -> S
V9               -> S
Y9 2019          -> S
Y17s             -> K
Y81              -> K
Y95              -> 1000以下
Y13s             -> J
Realme 5         -> S
Realme C11       -> S
Realme 其他      -> J
Sugar C60        -> J
Sugar T30        -> J
Sugar 其他       -> J
HTC 10           -> E
HTC U23          -> B
HTC Desire 12s   -> K
HTC 其他         -> K
S720E            -> 1000以下
```

### 其他

```text
Acer Iconia A1-810 -> E
Pixel / Google     -> P
Nokia              -> P
LG                 -> P
J4                 -> K
X01BDA             -> K
```

---

## 品牌延伸規則

未命中人工指定時，依品牌延伸：

```text
Samsung / Galaxy -> B
ASUS / Zenfone   -> P
Huawei / 華為     -> B
OPPO             -> B
Sony / Xperia    -> P
Xiaomi / Redmi   -> J
POCO             -> E
Realme           -> J
Google / Pixel   -> P
Nokia            -> P
LG               -> P
Vivo             -> K
HTC              -> K
Sugar            -> J
iPhone           -> K
```

---

## 價格規則

```text
商品活動價格 <= 1000 -> 1000以下
```

價格規則低於人工指定與機型固定規則。也就是說，如果人工指定 `iPhone 5 -> K`，即使價格低於 1000，仍分到 K。

---

## 目前最後驗證版本

最後在本地驗證版本：

```text
v127
Order.toship.20260620_20260720_原來分配格式交接版_v127.xlsx
```

v127 統計：

```text
P 31
E 22
B 41
S 24
J 20
K 25
1000以下 35
未分配 0
```

---

## 實作注意事項

1. 不要把真實訂單 Excel 上傳到公開 repo。
2. 不要把解密密碼寫進公開 repo。
3. 每次新增人工指定規則，都要放在品牌延伸規則之前。
4. 每次產檔後必須讀回檢查：分頁順序、orders 同步、未分配為 0。
5. 若出現未分配，先列出機型與商品選項，再補規則，不能直接交檔。
