# 第 0 步：五個畫面的欄位 vs API 實際回傳

**做法**：把 pen.dev 五個畫面上顯示的每一個欄位，逐一對到 `main.py` 的端點與
`lib/` 的實作、再對到 `schema.sql` / migration 的欄位。
**沒有跑任何東西，零成本。**

## 一句話結論

**資料層大致夠用，但有 11 個地方對不上，其中 3 個會讓畫面根本畫不出來。**
最嚴重的不是缺欄位，是**有兩塊內容根本沒有被存下來**——
它們只存在 n8n 的執行輸出裡，重新整理就消失。

---

## 🔴 會讓畫面畫不出來的（3 個）

### ✅ G1 / G2 / G8 —（**2026-09-07 已修**，migration 018）

`report` 加了三欄：**`caveats`**（jsonb）、**`acquisition`**（jsonb）、
**`novelty_verdict`**（text）。

**關鍵決定：三者都在 `save_report` 內從資料庫算出來，不接受呼叫端傳入。**
理由跟辯論的終止判定一樣——呼叫端手上拿的是模型對自己極限的說法，
而那正是模型最不該回答的問題。**所以 W9 不用改**，欄位會自動填。

`caveats` 四項，每一項都同時給數字與後果：

| 鍵 | 內容 |
|---|---|
| `fulltext` | 拿到全文的篇數／總篇數 ＋ 缺口句只存在 Discussion 這件事 |
| `novelty_unverified` | 沒驗過的方向數／已分級的方向數（**兩個數字，不是百分比**）|
| `excluded_as_already_done` | 被判已做過而排除的方向，**點名不只計數** |
| `debate` | 輪數、漂移、未解決反對、終止原因 |

`acquisition` 與 `novelty_verdict` 都是**抄寫而非參照**，
理由跟 `tier`／`rank` 一樣：分級和新穎性檢查都可以重跑，
參照出來的值會安靜地開始跟報告內文打架，而不會有任何東西報錯。

`tests/test_report_caveats.py` 離線釘住 **31 項**，包含三個退化情況：
沒採集、沒分級、沒辯論時要**降級成量得到的項目，而不是產生垃圾或消失**。

以下是原始的問題紀錄：

### G1（原始）— 報告的「這份沒有涵蓋什麼」沒有任何資料來源

**畫面 ⑤**，規格把它列為 **必要區塊、不可摺疊**。四項內容：
全文取得率、幾個方向沒驗過新穎性、幾個因為被判已做過而被排除（要點名）、
辯論輪數與未解決反對。

`report` 表只有：`sections`(8 節)、`citations`、`dropped`、`tier`、`rank`、
`model`、`created_at`。**四項全部不在裡面。**

前三項可以從 `harvest` / `novelty_check` / `debate_round` 拼回來（三次額外呼叫），
但**「被排除的是哪幾個」只有 W9 當下知道**——它算在守門輸出裡，而守門輸出
**沒有被存進資料庫**（`health_metric` 只能存 `numeric`，存不了清單）。

> **建議：`report` 加一個 `caveats jsonb`，W9 產報告時一起寫入。**
> 這是唯一誠實的做法。事後重算會漏掉「當時排除了誰」，而那正是規格
> 特別要求要點名的一項——安靜地少寫一份報告，在輸出上跟「這個方向不存在」
> 長得一模一樣。

### G2 — 報告的取得清單（不經模型那份）同樣沒被存下來

**畫面 ⑤ 第 06 節**，旁邊還掛著藥丸「直接從資料庫產生，不經模型」。
HANDOFF 寫它在守門輸出的 `data_to_acquire`——**同樣沒進資料庫**。

可以從 `/compute/feasibility` 的 `missing` / `route_to_tier_a` 重新拉，
但那樣它就不再是「報告產出當下的那一份」，而 `report` 表刻意把 `tier` 和
`rank` **抄寫而非參照**，理由正是這個。

> **建議：跟 G1 一起，寫進同一個 `caveats` 或另一個 `acquisition jsonb`。**

### ✅ G3 — 專案列表判斷不出「等你放行」（**2026-09-07 已修**）

`list_projects` 現在一起回傳 `usd_budget` / `usd_spent` / `usd_remaining`、
`chain_state`、`parked`、`n_stages_done`，外層還有 `n_awaiting_you`。
**兩次查詢做完全部，沒有 N+1。**

`chain_state` 七態：`not_started` / `running` / `awaiting_you` / `done` /
`failed` / `stopped` / `idle`。三個刻意的分辨：

- **`stopped` 不等於 `failed`**——刻意結束的鏈不該看起來像壞掉的
- **`parked.awaiting` 分 `review` 與 `precondition`**——兩種列都叫
  `awaiting_review` 但意思相反（跑完停在審閱點 vs 前置條件不足根本沒跑）。
  「按放行」和「去上傳資料」不是同一個請求
- **`chain_state` 不等於 `project.status`**，兩個分開回傳

