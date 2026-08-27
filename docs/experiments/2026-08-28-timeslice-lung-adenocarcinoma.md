# 時間切片驗證：肺腺癌 — FAIL

**2026-08-28。判準在跑之前就寫死在 `tools/timeslice_experiment.py` 的 `GATES` 裡，沒有事後更動。**

只餵 2015 年以前的文獻，讓 ABC 橋接找出「還沒有人做過」的候選，再拿 2016–2026 實際發表的論文對答案。

```
錨點     Adenocarcinoma of Lung (D000077192)
切點     2015-12-31        追蹤窗 2016–2026
候選池   12,935            掃描 160 個才湊到 9 個切點前真正沉默的

前 20（實際 9 個）  命中率 0.444   平均 LTC 19.2
頻率配對對照組（5）  命中率 0.400   平均 LTC  6.4
比值 1.11           及格線 2.0     → FAIL
```

原始輸出：[2026-08-28-timeslice-lung-adenocarcinoma.json](./2026-08-28-timeslice-lung-adenocarcinoma.json)

## 數字比看起來更差

四個命中裡兩個是字面比對的產物：`Achievement`（語意類型 Individual Behavior，實際來自摘要裡的 "achievement of…"）與 `Surgical Instruments`。它們在驗證查詢裡「命中」，是因為驗證用的是同一套字串比對——同一個錯誤被計算了兩次，不是一次發現。

把那兩個和 `Microscopy, Electron, Transmission` 一併扣掉：

```
前 20   2/6 = 0.33
對照組  2/5 = 0.40     對照組反而較好
```

**沒有訊號。**

## 診斷：樞紐型文獻

剩下的「真」候選是 `Mouth Neoplasms`、`Carcinoma, Ovarian Epithelial`、`Alzheimer Disease`、`Parkinson Disease`、`Leukemia, Lymphocytic, Chronic`、`Carcinoma, Adenoid Cystic`——**全部是別的疾病**，而它們與肺腺癌共現的原因是泛癌症研究本來就會並列這些。

三十個 B 裡有九個是實驗技術（`Immunohistochemistry`、`Blotting, Western`、`Paraffin`、`In Situ Hybridization`…）。這些出現在每一篇癌症論文的方法段，全域背景頻率門檻 2% 擋不住它們，因為它們只在**這個領域**高頻。

肺腺癌光標題摘要就有 35,065 篇，它與癌症生物學的每個概念都已經連上了。透過那樣的 B 到得了的 C，就是「癌症研究裡的其他東西」。**那不是橋接結構，是輪輻。**

Swanson 最初成功的案例——雷諾氏症 → 血液黏稠度 → 魚油——三端都是稀疏的小文獻。**這次的失敗與「LBD 只在稀疏文獻上有效」一致，但這次實驗沒有測那個假說，所以那仍然只是假說。**

## 事前約定的處置

判準未過 → **不為此類題目建 ABC**。若日後要在稀疏錨點上重測，那是**一次全新的實驗**，本紀錄不因此被覆蓋。
