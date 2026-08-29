# 去重合併的驗證（2026-08-29）

`/compute/dedup/resolve` 蓋好之後一直沒被真的跑過——資料庫裡從來沒有一組
`verdict = 'duplicate'`。兩次 W4、40 組配對全部判成 distinct，所以 union-find、
存活者規則、人工覆寫三條路徑都是沒執行過的程式碼。

這份紀錄是**造一組真的重複方向**把它們跑過一遍。

## 測試資料

專案 `7d495464-8570-480c-8b65-689ee8a3291b`，run `fca9c0e0-b15b-42fd-81aa-2a84a7fe3d2c`，
七個方向：

| code | 方向 | 設計意圖 |
|---|---|---|
| 1 | PM2.5 × 腦小血管疾病進展 | 與 2 重複 |
| 2 | 2.5 微米以下懸浮微粒 × 腦部小血管疾病進展 | 與 1、3 重複；**記錄最完整**（有 method_sketch 與 required_variables） |
| 3 | 細懸浮微粒 × 腔隙性梗塞發生率 | 與 2 重複，**與 1 幾乎不共用字詞** |
| 4 | PM2.5 × 腸道菌相 | 與 1 共用實體但問題不同 |
| 5 | 腦小血管疾病 × 心率變異度 | 不重複 |
| 6 | 臭氧 × 白質高訊號體積 | 與 7 重複 |
| 7 | 環境臭氧 × MRI 白質病變負荷 | 與 6 重複 |

1／2／3 是同一個問題的三種寫法，但**只有 1~2 與 2~3 在字面上看得出來**。
1 說「PM2.5」「cerebral small vessel disease」，3 說「fine particulate」
「lacunar infarction」，兩者幾乎沒有共同字詞。只做逐對比較的合併會留下三個裡的兩個。

2 是**中間那個**且記錄最完整，所以「取第一個」或「取最後一個」的規則都會挑錯卻看起來對。

## W4 自己找到了什麼

執行 129，16 組候選配對：

```
duplicate  6~7   「兩者都在問臭氧暴露是否與中年人的白質病變相關」
duplicate  1~2   「兩者都在問長期 PM2.5 暴露是否加速年長者腦小血管疾病進展」
distinct   2~3   「腔隙性梗塞是小血管疾病的一個特定表現，屬不同研究範圍」
其餘 13 組 distinct
```

**2~3 被判 distinct，而那個判斷是有道理的**——腔隙性梗塞確實是小血管疾病的一個子表現。
所以遞移鏈是我**手動補上**的（用 `/compute/dedup/save` 寫一列 2~3 duplicate），
測的是 resolver 而不是 W4 的判斷力。另外補了一組 3~4 `uncertain`。

## 驗到的六件事

```
POST /compute/dedup/resolve  {"run_id": "fca9c0e0…", "dry_run": true}

n_clusters 2   n_merged 3
  keep code 6  ← merged code 7
  keep code 2  ← merged code 1, code 3     basis: fullest record, then earliest, then lowest code
```

1. **遞移合併**：1~2 與 2~3 是僅有的兩條連結，1 與 3 從未被比對過，三個仍合併成一個。
2. **存活者取記錄最完整的**：留下 code 2（completeness 4，其餘為 2）。
3. **同分決勝是決定性的**：6／7 完整度相同，`created_at` 也相同，靠 `code` 分出 6。
4. **`uncertain` 不合併**：3~4 存成 NULL verdict，4 沒有進任何叢集。
5. **`distinct` 不合併**：4、5 保持獨立。
6. **`/compute/ideas/live` 回 4 個**（code 2、4、5、6）——被合併的三個確實擋在錦標賽之外。

人工覆寫另外測：

```
POST /compute/dedup/keep  {"idea_id": "<code 1>", "decided_by": "human"}
POST /compute/dedup/resolve  {"dry_run": true}

  keep code 1  ← merged code 2 (completeness 4), code 3
  basis: kept by a person
```

規則被推翻，完整度最高的 code 2 反而成為被合併的一方。這是對的。

## 這次跑動修掉的兩個缺陷

**`created_at` 當不了決勝鍵。** 一次跑動的所有方向是在同一個 statement 裡插入的，
時間戳精確到微秒都一樣（七筆全是 `10:23:36.900265`）。原本的「同分取先寫的」在**正常情況下
完全沒有鑑別力**，存活者實際上是由字典迭代順序決定的。已改成再退到 `code` 與 `id`。

**人工覆寫分支到不了。** 它檢查的狀態是 `merge_decided_by = 'human'` 且
`merged_into IS NULL`，而**沒有任何端點能產生那個狀態**——用 `decided_by='human'` 跑
resolve 標記的是**敗方**，不是存活者。那是一段在守護「沒有人記得下來的決定」的死碼。
補了 `POST /compute/dedup/keep`，那也正是去重審閱介面 👁① 需要的原語。

## 跨語言重複（第二組測試資料）

專案 `c4e71649`，run `b8f3f102`，六筆，三組英文三組中文：

| code | 方向 | 意圖 |
|---|---|---|
| 1 | fine particulate matter × ischaemic stroke recurrence | 與 2 相同 |
| 2 | 細懸浮微粒 × 缺血性腦中風再發 | 與 1 相同，**零共同字詞** |
| 3 | obstructive sleep apnoea × white matter hyperintensities | 與 4 相同 |
| 4 | 阻塞性睡眠呼吸中止症 × 白質高訊號 | 與 3 相同 |
| 5 | 腸道菌相 × 認知功能恢復 | 中文，不重複 |
| 6 | statin therapy × post-stroke depression | 英文，不重複 |

**腳本完全看不到那兩組。** `score_range` 是 `[0, 0.064]`，全部低於 0.15 門檻，
而且真正重複的 1~2 與 3~4 **連候選配對都沒進**——腳本挑出的五組候選全是不相干的組合。
這正是詞彙相似度對跨語言的失效方式：分數不是「低」，是**排不進前五**。

**`Sweep The Whole List` 兩組都抓到了**，理由自己寫出了原因：

```
duplicate  1~2  "These are the same question regarding PM2.5 exposure and stroke
                 recurrence in elderly patients, translated between English and Chinese."
duplicate  3~4  "These are the same question regarding the link between sleep apnea
                 severity and white matter hyperintensities, translated between
                 English and Chinese."
```

不重複的都保持 distinct，包含只有中文的第 5 筆。合併之後英文留下、中文被併
（完整度相同，靠 `code` 決勝）。

**這是 `Sweep The Whole List` 存在的唯一理由，而它成立了。** 沒有這一步，
一份中英混寫的方向清單會把每一組翻譯重複都留在場上。

## 仍未驗證

- 真實跑動裡重複率有多高。這兩組都是刻意造的，不能推論。
- 中文**與中文之間**的近似重複（不是翻譯，是換句話說）。這次的中文彼此都是不同題目。