規則寫在 `db._chain_state_of`（純函式），
`tests/test_projects_list.py` 離線釘住 17 項。

以下是原始的問題紀錄：

### G3（原始）— 專案列表判斷不出「等你放行」

**畫面 ① 狀態 2**，而「等你放行」是這一頁存在的**主要理由**。

`list_projects` 回傳：`id / title / topic / status / created_at /
n_runs / n_papers / n_ideas`。

- **沒有費用** → 畫面上那一欄要另外打 `/compute/run/budget`
- **`p.status` 不是畫面需要的五態**。要知道有沒有停在審閱點，
  得對每一個專案打一次 `/compute/chain/state`（看 `parked`）

**等於 N+1 次呼叫才畫得出一張列表。**

> **建議：把 `parked` 與 `spent` 併進 `list_projects` 的查詢。**
> 一次查詢就做得到，不用改結構。

---

## 🟡 對不上、要選一邊改的（4 個）

### G4 — 「去路」的五欄，資料庫只有一個自由文字欄

**畫面 ③ 的 C 級表格** 我畫了五欄：
`缺什麼／去哪裡拿／怎麼拿／多久／多少錢`。

實際欄位只有兩個：

| 欄位 | 型別 | 對到畫面 |
|---|---|---|
| `missing` | `jsonb`（字串陣列） | 缺什麼 ✅ |
| `route_to_tier_a` | `text` 一段散文 | **去哪裡拿＋怎麼拿＋多久＋多少錢 全部擠在這裡** |

W9 的提示詞**有**要求逐項寫五個欄位，但那是寫進 `sections.feasibility` 的
散文，不是結構化欄位。

> **建議：短期改設計**——`缺什麼`（清單）＋ `去路`（一段散文），
> 跟資料庫一致。**中期再考慮把 `route_to_tier_a` 結構化**，
> 因為散文會靜默漏欄，而規格說 C 級唯一有用的資訊就是去路。
> 先讓系統能跑，不要為了一個表格先改 W6 提示詞＋migration＋守門。

### ✅ G5 / G10 / G11 —（**2026-09-07 已修**）

新增 **`GET /compute/progress?project_id=`**（`lib/progress.py`），
一次回傳**十列**（鏈開始前的四步 ＋ 鏈自己的六段）、每一段的產出數字、
費用、`chain_state` / `parked`、以及**最新一場錦標賽的 id**（解 G11）。
錦標賽那一列同時給 `n_undecided`（解 G10）——未判決的對局是被計數的，
不是被藏起來。

**兩樣東西刻意不做**，因為後端給不出來：

| 設計上有 | 為什麼拿掉 |
|---|---|
| 階段內進度（「15 個方向中的 11 個」） | 階段派工到 n8n 裡跑，**只在結束時回報一次**。中途的分數是捏的，而且它會動，看起來像真的 |
| 精確 ETA（「還要 25 分鐘」） | **沒有量測基礎**。時間隨文獻量與模型排隊變動，整條鏈只完整跑過個位數次 |

改成 `eta_note`：「整條鏈通常 30–60 分鐘…系統不會估算剩餘時間——
沒有量測基礎的數字比沒有數字更糟。」

**設計稿與兩份前端文件都已經跟著改。**
`tests/test_progress.py` 釘住 30 項，其中有一項是**檢查那些欄位不存在**：
`eta` / `percent` / `progress` / `fraction` 這類欄名一個都不准出現。

以下是原始的問題紀錄：

### G5（原始）— 進行中畫面的每段產出數字，`chain/state` 都沒有

**畫面 ① 狀態 3** 一列一階段，右邊顯示
`10 個查詢 · 200 篇論文`、`全文 69 / 200`、`已生 15 個方向中的 11 個`。

`chain.state()` 每一段只回傳：`stage / label / review / status / run_id /
error / finished_at`。**沒有任何產出數字。**

而且 **`STAGE_PLAN` 只有六段**（dedup → tournament → feasibility → novelty →
debate → report），畫面上那十列裡的 **W2 / 採集 / W1 / W3 都不在鏈裡**，
它們是鏈開始之前跑的。

另外兩個畫面上有、系統裡沒有的：
- **「已生 15 個方向中的 11 個」** ——階段內的即時進度，後端只知道狀態不知道進度
- **「大約還要 25 分鐘」** ——沒有任何 ETA 來源

> **建議：新增 `GET /compute/progress?project_id=`**，
> 把鏈前四段與鏈內六段拼成一張表、各自帶產出數字。
> **階段內進度與 ETA 直接從設計拿掉**——做不到的東西畫在上面
> 只會變成謊話。ETA 可以改成「通常 30–60 分鐘」這種不假裝精確的說法。

### G6 — 辯論的門檻與輪數上限沒有回傳

**畫面 ④ 的終止摘要**寫 `漂移 0.62　門檻 0.50` 和 `輪數 2 / 3`。

`get_debate` 回傳 `drift_from_original` ✅ 和 `n_rounds` ✅，
但 **門檻（0.5）和上限（max_rounds）都沒回傳**。門檻寫死在程式裡，
上限在鏈的 params 裡。

