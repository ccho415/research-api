# 唱反調的五條規則，逐條對著線上資料庫驗

2026-08-30。W-ADMIN 執行 160–164。**零成本**——沒有任何一次模型呼叫。

## 為什麼要這樣驗

S9 的每一條規則都是為了擋一種**看起來像正常運作**的失效：一場讀起來很精彩、
但方向出來變得更軟更模糊、而且沒有經歷過任何實質攻擊的辯論。

那種失效不會在跑真的辯論時暴露出來——真的辯論產出漂亮的逐字稿，而逐字稿
永遠讀起來合理。所以規則要在**沒有模型參與**的情況下先驗過：直接餵構造好的
回合給 `/compute/debate/round`，看資料庫拒不拒絕。模型那一半是另一件事。

夾具用 C 級的 `0788a78a`（Noise x Smog x Hemorrhagic Stroke），因為它是這個專案裡
唯一有引用池的方向（W7 跑過，40 篇論文）。

## 結果

### 一輪三個反對，只有一個站得住（執行 160）

送進去：

1. 交通噪音與空污空間高度相關，聯合模型分不開兩者 —— `strong`，附
   *Transportation Noise Pollution and Cardiovascular Health* (2024, doi 10.1161/circresaha.123.323584)，
   `unresolved`，分數 2
2. 「這大概已經被 exposome 文獻涵蓋了」 —— `weak`、分數 3、想標 `resolved_by_evidence`
3. 「前案已經完全解決了交互作用問題」 —— 標 `strong` 但**沒附任何論文**

回：

```
n_objections_saved: 1
n_objections_open:  1
n_cited_open:       1
terminated:         false
rejected: [
  {2, "conceding to evidence needs a rebuttal_score of 4 or 5.
       At 3 or below the objection is plausible but unevidenced,
       and you do not concede to plausible."},
  {3, "`strong` means this objection stands on a real paper.
       Without one it is an opinion."}
]
```

**逐筆退回而不是整輪退回**，是刻意的。一個 critic 產出四個好反對和一個軟掉的
讓步，該掉的是那個讓步，不是那一輪。而且退回理由會回給呼叫端——一個一直
寫出同一種不可用形狀的模型，會變成一個看得見的模式，不是一份安靜變短的清單。

### 兩邊同一個模型（執行 161）

400，整輪拒收：

> proposer and critic are the same model. A model arguing with itself shares its
> own blind spots, and the transcript looks like a debate while being a monologue.

### 漂移壓過一切（執行 162）

第 2 輪送進去一個**還開著、而且有引用**的反對，同時把敘述換成完全不同的題目
（膝關節置換術後再入院預測）。

```
round_no: 2
drift_from_original: 1.0
terminated: true
termination_reason: "drift 1.0 exceeds 0.5; the revision has moved far enough
                     from the original that it is a different direction"
```

這是最重要的一條。有引用的反對還開著，照規則辯論該繼續——但漂移排在它前面。
**十輪小小的通融可以把一個方向走成另一個方向，而每一步看起來都合理**，
輪數上限救不了已經變成別的東西的方向。

漂移一律對照 `original_statement`，不對照上一輪。對照上一輪正是那種走法
能一直隱形的原因。

### 漂移停之後不能採用（執行 163）

400：

> this debate was stopped for drift, so its final text is not an improved version
> of the original - it is a different direction that arrived one reasonable-looking
> step at a time. Read the transcript and propose it as its own direction if it is
> worth having.

### 停了就不能再送（執行 164）

400：「reopening it would append rounds after a recorded ending」。

## 離線量到的漂移尺度

`python test_debate.py`：

| 改動 | 漂移 |
|---|---|
| 一字不改 | 0.0 |
| 收緊一個子句（`adults over 50` → `adults aged 50 to 75`） | 0.053 |
| 換成另一個題目 | 0.966 |

`DRIFT_MAX = 0.5` 落在中間那一大段空白裡。**但沒有任何真實辯論軌跡支持這個數字。**
每一輪都記下原始漂移值，所以之後可以從資料重設而不用重跑。如果早期辯論全都在
第 2 輪因漂移停掉，那就是這個數字錯了，而 `termination_reason` 會直接說出來。

## 沒驗到的

**兩個模型還沒有真的打過一場。** 這個專案的看板是 `{A:0, B:0, C:1, D:7}`，
W8 預設只打 A/B，所以它正確地擋下來了（執行 165）。攻擊 → 解析 → 辯護 → 解析
→ 重跑 → 寫入這半條鏈**尚未實跑**，不要當成已驗證。

## 這組夾具留下的痕跡

`0788a78a` 現在有兩列 `debate_round`（第 1、2 輪）和一列 `objection`，
全部是人工造的，而且該方向的辯論已被標成終止。**要對它跑真的辯論之前，
得先把這兩列刪掉。**