> **建議：`get_debate` 一起回傳 `drift_threshold` 與 `max_rounds`。**
> 前端寫死門檻是最糟的做法——那是政策值，改了兩邊會不一致而且看不出來。

### G7 — 沒有「這個專案辯了哪些方向」的端點

**畫面 ④ 有 N 個分頁**，一個被辯論的方向一個。
`/compute/debate` 和 `/compute/debate/state` **都只吃單一 `idea_id`**。
前端無從知道要開哪幾個分頁。

規格還特別要求：**分頁數必須等於實際被辯論的方向數，有方向被跳過要點名**
——那正是 W8 巢狀迴圈那個無聲失效的守門。

> **建議：`GET /compute/debate?project_id=` 回傳該專案所有辯過的方向摘要。**

---

## 🟢 小缺口（4 個）

| # | 缺什麼 | 影響 | 建議 |
|---|---|---|---|
| G8 | **新穎性判決不在 `report` 表** | ⑤ 頂部的判決藥丸要另外打 `/compute/ideas` 或 `/compute/novelty` | 可接受，多一次呼叫；或跟 G1 一起抄寫進報告 |
| G9 | **`health_metric` 沒有讀取端點** | ③ 證據區的**順序翻轉率**畫不出來（`get_tournament` 沒回傳它） | 加 `GET /compute/health?run_id=` |
| G10 | **未判決對局數沒回傳** | ③ 證據區寫「3 場未判決、不猜」——`get_tournament` 沒有這個數字 | 併進 `get_tournament` |
| G11 | **沒有「該專案最新一場錦標賽」的端點** | 前端拿不到 `tournament_id` 就打不了 `/compute/tournament/{id}` | 併進 G5 的 `/compute/progress`，或加 `?project_id=` |

---

## ⚪ 設計沒用到的既有資料（1 個，反方向）

### G12 — 畫面 ④ 浪費了 `objection` 表裡三個欄位

資料庫存了、畫面沒顯示：

| 欄位 | 允許值 | 畫面現況 |
|---|---|---|
| `severity` | `major` / `minor` | 沒顯示 |
| `axis` | `contribution` / `novelty` / `soundness` / `feasibility` | 沒顯示 |
| `citation_support` | `strong` / `weak` / `irrelevant` | 沒顯示 |
| `status` | `resolved_by_evidence` / `resolved_by_revision` / **`unresolved`** | **只畫了「未解決」一種** |

`status` 三態只畫一態是實際的缺陷——`resolved_by_evidence` 還有一條
資料庫層的規則（`rebuttal_score >= 4` 才准讓步），畫面上完全看不到。

> **建議：④ 的每個反對加上 `axis` 小標籤與三態的 `status`。**
> 這是免費的——資料已經在了。

---

## 兩個確認不存在的端點

| 需求 | 規格怎麼說 | 現況 |
|---|---|---|
| 報告匯出 PDF / Markdown | 「**下載是明確需求，不是加分項**」 | `main.py` 裡 `pdf` / `markdown` / `export` **零匹配** |
| 欄位清單範本下載 | 面板底部的 CSV 下載 | `tools/inventory_template.csv` 在 repo，**沒有端點送出去** |

---

## 建議的修法順序

**先做這三個，它們是「畫不出來」而不是「畫得醜」：**

1. ~~**`report` 加 `caveats` + `acquisition`**~~ — **✅ 2026-09-07 做完**
   （加了三欄，而且**在 API 端算、W9 不用改**）
2. ~~**`list_projects` 併入 `parked` 與 `spent`**~~ — **✅ 2026-09-07 做完**
3. ~~**新增 `GET /compute/progress?project_id=`**~~ — **✅ 2026-09-07 做完**
   （順手解掉 G10 的未判決對局數）

**三件都做完了。剩下的是四個小的（G4、G6、G7、G9）與兩個缺的端點。**

實際的施作順序是 **2 → 1 → 3**：第 2 件只改一個查詢、當場可驗；
第 1 件要動 migration 再改 W9 寫入；第 3 件最大，而且要先決定
**哪些欄位要從設計上拿掉**（階段內進度與精確 ETA 後端給不出來）。

**再做這三個小的：**

4. `get_debate` 回傳門檻與上限（G6）＋ 支援 `project_id`（G7）
5. `get_tournament` 併入翻轉率與未判決數（G9、G10）
6. 補兩個端點：報告匯出、範本下載

**設計端要改的：**

7. ③ 的 C 級表格從五欄改成「缺什麼＋去路」兩欄（G4）
8. ① 進行中拿掉階段內進度與精確 ETA（G5）
9. ④ 加上 `axis` 標籤與三態 `status`（G12）

**做完 1–6，前端規格第 7 節的 15 項能力才真的全部有對應。**
在那之前不要開始寫 n8n webhook——包一層在缺資料的端點外面，
只會讓缺口更難看見。
