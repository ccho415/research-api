# 交接文件 — 研究方向發想系統

**寫給：接手這個專案的任何一個新的 Claude Code 工作階段。**
最後更新：2026-09-09（**批次 2「進度回報」做完並部署；W5B 的守門結果第一次存得下來**）

## ✅ 2026-09-09 完成：批次 2 — 進度回報

會做這件事，是因為 W5B 在 Anthropic 的批次佇列裡卡了 **3 小時 40 分**，
而「還在跑」跟「已經死了」在畫面上長得一模一樣。使用者要的是三件事：
看得出還活著、看得出守門結果、**看得出取消划不划算**。

| 東西 | 在哪裡 | 狀態 |
|---|---|---|
| `run.reported_at` / `run.report` 兩欄 | migration `019` | 已套用 |
| `POST /compute/stage/report` | `main.py` → `chain.record_report` | 已部署（85 條路由） |
| `progress` 每一段帶回 `reported_at` / `report` | `lib/progress.py` | 已部署 |
| W5B 每輪回報批次進度 | `Say Where The Batch Is` | 已發布 |
| W5B 守門存成最終回報 | `Save The Gates` | 已發布 |
| 前端把回報畫出來 | `frontend/index.html` `reportBlock()` | 做完 |

**`report` 刻意不定 schema。** 每一段能報的東西本來就不一樣——批次報幾個請求
跑完、檢索報幾個查詢做完、辯論報跑到第幾輪。硬定一個共同格式，等於逼每一段
都只報它們交集裡最沒用的那個欄位。前端因此寫成：認得的欄位翻成中文，
**認不得的照原樣印出來**，以後加的階段不會因為沒人回來改前端就變成空白。

**「取消划不划算」是從 `request_counts.succeeded` 算的**，不是從工作流那句英文
`billing_note` 照抄——那句是給 LINE 訊息用的。已完成的請求已經計費，取消只省得下
還沒跑的部分；一個都沒完成就取消不花錢。

**守門的英文名字與理由在前端有對照表**（`GATE_ZH` / `GATE_NOTE_ZH`）。
翻譯放前端不放工作流，是因為工作流裡那些字串是 `pass` 判斷的依據，
不能因為翻譯而移動；對不上的就退回英文原文顯示。

測試專案 `82ffbcec` 的錦標賽守門已經**補寫回去**（`backfilled: true`），
`order_flip_rate: 0.23`、`all_gates_pass: false`、`cost_usd: 1.105`——
這是第一次這些數字存得下來，之前每跑一次都算、推去 LINE、然後消失。

### 還沒做

- **批次 4**：檢索詞分「一定要包含」與「可有可無」，
  動到 `/compute/search/expand`、W2、W3 與畫面 ②。
- **守門「偵測到但擋不住」**：`all_gates_pass: false` 的那一次，
  `Tell The Chain` 照樣回報 done 並排了 W6。勾選功能做完之後這件事的急迫性降低了
  （人本來就會在 ③ 看到守門結果再決定放行誰），但守門本身仍然不會擋。

## ✅ 2026-09-09 完成：審閱點 ③ 可以勾選要放行的方向

原本 ③ 只有一顆「放行」，然後 W7/W8/W9 各自回頭按 `tiers` + `max_ideas`
取排名前幾名。**人讀完分級板的判斷沒有地方可以進來**——而那正是審閱點的用意。

| 改哪裡 | 改什麼 |
|---|---|
| `frontend/index.html` `paintTiers` | 每個方向一個勾選框，加三顆批次勾選鈕 |
| `frontend/index.html` `releaseBlock` | 收一個 `Set`，回傳 `{node, sync}`；送 `params.idea_ids` |
| W7 `Novelty Request`／`Pick The Directions` | 收 `idea_ids`，有勾選時照 id 選 |
| W8 `Debate Request`／`Pick The Directions` | 同上 |
| W9 `Report Request`／`Pick The Directions` | 同上，但新穎性分層不受影響 |

**管路本來就通，不用改後端。** `chain.resume(params)` 會把 params 併進交棒
（merge 不是取代，所以送 `idea_ids` 不會蓋掉 W6 算出來的 `tiers`），
W-API 的 `release` 早就帶 `body.params`。`idea_ids` 走每一支的 `incoming`
一路往下傳，所以**在 ③ 勾一次，W8 和 W9 都算數**。

### 三個刻意的決定

1. **一開始一個都不勾。** 預先勾好的板子收到的是「按了放行」，不是一個決定。
2. **勾選蓋過 `tiers`。** C 級方向可能比 A 級值錢——這也是分級板從不按 tier
   重排的同一個理由。勾了卻不在分級板上的 id 直接擋掉，不默默少跑。
3. **錢寫在按鈕旁邊。** 每個方向往下跑約 $0.53（W7 $0.06 + W8 $0.40 + W9 $0.07）。
   預算護欄是在你決定**之後**才擋，那時候它已經不是資訊了。

### ⚠️ 動 idea_ids 就一定要動 max_ideas

三支的 `May We Afford This` 都**跑在讀分級板之前**，用 `max_ideas` 估預算
（W7：`0.061 × max_ideas`；W8：`0.04 × max_rounds × max_ideas`；W9：`0.07 × max_ideas`）。
勾六個而 `max_ideas` 留在預設 2 → **照兩個估、跑六個，護欄回報通過，超支要到帳單才看得見**。
所以正規化節點把 `max_ideas` 設成勾選數量。**以後任何會改變實際跑幾個方向的參數，
都要在正規化節點就把 `max_ideas` 對齊。**

W9 有一個差別：勾選只縮小候選範圍，**新穎性分層原封不動**。報告第 5 節就是
新穎性判決，被勾選但沒驗過新穎性的方向照樣寫不出報告——那是缺少輸入，
不是偏好，勾再多次也生不出判決。

順帶修掉：`release` 現在會看回應的 `resumed: false` 並照實回報。
原本不管後端說什麼都報「放行了」，一條沒有重啟的鏈會就這樣被晾著。

## ✅ 2026-09-09 完成：資料清單移到分級之前

**這是一個真的錯，不是版面問題。** W6 拿使用者手上的欄位去判每個方向做不做得到，
所以清單必須在 W6 跑之前存在。但上傳面板只出現在畫面 ③（分級），
而 `feasibility` 的 `pause_after=True` 意思是**跑完才停**——
唯一問清單的畫面，正好是給了也不會改變任何事的那一個。

順帶修掉兩處註解與程式碼對不上的地方，**接手的人不要再相信舊註解**：

| 舊註解說 | 實際上 |
|---|---|
| 「鏈停在 W6 之前等這份清單」 | 沒有。`chain.missing_precondition` 明確 `return None`，理由寫在它的 docstring 裡：W6 現在改問「要做到需要什麼」而不是丟例外 |
| 「直接繼續會讓 W6 改判」 | 在 ③ 說這句時 W6 早就判完了 |

`uploadPanel(pid, onDone, mode)` 現在有三個 mode，因為同一個上傳在三個時間點
的價值不一樣：`stage`（畫面 ②，還沒有專案，存 sessionStorage，
`flushStagedInv()` 在專案建立後立刻送出）、`before`（進度頁，W6 還沒輪到）、
`after`（畫面 ③，存得下來但不會重判，面板直說）。
`release` 只在 `after` 呼叫——另外兩處的鏈根本沒停，呼叫它等於推進使用者沒要求推進的鏈。

**還沒做**：③ 上傳新清單之後沒有「重跑 W6」的按鈕。
`chain/start` 會花錢，刻意不在前端白名單裡，目前要用 n8n 或 curl 打
（`stage: "feasibility"`）。要不要放進前端是個獨立決定。

## ⚠️ 用 MCP 改既有節點的 notes：只有一條路（2026-09-09 實測）

改 W-API `Write To The API` 的備註時踩到的：

- **`setNodeParameter` 只會寫進 `parameters`。** 傳 `path: "/notes"` 的結果是在
  HTTP Request 上長出一個不存在的 `parameters.notes` 參數，**真正的 `node.notes`
  一動也沒動**，而且工具回報 `appliedOperations: 1`、零警告——
  完全看不出做錯了。這是靜默失效。
- `update_workflow` 的操作清單裡沒有專門改 notes 的操作；
  `setNodeSettings` 只吃 onError／retry／executeOnce 那一組。
  **只有 `addNode` 的輸入結構收得下 `notes`。**

**唯一可行的做法：`removeNode` + `addNode` 重建，同一批操作送出（原子性的）。**
`id`、`position`、`typeVersion`、`parameters`、`credentials` 逐字照抄，
然後把每一條進出的連線 `addConnection` 接回去——`removeNode` 會把連線一起帶走。

兩個要注意的地方：

1. 回應會附一句 `HTTP Request nodes were skipped during credential auto-assignment`。
   **那句話會誤導**：只要 `addNode` 裡明確給了 `credentials`，憑證是有進去的
   （已逐欄比對確認）。那句講的是自動指派，不是你手動給的那份。
2. `addNode` 有丟欄位的前科（會吃掉 `executeOnce`），所以重建前先確認
   那個節點有沒有設 `executeOnce`／`onError`／`alwaysOutputData`／`retryOnFail`。
   有的話要一併確認有沒有被帶過去。

已完成並發布（`9015bf2d`）。發布後兩個 method 都測過，各回 403（驗證擋下），
不是 404 或 500——代表 webhook 兩條路都還活著。

## 🔧 怎麼從 MCP 問「這條路由上線了沒」（2026-09-09 實測）

**research-api 只在 Zeabur 內網**（`research-api.zeabur.internal:8080`）。
公開網域 `ccho415-research.zeabur.app` 是 **n8n**，不是 API——
所以從外面 curl `/admin/config` 一定 404，那不是部署失敗的證據。

**W-ADMIN（`3kLQ9JvEdLBYnsWe`）從 MCP 叫不動**：它的表單觸發節點上有
pinned data `{}`，會蓋掉 `execute_workflow` 傳進去的 `inputData`，
所以每次都在問一個空路徑、每次都回 404。`update_workflow` 沒有清 pin data 的操作。

**可行的做法**：暫時把 **W0 連線測試**（`LnIml88jxxjU5gSV`）的
`Check API Health` 節點 URL 指到要問的路徑，`manual` 執行，讀完改回 `/healthz`。
那支是停用的診斷工作流，觸發節點沒有 pin data。

**連憑證都不用**：FastAPI 先路由、再驗金鑰，所以
**404 = 路由不存在，401／403 = 路由存在但沒帶金鑰**。這就足以判斷部署。

同一次執行裡 W0 還會打 `/compute/search/vocab` 與 `/compute/search/query`
（帶 `Research API Key`），可以當對照組——它們正常而目標路由 404，
就確定是「服務活著但新路由沒上線」，不是服務掛了。

## 📅 文獻年份切點：只有 W3 有，其他都沒有（2026-09-10 查證）

被問到「發想、錦標賽、辯論分別用哪一年當切點」，追過一遍程式碼的結果：

| 階段 | 切點 | 出處 |
|---|---|---|
| W2 文獻檢索 | **無，全年份** | `Run One Search` 不帶 `year_from`／`year_to` |
| **W3 方向發想** | **當年** | W-START 傳 `cutoff: new Date().getFullYear()` |
| W7 新穎性 | **無，全年份** | `novelty.py` 的十四輪檢索不帶年份 |
| W5B 錦標賽 | **無** | 不檢索文獻，只比較兩個方向的文字 |
| W8 辯論 | **無** | 引用池就是 W7 撈回來的論文（`debate._evidence_pool`）|

W3 的切點只用在 `verify.verify`：把命中數切成 `papers_before`（≤ cutoff）與
`papers_after`（> cutoff），判決依序是
`ALREADY DONE` → `PURSUED SINCE` → `STILL OPEN`。

**已知的後果，不是缺陷**：切點是當年，所以 `papers_after` 幾乎恆為 0，
`PURSUED SINCE` 這個判決在正常使用下**永遠不會出現**，三檔實質剩兩檔。
那一檔是為另一種情境設計的——拿一個 2015 年提出的想法問「當年新、之後有沒有
人做」。實際專案問的是「到今天為止有沒有人做過」，當年切點才是對的。

**W3 有一個刻意不發布的草稿**（`49a71ac1`「清掉表單裡的肺腺癌預設值」）。
它要移除表單欄位殘留的 `topic = lung adenocarcinoma 2013-2015 gap harvest`
與 `cutoff = 2015`。已發布版本仍然預填這兩個，但**只影響手動開 W3 表單那條路**，
前端那條一律明確帶當年。使用者 2026-09-10 表示不再用表單，所以不發布。
**看到 W3 的 versionId ≠ activeVersionId 不用再查一次，就是這一筆。**

## ⏭️ 明天第一件事

測試專案 `82ffbcec-20fc-4377-b1a1-01f5dff6061f`
（雙抗血小板藥物 · 已花 $0.0394 / $2.00）**停在 W4 之前，方向 15 個都在**。
缺陷已修好，續跑只要一行：

```
POST /compute/chain/start
{ "project_id": "82ffbcec-20fc-4377-b1a1-01f5dff6061f",
  "stage": "dedup",
  "params": { "run_id": "8c17853c-0ae6-4519-b241-8eabda0e183a" } }
```

`run_id` 是**方向所屬的那個 run**，不是文獻檢索那個——理由見下面。
`chain/start` 刻意沒有放進前端白名單（它會花錢），要用 n8n 或 curl 打。

> **先讀完這一份再動手。** 上一個工作階段沒讀，結果重新踩了一次「thinking token
> 算在 maxOutputTokens 裡」——那條在本文件的環境備忘裡本來就寫著。

## ⏭️ 下次開機從這裡接

**W1–W10 全部建好了**，**預算護欄十個都接完了**，
**階段自動接續也建好、驗過、啟用了**——PRD 三個貫穿機制到齊（2026-09-02）。

migration 017 已套用，鏈的控制流程整條走過一遍（零成本，沒叫任何模型），
W-CHAIN `UJiYf5NJRM0uVXew` **已啟用**，每十分鐘掃一次待辦。

**後端到此為止該驗的都驗過了。2026-09-05 起工作重心是前端**——見下一節。

---

## 🔴 開機第一件事：LINE 掛了，整個系統目前是靜音的

**W-LINE 通知測試（`5hjjy6sjMPBJaHGg`）的判決**：

```
token_ok: false   bot_name: null   push_status: 401
verdict: "TOKEN BAD - the credential is wrong.
          Check the Value field starts with \"Bearer \" and a space."
```

兩個端點（`/v2/bot/info` 與 `/v2/bot/message/push`）都回 401，LINE 說的是
**`Authorization header required`**——代表它**根本沒收到合法的標頭**，
不是收到一個過期的 token。

**要修的地方**：n8n → Credentials → **LINE Messaging API**
（`dAytbkY0WTl24Yjm`，型別 `httpHeaderAuth`）

| 欄位 | 應該是 |
|---|---|
| Name | `Authorization` |
| Value | `Bearer ` ＋ channel access token（**`Bearer` 後面有一個空格**）|

最常見的錯法就是 Value 只貼了 token、少了前綴——症狀正好是
「header required」而不是「invalid token」。

**為什麼這件事排第一**：**W-ALERT 失敗告警走的是同一把憑證。**
所以現在任何工作流在 production 失敗，你都不會收到通知；W10 就算抓到
「被搶先」也推不出去。**這比單一功能壞掉嚴重，因為它讓其他所有失敗
都變得看不見**——正是這個專案一直在防的那種「少掉的那一半在輸出上看不出來」。

08-30 憑證外洩處理時 W-LINE 測試（執行 47）是通過的，所以是**那之後才壞的**，
或者換憑證時 `Bearer ` 前綴掉了而當時沒重測。

> **🔴 修之前先讀這一段。** 建 `W-START` 時 n8n **自動把這把 LINE 憑證綁到了
> webhook 的入站驗證上**（它是唯一一把 `httpHeaderAuth`）。所以現在
> 「前端要送什麼標頭才進得來」跟「LINE 要收什麼標頭」是同一個值——
> **你一改 LINE 的 Value，前端的鑰匙就跟著變**。
> 正確做法：另外建一把 `httpHeaderAuth` 叫 `Frontend Webhook Token`
> （Name 自訂如 `X-Frontend-Key`，Value 隨機字串），
> 換到 `W-START` 的 `Frontend Calls` 節點上，**再去改 LINE 那把**。

**修好之後**：重跑 W-LINE 測試確認，然後補跑一次 W10——今天那次的花費
因為執行中斷沒被記錄（見下）。

---

## 🔧 前端接線第一天（2026-09-08）

**做這一段的判準**：使用者要「能實際從前端操作、順利跑到報告下載」的成品，
細節之後再修——**只要不影響實際運行**。所以下面每一項都是「不做就跑不起來」，
不是「做了比較好」。

### 三個發布，其中一個是修好的東西沒按下去

| 工作流 | 之前 | 現在 |
|---|---|---|
| **W-CHAIN** | 已發布版本仍是舊的，`Spread The Claims` 送 `run_id` | 發布了草稿裡的 `chain_run_id` 改名 |
| **W1 領域框架** | `activeVersionId: null`，**從來沒發布過** | 已發布並啟用 |
| **W3 缺口組合推理** | 同上，而且名字還叫 `W3-TEST` | 已改名、已發布並啟用 |

**W-CHAIN 那個要特別記**：修正在草稿裡躺了六天沒發布。已發布版本會讓
`params.run_id`（研究跑動）和頂層 `run_id`（鏈的記帳列）撞名，正規化器挑外層，
**W4 會去查一個沒有方向的列、去重零筆、然後回報成功**。
草稿的版本說明是自己寫的，內容完全正確——只是沒按發布。

> **教訓：`versionId !== activeVersionId` 要當成待辦看，不是當成「有草稿」看。**
> 檢查方式：`get_workflow_details` 比對這兩個欄位。
> `autosaved: true` 且沒有名稱的是編輯器自動存的（開過就會有），可以忽略；
> **`autosaved: false` 且有標題的是真的改動，沒發布就是沒生效。**

### 一條過期的筆記：交棒穿透其實早就修完了

本文件原本寫著「W4／W5B／W6／W9 還沒改」。**版本紀錄顯示 09-05 09:46
一口氣發布了三個**，說明裡寫「補完六段一致」：

- W4「交棒時保留收到的參數，不要只挑自己用得到的」
- W5B「交棒時保留收到的參數」
- W6「交棒時保留收到的參數」

W9 沒有這一條，但 W9 是最後一段、沒有下游可以交棒，位置上不會出事。
**這件事整條劃掉。**

### W1／W3 為什麼不能只按發布

兩個都**只有表單觸發器**，而且 `Route With Sonnet`／`Build The Frame`／
`Record The Spend`（W1）與 `Load The Harvest`／`Check Against The Record`／
`Save The Directions`／`Record The Spend`（W3）**直接引用表單節點**。

**引用一個沒有觸發的節點會拋錯**，所以那些引用讓這兩個工作流
只能從表單啟動——不試就看不出來。照 W4 的形狀補上：
`executeWorkflowTrigger` 與表單各自接進一個 `Form Or Caller` 正規化節點，
**下游一律讀正規化節點，不准讀觸發器**。`params` 優先於外層扁平欄位。

順手修掉 W3 的一個硬編碼：四處 `Number(...) || 2015` 是肺腺癌那次驗證留下的。
換題目而呼叫端忘了帶 `cutoff`，新穎性會**安靜地以 2015 為界**，結果看起來完全正常。
現在正規化節點驗不過就拋錯，**沒有預設值是刻意的**。表單的預設值也一併清掉。

### W2：畫面 ② 本來就存在，它是工作流中間的一個表單頁

`Confirm Concepts` 這個 `n8n-nodes-base.form` 節點就是「確認檢索概念」那一頁，
夾在 `Split Topic Into Concepts` 和 `Normalise Input` 之間。
**前端要自己做那一頁，就得從中間切開。**

做法（**表單那條路一個節點都沒刪**，手動跑體驗完全不變）：

```
                    ┌─ Literature Search Request（表單，原封不動）
Split Topic ← ──────┤
                    └─ Called By The Frontend → Read The Caller → Propose Or Search
                                                                    ├ propose → 上排
                                                                    └ search  → Normalise Input
```

兩種模式：

- **`propose`** — 只把題目拆成概念就回手。**不建專案、不建 run、不繼續花錢。**
  概念確認頁上的修改與重查因此是免費的，這是它會被真的使用而不是被點過去的前提。
- **`search`** — 收下已經被人改過的概念，直接建 run 開始檢索。

新增三個分岔節點：`Confirm Page Or Return`（表單進來的才看確認頁，
前端進來的碰到那個節點會停在一個沒有人會打開的網址）、
`Form Needs A Done Page`（`Search Started` 是表單完成頁，前端這條要繞過）、
`Propose Or Search`。`Build Confirm Form` 加了 `entered_via`，
用 try/catch 探測 `Read The Caller` 有沒有跑過。

順帶修掉同一類的舊問題：`Start Run` 直接引用表單觸發器拿預算上限，
**那一個引用就是讓 W2 後半段只能從表單啟動的原因**，改成從 `Normalise Input` 讀。

**前端這條路沒有表單頁 30 分鐘逾時的限制**——可以下班前交題目，隔天再確認概念。

### W-START 交題目（`ZqtKMxcuCNkFIRvf`）— 新建，已發布

前端面向的第一條 webhook：`POST /webhook/research/start`

```
Frontend Calls → What Was Asked → Propose Or Start
   ├ propose → Ask W2 For Concepts → Reply With Concepts
   └ search  → Create The Project → Reply With The Project ←── 先回應，再繼續
                 → Hand W2 The Concepts → Run The Literature Layer
                 → Hand W1 The Topic   → Judge The Domain Frame
                 → Start The Harvest → Wait 30s → Is The Harvest Done
                 → Ready Or Wait Again → Harvest Ready ─┬ 否 → 回去等
                                                        └ 是 → Combine Into Directions
                 → Put It On The Chain
```

幾個刻意的決定：

- **先建專案再回應瀏覽器。** `/compute/run/start` 會 adopt，所以先拿到
  `project_id` 立刻回給前端，後面二十到四十分鐘在背景跑。沒有瀏覽器會等那麼久。
- **W2 收到的是 `resume_run_id` 而不是 `run_id`。** run 已經建好了，
  要它接手而不是再開一個；而 `run_id` 在 W2 那邊會被讀成「別人的檢索要續跑」——
  跟 W-CHAIN 那個撞名是同一類。
- **採集用輪詢加計次上限**（40 輪 × 30 秒 = 20 分鐘就拋錯）。
  卡住的採集和很慢的採集**在畫面上長得一模一樣**，只有計次分得出來；
  無限迴圈會讓執行一直開著，看起來還很正常。
- **`Put It On The Chain` 一定要帶 `params.run_id`**，否則 W4 查到零筆回報成功。
- **W3 的 `cutoff` 用當年年份**，因為文獻是幾分鐘前才採集的，
  語料裡的東西都在那一年或之前。W3 不接受沒有 cutoff。

**實跑驗過（執行 1191／子執行 1192，成本一次 Gemini flash 呼叫）**：

```
題目：空氣中細懸浮微粒暴露與兒童氣喘發作的關聯
→ concepts: ["fine particulate matter", "asthma", "child"]
   nothing_created: true      4.5 秒
```

這一趟同時驗掉了 W2 的新入口、`Confirm Page Or Return` 有正確避開表單頁
（沒避開的話執行會掛在那裡等），以及回應節點。

**search 模式還沒實跑過**——那一趟會花約 $0.8–1.5、跑二十到四十分鐘，
要使用者點頭才跑。

### W-API 前端讀寫（`aH4K0fTV8l6Do59c`）— 新建，已發布

前端唯一的讀寫入口：`GET|POST /webhook/research/api/:route`

**白名單，不是通用轉發器。** `/admin/migrate`、`/admin/backup`、
`/admin/restore-drill` 跟這些端點住在同一個服務、同一把金鑰後面；
通用轉發等於把它們一起開給瀏覽器。

十六條路由，每一條都對應某個畫面實際會綁的欄位：

| 畫面 | route | 上游 |
|---|---|---|
| ① | `projects` / `runs` / `progress` / `chain-state` | 專案列表、跑動、十步進度、鏈狀態 |
| ② | `verify-terms`（POST） | `/compute/verify/terms`——**免費、不叫模型** |
| ③ | `feasibility` / `dataset` / `ideas` / `dedup` | 分級板、資料清單、方向、去重證據 |
| ④ | `debate` / `debate-state` / `novelty` | 摘要、辯論內文、新穎性判決 |
| ⑤ | `report` / `watch` / `report-export` | 報告、撞題監看、下載 |
| ③④ | `release`（POST） | `/compute/chain/resume`——**唯一會讓鏈前進、因而會花錢的路由** |

三個刻意的決定：

- **上游的 HTTP 狀態碼原樣傳回。** `neverError` 開著，400／404 以資料的形式
  抵達 `Shape The Reply`。沒有這個的話「API 說不行」和「伺服器掛了」
  在瀏覽器看起來一模一樣，而只有其中一種是 bug。
- **路由寫錯回 400，不是讓執行死掉。** 這是實測抓到的：`Which Route` 拋錯
  會讓執行死在回應節點之前，n8n 交給瀏覽器一個通用 500——又是同一個
  「兩種失敗長得一樣」的問題。改成自己接住並附上已知路由清單。
- **報告匯出走獨立分支**（Switch 第三個出口 → `responseFormat: file`），
  因為 PDF 是二進位，跟 JSON 共用一條路會壞。

> **🔴 `multipleMethods` 的坑（實跑抓到的）**
> 開啟 `multipleMethods` 之後，**webhook 節點每個方法各給一個輸出**：
> 輸出 0 是 GET、輸出 1 是 POST。**兩個都要接到下游。**
>
> 只接輸出 0 的症狀是最難查的那一種：POST 進來，`Frontend Calls` 亮綠燈、
> 執行狀態 `success`、HTTP 回 200——**但回應是空的，下游一個節點都沒跑**。
> 沒有錯誤訊息，執行紀錄看起來完全正常。
> 唯一看得出來的地方是 `lastNodeExecuted` 停在觸發器自己身上。
>
> `verify-terms` 和 `release` 都是 POST，所以這條沒接的話，
> **畫面 ② 和兩個放行鈕會全部靜默無回應**。

### 正確的 webhook 網址

`W-API` 的路徑帶了 `:route` 參數，**n8n 因此會在網址裡插一段 UUID**：

```
W-API    https://ccho415-research.zeabur.app/webhook/5165edde-989c-4cc2-a500-f5915745ef67/research/api/<route>
W-START  https://ccho415-research.zeabur.app/webhook/research/start
```

驗證用的標頭：`X-Frontend-Key`，憑證是 `Frontend Webhook Token`
（`Kh0DkIvuT0Yh1oZJ`）。**兩條 webhook 共用同一把。**

### 實測回來的欄位（前端只能綁這些）

**畫面 ①** `projects` → `id, title, topic, status, created_at, usd_budget,
usd_spent, usd_remaining, n_runs, n_papers, n_ideas, chain_state,
parked{stage,label,review_point,status,awaiting}, n_stages_done, n_stages`
＋頂層 `n, n_awaiting_you`

**畫面 ③** `feasibility` → 頂層 `n, counts{A,B,C,D},
doable_now[], needs_acquisition[], parked[], assessments[]`；
每筆 `id, idea_id, dataset_id, tier, missing[], route_to_tier_a, design,
power_note, assessed_at, code, title, statement, rank`

> **兩個建置時會踩到的點**（實測資料就長這樣）：
> ① **排序是錦標賽名次，不是分級**——`tier=C rank=2` 排在 `tier=B rank=6` 前面。
> 後端註解寫得很明白：「grouped but never reordered」，因為 C 級可能比 A 級值錢。
> **前端不准重排。**
> ② **A 級是 0 筆**（counts `{A:0, B:1, C:10, D:0}`）。空清單是常態不是例外，
> 而且 `dataset_id: null`——沒上傳資料清單時全部會落在 C。

**畫面 ②** `verify-terms`（POST）→ `terms[{term, in_mesh, mesh_label,
semantic_types[], variants[], papers}]`

> 實測就抓到一個真的：propose 從「空氣中細懸浮微粒」拆出的
> `fine particulate matter` **不在 MeSH 裡**（8,190 篇），
> 而正式的 `particulate matter` **在**（`Particulate Matter`，35,940 篇）。
> 差四倍多，而且沒有階層可以展開。**這就是畫面 ② 存在的理由的活例子。**
> 對照組：`genetic alteration mutation` → 不在 MeSH、**3 篇**。
>
> 判斷「這一軸等於沒有」要看 `in_mesh: false` 加上 `papers` 很小，
> 不是看 `unique_id` 是不是 null——這個端點沒有回 `unique_id`。

**畫面 ④** `debate` → `project_id, n_debated, drift_max, max_rounds,
debates[{idea_id, code, title, n_rounds, last_round, terminated, drift,
n_objections_open, termination_reason, rank}]`
**但沒有反對意見內文**——那要 `debate-state?idea_id=`。所以 ④ 是
「一次拿清單、再對展開的那個方向拿內文」，不是一次拿完。

## 🖥 前端：`frontend/index.html`（2026-09-08）

**單檔 HTML，本機直接開。** 沒有建置步驟、沒有相依套件、沒有伺服器。

```
file:///D:/n8n_Claude/research-api/frontend/index.html
```

金鑰第一次開會跳輸入框，存在 `localStorage`。**檔案裡沒有寫死金鑰**——
所以這個檔案本身不是秘密，可以備份、進 git、傳給人看版型。

### 🔴 `docs/frontend-brief.md` 是過期的，不要照它做

那份第 0 節寫「唯一的風格依據是 `dei.azabu-u.ac.jp`」，
第 1 節整組色票／字體都是從那個網站量的（`#F4EDE7`、Montserrat、虛線分隔、
扁平插圖、有機色塊）。**但風格後來換過第三次**，
定案是 `select.daiichisyokuhin.com`，五張稿也是照那個建的。

**真正的依據是 pen.dev 文件本身的變數。**
本文件較前面那一節（畫面 ③ 已建好）記的是對的，簡報沒跟著更新。

實際代幣（`GetVariables()` 讀出來的，前端 CSS 的 `:root` 與它一一對應）：

```
s-ground  #F8E2D8   s-ground2 #F1D2C5   s-white  #FFFFFF
s-camel   #C2A084   s-camel2  #E0CBB6
s-teal    #4E9A95   s-wine    #7A2233   s-night  #1E1B1A
s-text    #333333   s-text2   #7A6E68   s-rule   #E2CCC0
s-ochre   #B0862B   s-ochre-tint #F0DFBE

s-serif Cormorant Garamond   s-sans Jost
s-cjk   Noto Serif TC        s-cjks Noto Sans TC
```

分隔線是 **`1px solid #E2CCC0`**，不是虛線（那是舊風格的規格）。
圓角是 50%（圓點）、16–20px（藥丸）、以及分頁的不對稱 `8px 0 0 0`。

**pen.dev 的算圖／截圖管線仍然壞著**（`TakeScreenshot` 逾時），
但 `Export(...,"html-css")` 正常，版型是那樣抽出來的。

### 每一格都對得到實測欄位

建置前把每條路由都實跑過一次，欄位清單在上一節。**三處我原本用猜的，都猜錯了**：

| | 我猜的 | 實際 |
|---|---|---|
| `watch` | `rows` / `checks` | **`watches[]`**，含 `verdict, n_new_papers, checked_at, coverage_limits` |
| `dataset` | 整包 JSON 印出來 | **`{n, datasets[]}`** |
| 報告內文 | 平的鍵值 | **`{report:{sections:{8 節}, citations[], caveats, acquisition, novelty_verdict}}`** |

**`order_flip_rate` 沒有畫**——後端從來沒存過它（G13），所以畫面 ③ 上沒有那一格。

報告的 `caveats`／`acquisition`／`novelty_verdict` 是 migration 018 才加的，
**舊報告是 null**，所以那三塊是條件顯示的，不是永遠都在。

### 資料清單上傳做進畫面 ③ 了（2026-09-09）

使用者指出畫面 ③ 顯示「你的資料清單」卻沒有任何上傳入口——**功能一直只活在
`W-DATA` 那張 n8n 表單裡**，跟畫面 ② 當初的狀況一模一樣。

新增三條路由：`dataset-save`、`dataset-template`、`chain-stop`。

**CSV → inventory 的轉換整段搬進瀏覽器，而且是照抄 W-DATA 的邏輯**——
必要欄 `file`/`column`、可選 `dtype`/`description`/`joins_on`/`personal`、
BOM 剝除、引號感知的 CSV 解析、`provenance: documented`。
**形狀不一致不是比較弱的答案，是 W6 讀不懂的答案。**

> **搬到瀏覽器反而更符合原本的前提。** W-DATA 那張表單自己寫著
> 「這個網頁讀不到你的硬碟（它跑在雲端）」；前端跑在使用者本機，
> 檔案在瀏覽器裡解析，**送出去的只有欄位名稱與描述，原始資料連送都不會送**。
> 送出前會先把「將要送出的欄位名稱」列給使用者看——選錯檔案由你發現，
> 不是由伺服器發現。

三種情況都做了（W-DATA 有三個選項，不是一個）：上傳清單／沒資料但直接繼續／
沒資料先停著。存完會順手 `release`，因為鏈會停在 W6 前面等清單。

用真的 `tools/inventory_template.csv` 跑過解析：
2 個檔案、10 個欄位、`personal` 與 `personal_because` 都對、
**沒有洩漏任何量測欄位**（documented 帶量測值會被 API 拒絕）。
兩道擋牆也驗過：帶 `rows` 鍵的 JSON 擋下，病歷型 CSV 因為缺 `file`/`column` 擋下。

## 🔴 search 模式第一次全程實跑（2026-09-08 深夜）

使用者交了一個真題目：**雙抗血小板藥物對多重慢性病之腦中風患者的效用與安全性**
（`82ffbcec-20fc-4377-b1a1-01f5dff6061f`）。

**W-START 整段編排是對的，從頭串到尾：**

| 步驟 | 結果 |
|---|---|
| W2 文獻層 | 89 秒 · 9 個查詢 · 217 篇 |
| W1 領域框架 | $0.0076 · observational · clinical · high |
| 採集缺口句 | 輪詢 13 次（6 分半）· 200 篇 · 全文 94 · 缺口句 110 |
| W3 想點子 | 3 分 21 秒 · $0.0318 · **15 個方向** |
| 上鏈 | W4 排入 pending |

**然後 W4 當場錯掉，而錯的是我。**

### 缺陷：`run_id` 在這裡也有兩個意思

W4 的 `Load The Directions` 回 `{n:0, ideas:[]}`，被 API 的
`need at least 2 ideas` 擋成硬錯誤。原因：

- W-START 建專案時 `/compute/run/start` 給了一個 run（**文獻檢索用的**）
  `5c1a8faf-…`
- W3 的 `Save The Directions` **只送 `project_id`**，於是
  `/compute/ideas/save` **自己另開了第二個 run** `8c17853c-…`，方向掛在那上面
- 我的 `Put It On The Chain` 傳了**前者**

> **這跟 W-CHAIN 那個 `run_id` 撞名是同一類缺陷，而且我在讀過那段註解之後
> 又犯了一次。** 兩個東西都叫 `run_id`，指的卻是不同的 run。
>
> 這次是 API 的守門把它擋成硬錯誤，才沒有變成「去重零組然後回報成功」。
> **守門救了它，不是我的設計救了它。**

**修法**：`Combine Into Directions` 之後插兩個節點——
`Which Run Owns The Directions`（查 `/compute/ideas?project_id=…&limit=1`）
與 `The Run W4 Must Look At`（取 `ideas[0].run_id`，**查不到就拋錯而不是傳 null**，
因為 null 到了 W4 等於「不過濾」，又是靜默失敗）。已發布。

### 另一個副作用：卡在 running 的 run 列

W4 是**內部錯誤**，不是派工失敗，所以 W-CHAIN 的
`Tell The Chain It Did Not Start` 不會觸發，`advance` 也沒被呼叫——
那一列從此停在 `running`，十分鐘的安全網也撿不到（它只撿 `pending`）。

已用 `chain/stop` 清掉並寫了理由。**`closed_stages: ["dedup"]`。**

> 值得記的形狀：**階段內部錯誤會讓 run 列永遠停在 `running`。**
> 派工失敗有人管，階段自己掛掉沒有。

### 順手修掉的：W2 記帳在前端這條路會報錯

`Record The Spend` 引用 `$(Split Topic Into Concepts)`，但前端進來時那個節點
不執行，於是拋錯，母工作流收到 `{error: Node … hasn't been executed}`。

**實際上沒有漏記錢**——前端這條路 W2 一次模型都沒叫。但訊息會誤導。
改成先探測有沒有 usage，沒有就回零筆讓記帳整段跳過。
**不是送 0**：送 0 在帳上跟「真的免費」長得一樣。

## 🖥 前端當天後半段補的東西

- **狀態軸可以點了。** 後三步是某個專案的結果，所以軸記得「當前專案」
  （`sessionStorage` ＋ 右側直立標籤）。沒選專案就點會說明原因再帶回首頁，
  **不會丟到一個只會說「沒東西」的頁面**。
- **「尚未有結果」跟「出錯了」分開。** 4xx 當成「這步還沒跑」，
  只有網路／5xx 才跳錯誤。
- **進度頁每 20 秒自動重讀**，顯示「更新於 hh:mm:ss」，
  跑到 `awaiting_you`／`done`／`failed` 就停止輪詢。
- **`runningHint`**：偵測到「前面幾步完成、下一步沒紀錄」時直接說明
  ——鏈之前那四步只在存好結果時才變 `done`，**正在跑的時候看起來跟沒跑一樣**。
  附上實測耗時（文獻 1–2 分、採集 5–8 分、W1 10 秒、W3 3–5 分）。
  這是使用者當場問「這樣是還在跑嗎」逼出來的。
- **五張內嵌 SVG 科研線稿**（星座問號／MeSH 階層樹／名次條／天平／報告頁）。
  pen.dev 的 AI 圖**不存在硬碟上**，匯不出來，所以自己畫。
- 深色圓角頁尾、紙紋網點、交錯色帶、卡片左上髮絲刻線、首字放大。

### 還沒做的（接下來）

1. **續跑測試專案**（見本文件最上面那段指令）
2. 全域花費上限（`lib/budget.py` 只有每專案上限）
3. `/compute/chain/plan` 的說明字串已過期
4. 唯讀報告分享連結（要分享給朋友時才需要）
5. 考慮：**W3 存方向時應該收下傳進來的 `run_id`**，而不是另開一個。
   現在是靠 W-START 事後查回來補救；從源頭一致會更乾淨，
   但那要動 W3 與 `/compute/ideas/save` 兩邊，不是今晚該做的事。
2. **整條 search 模式還沒實跑過**（約 $0.8–1.5、20–40 分鐘）
3. 全域花費上限（`lib/budget.py` 目前只有每專案上限，
   金鑰外流或哪個 bug 失控時沒有天花板）
4. 唯讀報告分享連結（要分享給朋友時才需要，見對話紀錄的 B 案）
5. `/compute/chain/plan` 的說明字串已過期：它還寫著
   「W1, W2, harvest and W3 are started by hand」——現在 `W-START` 會串起來

### 現成的測試資料，不用花錢

專案 `88bb63ee-2c6a-4386-9377-608ef62d81bf`（胰臟癌）
**現在就停在審閱點 ④**（`chain_state: awaiting_you`），
而且 W6 分級、W7 新穎性、W8 辯論、W9 報告的資料全都在。
**畫面 ①③④⑤ 可以直接拿它開發**，一毛錢都不用花。

---

## 🟡 真實發現：MCN 那個方向四天內就被壓縮了

W10 第一次對胰臟癌專案實跑（2026-09-07 15:00），六個方向：

| 方向 | 結果 |
|---|---|
| **code 14 · MCN 監測後切除**（**報告 `368c9d4d` 寫的就是這個**） | **`incremental`，4 篇新論文**——不是被搶先，但**範圍被縮小** |
| code 5 · KRT19 液態切片 | `incremental`，1 篇新論文 |
| code 9 · 膽道支架 | 安靜日，0 篇新論文 |

**報告 09-05 說它是 `adjacent`（沒人做過），四天後就不完全成立了。**
這正是 W10 存在的理由——**新穎性判決是一句有時效的話**。

---

## 🔧 W10 這一天改了什麼（2026-09-07）

### 實跑第一次就發現它盯錯了專案

W10 建好之後**從來沒跑過**（六個方向的 `last_watched_at` 全是 `null`）。
第一次跑發現：**`Which Project To Watch` 讀的是一個寫死的 id，
而那個 id 指向「PM2.5 缺口採集測試」——一個測試專案。**

**如果當初直接把排程啟用**，它會每天早上八點去監看一個測試專案，
每次花約一分錢，而真正在意的方向一次都不會被查。
**從工作流的結構上看不出這件事，只有實際跑一次才會發現。**

（另外：用 MCP 執行有兩個觸發器的工作流時，**它選的是排程觸發器**，
所以我傳的 `project_id` 被忽略了。要指定專案得用表單的 production URL。）

### 改成可指定的清單

`Which Project To Watch` 從 Set 節點改成 **Code 節點**，最上面一份陣列：

```js
const WATCHLIST = [
  "88bb63ee-2c6a-4386-9377-608ef62d81bf", // 胰臟癌
];
```

一行一個 id，前面加 `//` 就是暫時停掉。表單填了 `project_id` 就只跑那一個。
清單是空的會**直接拋錯**，不會默默什麼都不做。

### 順手修掉兩個會靜默出錯的地方

1. **`One Item Per Direction` 原本用 `.first()`** 取監看清單。多專案時
   只拿得到第一個，其餘被靜默丟掉——**跟 W8 那個「三個方向只辯到一個
   但守門全過」是同一個形狀**。改成走訪全部並替每個方向標上 `project_id`。
2. **花費原本全記到第一個專案。** 預算是每個專案各自的，記錯會讓護欄
   拿錯數字判斷。新增 `Spend Per Project` 按專案分開記帳。

也把預算檢查與清單查詢改成 `continueRegularOutput`：**某個專案預算不足
或讀不到時只跳過那一個**，其餘照跑。

### 🔴 然後我自己引入了一個缺陷，實跑當場抓到

改完之後我把「記帳」和「LINE 通知」放成**兩條平行分支**。實跑時 LINE 憑證
失敗 → 整個執行停止 → **記帳那條沒跑到**。結果是：模型判決產出了
（MCN 的 `incremental` 有存進資料庫），**但 `by_stage` 裡沒有
`collision-watch`，錢花了沒記到**。

`budget.py` 開頭就寫過：**「一個數字安靜偏低的護欄，是這個檔案唯一不能
變成的東西。」**

**已改成序列：記帳在前，通知在後**，中間一個 `Anything To Record?` 讓
安靜的日子直接跳過記帳（不為零元花費打 API）。`Push To LINE` 也設成
`continueRegularOutput`——**通知失敗不該讓整個巡查算失敗**。

**那筆漏掉的花費還沒補記。** LINE 修好後補跑一次 W10 就會進去。

### 還沒做：用題目文字代替 uuid

要人查一串 uuid 再貼進程式碼，本身就是會出錯的做法。計畫是在前面加一個
節點讀 `/compute/projects`，讓 WATCHLIST 直接吃題目的一段字：對到一個就用它、
對到零個就**把現有專案清單印在錯誤訊息裡**（錯誤訊息本身回答「去哪裡查 id」）、
對到多個就要求寫精確一點。

---

## 🎨 前端（2026-09-05 → 09-07）：畫面 ③ 已在 pen.dev 建好

### ⏭️ 目前的狀態

**風格第三次換定：`https://select.daiichisyokuhin.com/`**（日本第一食品 SELECT）。
雜誌編輯感——粉膚底、滿版攝影、超大浮水印斜體襯線字、色塊左右交錯、
細規線、直排標籤、深色頁尾。**不是**先前的 Azabu 扁平插圖風。

**五個畫面全部建完了**（2026-09-07）：

| 節點 | 畫面 | 尺寸 |
|---|---|---|
| `jGoUr` | ① 首頁（交題目／專案列表／進行中，三狀態堆疊） | 1440 × 4007 |
| `r0tLGs` | ② 確認檢索概念 | 1440 × 1599 |
| `hOMBb` | ③ 審閱點三 · 可行性分級 | 1440 × 5979 |
| `C6vsYv` | ④ 審閱點四 · 辯論紀錄 | 1440 × 2522 |
| `J7fFWn` | ⑤ 報告 · 含下載與撞題監看 | 1440 × 3266 |

**頁首做成了可重用元件 `QBXeZ`**（`reusable:true`，原本住在 ③ 裡面）。
其他四個畫面用 `{type:"ref",ref:"QBXeZ",descendants:{…}}` 插入，
只覆寫哪一個步驟點是亮的。**改頁首改一次就好。**

流程步驟點的 id（覆寫用）：
`xTJiD`/`Jse2z`（1 題目）、`a6rk9l`/`HusOf`（2 概念）、`OHT64`/`rkxik`（3 分級）、
`Y6V8b`/`XR2R3`（4 辯論）、`kGiFB`/`tUgfg`（5 報告）。亮的是 `$s-wine`＋7px。

**③ 和 ④ 共用版型**（標頭 → 證據 → 但書 → 放行），④ 的放行區是用同一個
產生函式做的，只換文案與圖示。

### 🔴 pen.dev 的算圖管線壞了——先看這一段，不然會鬼打牆

**`Export` 成 PNG 和 `TakeScreenshot` 都只畫得出「被匯出那個節點自己的填色」，
所有子元素一律不畫。** 連一個純色 `rectangle` 子節點都畫不出來。

用一個最小 PROBE（一個有填色的 frame + 一個矩形 + 兩行文字）確認過：
框的駝色有出來，三個子元素全部消失。**跟結構、變數、字體、佈局都無關。**

先前那份「畫面 B 算不出圖」的診斷因此是誤判——不是那棵樹壞了，是整個算圖壞了。
（今天稍早它還正常過一次，所以是 app 跑到一半壞掉，重開 Pencil 可能會好。）

**✅ 可用的替代路徑（今天全靠這條）**：

```
Export([id],"html-css","...\s3.html")
  → mcp__pencil__browser  load-page   file:///...\s3.html
  → mcp__pencil__browser  return-screenshot
```

HTML 匯出完全正常，瀏覽器截圖看得到真實成果。**但有四個限制**：

1. **`Generate(...,"ai",...)` 產的圖不會匯出**——HTML 用相對路徑
   `./images/generated-*.png` 參照它們，而**那些檔案根本不在硬碟上**
   （查過整個文件資料夾，只有我寫的 `.glsl`），圖存在 app 內部。
   **所以所有 AI 素描都無法用這條路驗證，只能請使用者在畫布上看。**
   Unsplash 的 `stock` 圖是絕對網址，看得到
2. **shader 填色在 HTML 裡是死的**——看不到動畫
3. 瀏覽器視窗約 1199px 寬，1440 的設計右側會被裁掉——那是視窗不是版面問題
4. **HTML 的元素堆疊有小誤差**，會讓相鄰區塊看起來重疊。
   **以 `Get` 的 `c.bounds` 為準**：⑤ 的第 06 節結束在 y=1211、
   第 07 節從 1211 開始，數據是乾淨的，畫面上的重疊是匯出假象

### ⚠️ 文件被清空過

`R49B9`（Azabu 交題目）、`h21qL`（Azabu 確認概念）、`yZEQY`（舊操作台）
**都已經不存在**。現在根層只有新的 ③ 和一個空的 `bi8Au`。
不用去找它們，也不用重建——風格已經換掉了。

（以下是舊的畫面 B 診斷紀錄，保留只是因為排除法本身還有參考價值：）

畫面 B（`h21qL`）**匯出是一片空白米色**，子樹裡任何一個節點單獨匯出也是白的
（試過 `MufFG` Head）。**畫面 A（`R49B9`）同一份文件、同一組變數，匯出完全正常。**

**已經排除的原因**（不要重驗）：

| 懷疑 | 查法 | 結果 |
|---|---|---|
| 變數表被壞色碼汙染 | 19 個變數逐一比對 `#rrggbb` | 全部合法 |
| 引用到不存在的變數 | 蒐集子樹所有 `$xxx` 比對變數表 | `MISSING: (none)` |
| 節點是 placeholder | `Get("h21qL",{depth:2})` | 沒有 placeholder 旗標 |
| 結構壞掉 | 同上 | frame／text 結構正常 |

**唯一異常的線索**：`h21qL` 是 `layout:"vertical"`、沒有 padding，
但第一個子元素 `Nav` 的 `y` 是 **50** 而不是 0（畫面 A 的第一個子元素是 0）。
子元素相接無縫（50→125→359→473→791→956→1110），而框高是 **1060**——
剛好等於內容高度，但整段被往下推了 50，所以最後 50px 溢出、`CTA` 報
`partially clipped`。**那個幽靈 50px 偏移大概就是同一個病的表徵。**

**若新設計也發生同樣的事**，未做完的診斷是：建一個最小 PROBE 框
（一個 frame + 兩行文字）匯出，分辨「新建的節點都算不出來」還是「那棵樹壞了」。
上次卡在語法——**`Create` 不是 pen.dev 的 API**（`ReferenceError`），
先 `read_skill` 查正確的建立節點寫法。
PROBE 白 → 文件層級問題（存檔後重開或另開新 .pen）；PROBE 正常 → 刪掉重建。

### 🔴 第 0 步做完了：`docs/frontend-api-gaps.md`（2026-09-07）

把五個畫面上的每一個欄位對到端點與資料表，零成本、沒跑任何東西。
**找到 11 個對不上的地方，其中 3 個會讓畫面根本畫不出來。**

最嚴重的不是缺欄位，是**有兩塊內容根本沒被存下來**——
報告的「這份沒有涵蓋什麼」和「不經模型的取得清單」只活在 n8n 的執行輸出裡，
`health_metric` 只吃 `numeric`，存不了清單。

**下一步的順序寫在那份文件最後**。重點：
**做完後端那 6 項再開始寫 n8n webhook**——
包一層在缺資料的端點外面，只會讓缺口更難看見。

#### ✅ 第 2 件做完了：`list_projects` 併入費用與鏈狀態（2026-09-07）

`GET /compute/projects` 現在多回傳
`usd_budget` / `usd_spent` / `usd_remaining` / `chain_state` / `parked` /
`n_stages_done` / `n_stages`，外層多一個 `n_awaiting_you`。
**兩次查詢做完全部**（專案一次、所有專案的最新 run 一次），沒有 N+1。

`chain_state` 七態，規則在**純函式** `db._chain_state_of`，
`tests/test_projects_list.py` 離線釘住 **17 項**（六個測試檔全過）。

三個刻意的分辨，改動時不要合併：

1. **`stopped` ≠ `failed`**——刻意結束的鏈不該看起來像壞掉的
2. **`parked.awaiting` 分 `review` / `precondition`**——兩種列都叫
   `awaiting_review` 但意思相反（跑完停在審閱點 vs 前置條件不足根本沒跑）。
   「按放行」和「去上傳資料」不是同一個請求
3. **`chain_state` ≠ `project.status`**——後者是專案自己的生命週期旗標，
   合併會產生一個「有時是這個有時是那個」的欄位

**還沒對線上資料庫驗過**（純函式的部分測過了，SQL 沒有）。
部署後用 W-ADMIN 打一次 `/compute/projects` 確認欄位都在。

#### ✅ 第 1 件做完了：報告自己記住警語（2026-09-07）

**`migrations/018_the_report_keeps_its_caveats.sql`——⚠️ 還沒套用。**

`report` 加三欄：`caveats`（jsonb）、`acquisition`（jsonb）、
`novelty_verdict`（text）。

**關鍵決定：三者都在 `save_report` 內從資料庫算出來，不接受呼叫端傳入。**
理由跟 `debate.decide_termination` 一樣——呼叫端手上拿的是模型對自己極限的
說法，而那是模型最不該回答的問題。**所以 W9 完全不用改**，欄位會自動填。
（W9 守門裡那份 `data_to_acquire` 現在變成冗餘的第二份，留著無害。）

`caveats` 四項，每一項都同時給數字與後果：`fulltext`（全文篇數／總篇數）、
`novelty_unverified`（**兩個數字不是百分比**）、
`excluded_as_already_done`（**點名不只計數**）、`debate`（輪數／漂移／未解決）。

`acquisition` 與 `novelty_verdict` **抄寫而非參照**，理由同 `tier`／`rank`：
分級與新穎性檢查都可以重跑，參照出來的值會安靜地跟報告內文打架而不報錯。

`tests/test_report_caveats.py` 離線釘住 31 項，含三個退化情況
（沒採集／沒分級／沒辯論要降級成量得到的項目，不是產生垃圾或消失）。

#### ✅ 缺口全部收完並在生產環境驗過（2026-09-07）

**84 個路由**（80 → 81 → 84）。實測結果：

| 端點 | 實測 |
|---|---|
| `/compute/debate?project_id=` | `n_debated: 3`，三個方向名次 2/4/6，帶 `drift_max: 0.5` 與 `max_rounds: 10`（G6+G7）|
| `/compute/tournament/{id}` | `n_matches: 286 / n_judged: 283 / **n_undecided: 3**`（G10）|
| `/compute/health?project_id=` | 三個指標，見下方 🔴（G9）|
| `/compute/report/export?format=markdown` | `text/markdown`，`filename="report-368c9d4d.md"`，八節齊全 |
| `/compute/dataset/template` | 已上線（`main.py` 讀 `tools/inventory_template.csv` 加 BOM）|

**W8 的修正也被獨立佐證**：`/compute/debate?project_id=` 回傳三個**不同的**
方向、各一輪。修正前是一個方向一輪、另外兩個被靜音跳過而守門全過。

**兩條路徑還沒在真實資料上跑過**：`caveats` / `acquisition` 的自動填入
——`368c9d4d` 是 09-05 寫的，那三欄都是 null，所以匯出裡**沒有**
「這份沒有涵蓋什麼」。那是正確行為（測試釘住「沒有警語不要長出空區塊」），
但要驗證自動填入得**產一份新報告**。

#### 🔴 新發現：順序翻轉率根本沒被存下來

`GET /compute/health` 做好之後才看見的。`health_metric` 裡只有三個指標，
全部來自 W2（`paper_reuse_rate` / `query_repeat_rate` / `within_run_overlap`）。
**沒有 `order_flip_rate`**——它在 W5B 的守門裡算出來，只活在 n8n 的執行紀錄裡。

所以畫面 ③ 的「順序翻轉率 18.6%」**仍然沒有來源**。G9 補的是讀的那一半，
寫的那一半不存在。**跟報告警語是同一類問題：算出來、看過一次、然後消失。**

修法要動 W5B（算完之後把它寫進 `health_metric`）。在那之前，
**③ 的翻轉率欄位要從設計上拿掉或標成「尚未量測」**。

#### ⚠️ Zeabur 的第四種失敗：Docker Hub 429

`746271c` 的建置失敗在第一步：

```
#2 ERROR: unexpected status from HEAD request to
   registry-1.docker.io/v2/library/python/manifests/3.13-slim: 429 Too Many Requests
```

**Docker Hub 擋下了拉取基底映像的匿名請求**，因為那天連續建置太多次
（80→81→84 再加重新部署與重試）。

**那個 commit 只有文件改動，所以線上完全不受影響**——`/compute/health`
還在，跑的仍是驗證過的 `d2a2e2e`（84 個路由）。

**處置：等一段時間再推。** 不要連續重試，那只會加深限制。
真的常撞到的話，兩個解法：Dockerfile 改用已認證的 registry，
或把基底映像鏡像一份到 Zeabur 自己的 registry。

#### ⚠️ Zeabur 的第三種失敗形態：建置成功但卡在拉映像檔

`d2a2e2e` 推上去之後 20 分鐘沒生效。**建置紀錄是 `DONE build completed`**，
pip 也裝完了——所以不是建置失敗。**運作紀錄只有一行**：

```
Pod/... - Pulling: Pulling image "registry-oci.zeabur.cloud/..."
```

然後就停在那裡。**容器從來沒啟動，Python 一行都沒跑過**，所以沒有 traceback。

**而且它會卡住後續的部署**：服務頁面同時出現「建置中 15m」「啟動中 37m」
「運作中」三個部署，狀態顯示 `1/2`。**卡住的那個佔著位置，新的排在後面**。

**處置：在服務頁面把卡住的那個部署取消掉，再重新部署。** 之後就正常了
（`Pulling` → `Successfully pulled` → `Container started` 三行都出現）。

**三種失敗形態長得都不一樣，診斷順序是**：
`/admin/config` 路由數沒變 → 看**建置紀錄**（失敗？）→ 沒失敗就看**運作紀錄**
（卡在 Pulling？還是 Python traceback？）→ 都不是才懷疑自己的程式。

**我這次連續猜錯兩次**（先怪 reportlab 裝不起來、再怪 import 崩潰），
兩次都是因為沒有先去看紀錄就推論。

#### 🔴 這一段是舊的紀錄：`d2a2e2e` 當時沒有生效

推上去 13 分鐘後 `/admin/config` 還是 **81 個路由**（應該 **84**），
`/compute/dataset/template` 回 **404**。前兩次建置分別是 3.5 和 5 分鐘。

**唯一的新變數是 `requirements.txt` 加了 `reportlab>=4.0`。**

**症狀為什麼不明顯**：建置失敗時舊容器會繼續服務，所以 `/healthz` 正常、
API 全部能用，唯一的徵兆就是路由數沒變。這就是「用路由數判斷部署，
不要看時鐘」的理由。

**退路已經鋪好**：`lib/exporting.py` 的 reportlab 是**延後匯入**的
（寫在函式裡不是模組頂層）。所以只要把 `reportlab>=4.0` 從
`requirements.txt` 拿掉：

- Markdown 匯出照常運作
- PDF 回一句「這個部署沒裝 reportlab，請改用 format=markdown」
- **其他七項缺口完全不受影響**

當初刻意寫成延後匯入就是為了這個。**PDF 是可以割掉的。**

**要先看 Zeabur 的建置紀錄確認原因**（我從這裡看不到），
不要盲目再推——HANDOFF 前面記過，連續快速推送會被合併或取消。

#### ✅ 前三件已上線並在生產環境驗證過了（2026-09-07）

部署完成的判斷：`/admin/config` 的 `n_routes` **80 → 81**，
`/compute/progress` 出現在路由清單裡。**用它判斷部署，不要看時鐘。**

| 驗證 | 結果 |
|---|---|
| migration 018 | `applied: true`，表數 26→26（正常，ALTER 不是 CREATE）|
| **另外讀回來確認** | `/compute/report?report_id=...` 回傳的最後三個鍵是 `"caveats": null, "acquisition": null, "novelty_verdict": null`——**鍵存在就代表欄位存在**，值是 null 因為那份報告是 09-05 寫的 |
| `/compute/projects` | `usd_budget` / `usd_spent` / `usd_remaining` / `chain_state` / `parked` / `n_stages_done` 全部有，外層 `n_awaiting_you: 0` |
| `/compute/progress` | 十列齊全，實測數字：文獻 16 查詢／248 篇、採集 200/69/112、方向 15、去重 20 組 0 重複、錦標賽 286 場**3 場未判決**、分級 `{A:0,B:1,C:10,D:0}`、新穎性 `{adjacent:1, incremental:3, scooped:2}`、辯論 1 方向 1 輪 2 未解決、報告 2 份 |
| 過期暫停的修正 | 胰臟癌專案回 `chain_state: "running"`、`parked: null`。**修正前這會誤報成「等你放行」** |

**實跑抓到一個離線測試看不到的錯誤**：`frame` 那一列的 `q1/q2/q3` 全是 null，
因為那三個路由答案巢狀在 `domain_frame.routing` 底下。而且就算讀對了也不該放
——那是三段一兩百字的推理散文，而那一列只有一行。改成
`paradigms` / `field` / `confidence`，讀起來剛好是
「observational + measurement + clinical」。已修並重新部署（commit `c9e96cc`）。

#### ⚠️ 部署順序跟直覺相反：先部署，再套 migration

`/admin/migrate` **是從容器裡的 `migrations/` 讀檔的**（`main.py` 的
`os.path.join(dirname(__file__), "migrations", name)`），
所以**還沒部署的 migration 檔案根本不存在**，套不了。

正確順序是 **push → 等建置 → 套 migration**。

中間有個空窗：新程式會 `INSERT` 三個還不存在的欄位，**但只有 W9 存報告時
才會踩到**。所以部署前要先確認**沒有任何階段是 `pending`**——
W-CHAIN 只派 `pending` 的列，沒有就不會有東西去叫 W9。

2026-09-07 部署前查過：唯一活躍的專案沒有 `pending`，安全。

#### 🔴 這一段是舊的紀錄（當時以為要先套 migration）

1. **程式沒有 commit、沒有 push**——`research-api` 是 git repo，
   改動在 `lib/db.py`、`lib/report.py`、`main.py` 加三個新檔
2. **migration 018 沒有套用**——要
   `POST /admin/migrate {"file":"018_the_report_keeps_its_caveats.sql",
   "expect_database":"research"}`，透過 W-ADMIN 打
3. **套用後一定要另外讀一次確認**——`applied: true` 只代表 SQL 跑完沒丟例外，
   本文件前面就寫過這個坑

**順序很重要：先套 migration 再部署程式。** 反過來的話，新程式會
`INSERT` 三個還不存在的欄位，W9 每次存報告都會 500——而那是整條鏈的最後一段，
失敗在那裡等於整趟白跑。

#### ✅ 第 3 件做完了：`GET /compute/progress`（2026-09-07）

`lib/progress.py`，一次回傳**十列**（鏈開始前的 W2／採集／W1／W3
加上鏈自己的六段）、每段的產出數字、費用、`chain_state`／`parked`、
以及**最新一場錦標賽的 id**。錦標賽那列同時給 `n_undecided`。

**兩樣東西使用者同意拿掉**，因為後端給不出來：

- **階段內進度**（「15 個方向中的 11 個」）——階段派工到 n8n 裡跑，
  **只在結束時回報一次**，中途的分數是捏的而且會動，看起來像真的
- **精確 ETA**——沒有量測基礎，時間隨文獻量與模型排隊變動

改成 `eta_note` 說實話。**設計稿與兩份前端文件都跟著改了**，
畫布上 ① 的「還要 25 分鐘」與 W3 那列的「15 個中的 11 個」已經改掉。

規則抽成純函式 `progress.build_steps`，`tests/test_progress.py` 釘住 30 項，
**其中一項是檢查那些欄位不存在**（`eta` / `percent` / `progress` /
`fraction` 這類欄名一個都不准出現）。八個測試檔全過。

#### 🔴 線上資料推翻了一個前提：過期的暫停（2026-09-07）

**部署前查線上狀態時發現的，離線測試看不到。**

胰臟癌專案 `88bb63ee` 的 `chain/state` 是這樣：

```
dedup       done
tournament  done
feasibility awaiting_review   ← 停在 ③
novelty     done              ← 但後面全跑完了
debate      running           ← 而且這一列從 09-05 就沒關過
report      done
```

那一輪是用 `chain/start` 往下推的（HANDOFF 前面記過），
而 **`chain/start` 只排下一段，不會碰被暫停的那一列**。

`_chain_state_of` 原本假設 parked 與 running 互斥（理由是 `resume` 會把
暫停那列自己翻成 pending）。**這個前提在真實資料上不成立**——
照原規則，一個已經產出報告的專案會永遠留在「等你放行」清單上，
而那張清單只有在上面每一列都是真的時候才值得打開。

**規則改成：暫停的後面只要有任何一段有紀錄，那個暫停就是歷史。**
兩段都看起來暫停時，活的是後面那一個。

**這是離線測試看不到的那一類缺陷**：規則本身自洽，錯的是它對真實資料的假設。

**✅ 那兩列已經清掉了（2026-09-07，使用者同意）。**
`POST /compute/chain/stop` 回 `closed_stages: ["feasibility","debate"]`，
只動那兩列，其他四段 `done` 的沒碰。

**清掉的理由寫在那兩列的 `error` 欄裡**，三個月後回頭看得出來這是
被刻意結束的，不是沒人管。

**驗證過報告完全沒受影響**：還是 2 份，`368c9d4d` 依然 8 個引用 0 個被擋下。
`stop()` 只 `UPDATE run SET status='stopped'`，不刪任何東西，
也不碰 `report` / `idea` / `feasibility` / `novelty_check` / `debate_round`。

**專案狀態變成 `done` 而不是 `stopped`**——因為 `report` 那段是 `done`，
而判定順序裡「最後一段完成」排在「有東西被停掉」前面。這是對的：
**這條鏈確實走到終點並產出報告**，被停的是它中途繞過去的兩列。

**副作用（正面的）**：`debate` 解除封鎖了。migration 017 的唯一索引
（`status IN ('pending','running')` 時同一專案同一階段只能有一列）
本來擋著這個專案重跑辯論——而 **W8 攤平巢狀迴圈的修正到現在還沒實跑驗證過**，
那個驗證正好需要重跑辯論。現在可以做了。

**三件全部做完了。剩下四個小的（G4、G6、G7、G9）與兩個缺的端點
（報告匯出、範本下載）。**

### 📄 兩份前端文件

| 檔案 | 內容 | 換風格時 |
|---|---|---|
| `docs/frontend-spec.md` | **功能規格**：5 個畫面要有什麼、怎麼運作、狀態、驗證、後端能力清單。**完全不含視覺** | **不動** |
| `docs/frontend-brief.md` | **風格簡報**：Azabu 風格的實測色票、字體、五個結構特徵，加每個畫面的真實文案 | 換一份 |

拆成兩份是使用者要求的——他可能會請 pen.dev 用不同風格各生一版，
功能那份不該跟著重寫。

### 風格簡報：`docs/frontend-brief.md`（2026-09-06）

**改成先讓 pen.dev 依簡報產出設計，我再照著建。** 先前是我直接在畫布上搭，
使用者的評語是「不太像我提供給你的網頁」——**原因是只抄了顏色沒抄結構**。

簡報裡的風格規格**是從 `dei.azabu-u.ac.jp` 實際量出來的**（用
`mcp__pencil__browser` 的 `return-element` 讀 computed style），不是目測：

```
文字 #333333（柔和深灰，不是純黑）    面板 #F6EFE5    底 #F4EDE7
黑底上的字是米白 #F6EFE5，不是純白
描邊 1.6px solid（不是 1px）          分隔線 1.6px dashed rgba(0,0,0,0.2)
Montserrat 500 / -0.02em（拉丁）      中文字距 0.05em ← 這個佔了調性的一半
```

**當初漏掉的五個結構特徵**（簡報裡列為硬性規格）：
① 巨大有機色塊當背景（單角 200–400px 圓角、滿版出血、跟上下段重疊）
② 黑色圓形箭頭鈕（40px 正圓，**文字在圓圈右邊不在裡面**）
③ 虛線分隔 ④ 不對稱單角圓角 ⑤ 扁平粗描邊人物插圖（一排人並肩走）

每個畫面都填**真實資料**（胰臟癌那次跑出來的數字），這樣設計階段就能看到
真實文字長度。

### 畫面數 11 → **5**（2026-09-07，使用者質疑後收斂）

使用者問「前端有需要那麼多頁面嗎」——**他是對的**。我把「有這份後端輸出」
當成了「要一個頁面」。**正確的判準是：使用者在這裡要不要做決定。**

真正需要人的只有五個地方：

```
① 交題目   ② 確認概念   ③ ⏸ 分級放行   ④ ⏸ 辯論放行   ⑤ 報告下載
```

| 原畫面 | 處置 |
|---|---|
| C 進行中、J 專案列表 | **折進 ①**——同一頁的另外兩個狀態 |
| D 👁① 去重、E 👁② 排名 | **折進 ③ 的證據區** |
| G 資料清單 | **折成面板**，出現在 ① 與 ③ 裡，不跳頁 |
| K 撞題監看 | **折進 ⑤ 底部一區** |

**D、E 折進 ③ 不只是省頁面，設計上更好**：去重與排名在 ③ 之前就跑完了，
使用者回來時它們已經是歷史；而 ③ 要他決定「往下驗哪幾個」，
**名次正是做這個決定的依據**。拆成兩頁等於把證據和決定隔開。

**③ 和 ④ 共用同一個版型**（標頭 → 證據 → 但書 → 放行），畫一次填兩份內容。

視覺強度也從兩級改成三級：**⏸ 阻塞**（坐在大色塊上）／
**✎ 必填**（米白面板）／**👁 參考**（低對比、可收合）。

### 使用者要的是什麼（我第一次弄錯過，寫在這裡免得再錯）

> 我需要的是一個可以從 W1 到 W9 的系統，不是指單一個專案的系統，而是透過
> W1 到 W9 的步驟可以讓使用者透過前端提供初步的研究方向或上傳題目，
> 系統會自動在後端去處理，中間可能會有一些需要使用者確認的地方
> （這時候就需要用前端呈現），最後會有個報告產出讓使用者在前端可以看到
> 結果並且可以下載報告結果。

**我第一次做成了「單一專案的操作台」（給我自己看的儀表板），方向是錯的。**
正確的框架是**研究者的一趟旅程**：交題目 → 確認概念 → 等 → 幾個審閱點 → 拿報告。

### 架構決定：**B — 走 n8n webhook**

前端只跟 n8n 說話，**憑證留在 n8n 那一側**；`research-api.zeabur.internal`
是內網位址，**瀏覽器根本連不到**，所以前端不可能直接打 API。

### 風格：`dei.azabu-u.ac.jp`（麻布大學 DEI）

使用者先給 `sawai.co.jp`（冷調薄荷綠），**後來改成 Azabu**。

**畫布上那組 `paper` / `terra` / `brand` 代幣是目測的舊值，已經作廢。**
現行色票在 `frontend-brief.md`，是量出來的（見上）。新設計進來時整組換掉。

### 畫面 ② 為什麼要那樣設計（別在重建時弄丟）

② 是整條流程裡**唯一非擋不可的人工步驟**，而且是踩過的坑：
`genetic alteration mutation` 對不到 MeSH、退化成 `Mutant (null)`、只搆到 3 篇，
查詢數 6 而不是 10，**白跑一次 W2**。

所以每張概念卡要並排三件事：**你輸入的詞 → 解析到的 MeSH 描述詞 → 論文數**，
而且要有一張是錯誤態（「只搆到 3 篇論文——這一軸等於沒有」）加替代建議。
**讓錯誤在按下去之前就看得見**，這是零成本的 `/compute/verify/terms` 的介面化。

### ⚠️ 一個已知的衝突：pen.dev 畫不出虛線

參考網站的**虛線分隔是它的識別之一**（`1.6px dashed rgba(0,0,0,0.2)`，
清單每一列之間、卡片內部切分都用它），簡報裡也列為硬性規格。
**但 pen 的 schema 沒有虛線描邊。**

pen.dev 大概會自己想辦法（一排小方塊、或退回實線）。
**建置時要確認它選了什麼**——退回實線的話整體會偏硬，
一排小矩形則要注意不能每條線都變成幾十個節點。

### 畫面 ③ 的實作重點（2026-09-07）

**風格實測值**（用 `browser return-element` 讀出來的，不是目測）：
拉丁字 **Jost**（標籤，字距 0.06em，小寫字級 10–14）、
日文用明朝＋角ゴ ⇒ 中文對應 **Noto Serif TC**（標題）／**Noto Sans TC**（內文），
文字色 `#333333`。

設計代幣建在 pen 變數裡，全部 `s-` 前綴：

```
s-ground #F8E2D8   s-ground2 #F1D2C5   s-camel #C2A084   s-camel2 #E0CBB6
s-teal #4E9A95     s-wine #7A2233      s-night #1E1B1A
s-text #333333     s-text2 #7A6E68     s-rule #E2CCC0
s-serif "Cormorant Garamond"（浮水印用 italic 300）   s-sans "Jost"
s-cjk "Noto Serif TC"   s-cjks "Noto Sans TC"
```

**動畫**：`research-field.glsl` 放在 .pen 檔旁邊，用 `fill:{type:"shader",
url:"./research-field.glsl",uniforms:{...}}`。`@time` uniform 讓它會動——
一片緩慢漂移的粒子與連線場，當作研究網絡的意象。
**`@resolution` 和 `@time` 標註的 uniform 不可以寫進 `uniforms`**，會報錯。

#### ⚠️ Unsplash 的 `stock` 查詢對「科學主題」很不可靠

`Generate(node,"stock","關鍵字")` 當場套用、不用等，但**回傳的圖經常文不對題**，
而且色調常常跟粉膚色盤打架。實際踩到的：

| 查詢 | 實際回傳 |
|---|---|
| `petri dish` | **一盤食物**（濃湯佐香草） |
| `medicine capsules` | **抹茶粉配湖水綠背景** |
| `dna helix` | 螢光綠紫的抽象 3D 圖 |
| `brain scan` | 戴耳機的鉻色頭像（比較像音響廣告） |

**每一張都要看過才算數**，不能因為關鍵字對就假設圖對。

可用的（中性、暖調、真的像實驗室）：
`microscope laboratory`／`laboratory bench`／`laboratory glassware`／
`laboratory pipette`／`microscope slide`／`hospital corridor`／`server room`。

**結論：抽象或特定領域的科學概念不要用 stock，改用 `Generate(node,"ai",...)`
產素描。** 這次三聯圖（臨床醫學／神經科學／人工智慧）和藥學那張全部改成
石墨素描，提示詞固定開頭：

```
A hand-drawn pencil sketch, graphite on warm off-white paper, fine cross-hatching
and loose confident linework, monochrome with no colour, editorial illustration
style, generous empty paper, no text and no lettering: <主題>
```

**單色素描還順便解決了色調打架**——暖白紙配粉膚底天生就合。
改成淺色圖之後記得把上面的壓暗層翻成淺色（`#F8E2D8D9`）、文字改深色，
不然白字會看不見。

**按鈕的小插圖**用 `icon` 節點（lucide 的 `microscope`／`flask-conical`／
`dna`／`atom`）包在圓形徽章裡，**不要為每顆按鈕生一張 SVG**——太慢也太貴。

**插圖**用 `Generate(frame,"svg",...)`，非同步、要幾分鐘，
用 `Get(id,{depth:0}).placeholder` 輪詢，**不要用截圖檢查**。

### pen.dev 的坑（實測）

- **建立節點是 `Insert(parent, {...})`，不是 `Create`**（先前記成要查，這裡直接寫死）
- **`height:"fill_container"` 會跟 `fit_content` 的父層形成循環依賴**，
  兩邊一起塌成 0。想讓色塊面板跟旁邊的清單等高，要**先 `Get` 量出清單的
  `c.bounds.height`，再 `Update` 面板的固定高度**
- **`alignItems` 沒有 `stretch`**，`margin` 和百分比尺寸也不支援
- **`TakeScreenshot` 只畫得出描邊**，沒有填色和文字。要看實際樣子得用
  `Export(nodes,"png",path)` 再用 Read 讀那個 PNG
- **`execute` 之間全域變數不留存**，要用字面 id
- 圖示名是 **`triangle-alert`** 不是 `alert-triangle`
- schema **沒有虛線描邊**（見上）
- 「fully clipped」的回報**先前多次是誤報**——但 `h21qL` 的 `partially clipped` 是真的
- **`mcp__pencil__browser` 很好用**：`load-page` 載入參考網站 →
  `return-screenshot` 看整頁 → `return-element` 讀 computed style。
  **今天的實測色票就是這樣拿到的**，比目測可靠得多。
  注意 `return-element` 的輸出很大，只查小的選擇器

---

## ✅ 第一份真正合格的報告（2026-09-05）

**報告 `368c9d4d`**，方向 code 14「監測後切除的黏液性囊性腫瘤，長期腫瘤學預後」。
**五道守門全過**，8 個引用零捏造，$0.133。累計約 **$1.63 / $2.00**。

### 新穎性閘門的第一次實跑，結果比預期好

| | |
|---|---|
| 挑中 | **`adjacent`**——PRD 定義的健康結果（沒人做過，但有鄰近文獻）|
| 排除 | **2 個 `scooped`**：CLEC4G，以及 **CRPM** |
| 未驗證 | 5 個，列在 `needs_novelty_check`，不參加排序 |

**CRPM 被排除這件事值得記**：它是 W6 判定唯一的 **B 級**、
「申請 NCDB/SEER 幾週就能做」的那個——**可行性最好的方向，
新穎性上已經被做過了**。這正是兩個軸不能合成一個數字的實例。

### 沒驗過新穎性 = 不合格（不是排在後面）

上一版把「沒驗過」排在 `incremental` 之前，理由是「沒檢查不等於不好」。
**那造成一個更糟的結果**：W7 驗完前幾個之後如果都是 `incremental`
（實測的常態，不是例外），W9 會直接跳過它們去寫沒驗過的——
**只要 W7 的結果不夠好，W9 就系統性地繞開它的成果**，
而且在正常跑完整條鏈時也會發生，不只是測試的假象。

改成不合格之後，「沒驗過和 incremental 誰先」這個問題**自動消失**——
兩邊的理由都說服不了人，而正確答案是它不該參加排序。
報告八節有一節專講新穎性，沒有材料就只能貼警語充數。

### W7 也會跳過已驗證的了

`Pick The Directions` 原本照分級看板取前 N 個、不看 `novelty_check`
裡已經有什麼——再跑一次只會把同樣那幾個重驗，每個 $0.067 換來同樣的判決。
**跟 W9 沒讀新穎性是同一個形狀：資料已經算出來也存下來了，只是沒人讀。**
`recheck=true` 才會重驗（方向被改寫過時才需要）。

### 取得清單守門：從誤報變成真的通過

`3/3 items named`。上一版報 `0/3` 是比對太嚴（取前 24 字元做子字串比對），
這次改成識別性關鍵字之後，三個 missing 變項全部驗證到被指名。

### 各階段實測單價（換題目重跑時拿來估算）

| 階段 | 實測 |
|---|---|
| W5B 錦標賽 | **$0.773**（283 場，佔全部六成）|
| W7 新穎性 | **$0.067／方向** |
| W9 報告 | **$0.134／份** |
| W6 可行性 | $0.079 |
| W8 辯論 | $0.036（1 場 1 輪）|
| W3 想點子 | $0.031 |
| W1 / W4 / W2 | $0.011 / $0.009 / $0.003 |

**$2 足夠換一個新題目完整跑一次；不夠在同一個專案上把 11 個方向全部驗完**
（光 W7 就要 $0.74）。

---

## ✅ 整條鏈跑通了一次（2026-09-05 稍早）

**專案 `88bb63ee-2c6a-4386-9377-608ef62d81bf`**，已花約 **$1.28 / $2.00**。

W2 → 採集 → W3 → W4 → W5B → W6 → W7 → W8 → **W9 九個環節全部走通**。
報告 `92e94fb5` 存進資料庫：八節齊全、6 個引用零捏造、$0.136。

### 這一輪修掉的四件事，全部是實跑才會出現的

**一、W8 的巢狀迴圈害兩個方向從沒被辯論（無聲）**

執行紀錄講得很清楚：

```
One Round At A Time  run5  out=5    ← 方向 1 正常跑完
One Round At A Time  run6  out=10   ← 方向 2：立刻從「完成」出口吐出
One Round At A Time  run7  out=15   ← 方向 3：同上
```

**內層 Loop Over Items 跑完一次之後不會重置。** 外層再餵新的一批進去，
它直接回報 done 並把項目累加上去。方向 2、3 的回合槽都建好也交出去了，
**一輪辯論都沒發生**——而 `Adopt` 照樣執行、**四道守門全過**，
因為每一道都只數「發生過的回合」。

修法是**攤平成單層迴圈**（先展開成 方向×回合 的平清單），不是加 `reset`
旗標——那會讓它每輪都重置、永遠跑不完。另加一道守門：
**被挑中的方向數必須等於有回合紀錄的方向數**，並點名是哪幾個沒辯到。

**二、一個多餘的 `]` 丟掉一份完整的報告**

模型寫完八節、內容紮實、引用真實，但在 `background` 結尾多打一個 `]`。
既有的救援假設「壞的是結尾」（多一個大括號、或被截斷），
這次**壞在中間**，靠括號配平的救援全部失效。

改成**逐個鍵抓字串**：八節是內容，信封的語法完整與否不該決定內容救不救得回來。
引用陣列刻意**不從碎片重建**——把 DOI 配到錯的 `used_for` 比缺少引用更糟，
因為存檔端檢查的是識別碼存在，不是它支持旁邊那句話。
需要救援會記在 `recovered_key_by_key` 並寫進 caveat。

**三、W9 從來沒讀過新穎性判決**（使用者發現的）

W7 花十四輪檢索得出 `scooped`，結論寫進資料庫然後**被 W9 無視**——
被做過的方向照樣拿到完整的八節報告。

現在的排序：`adjacent`／`no_prior_art`（已驗證還活著）→ 沒驗過（標記）→
`incremental` → **`scooped` 預設排除**。三個決定的理由：

- **排除而非排到最後**：寫一份要 $0.13，而讀的人得自己從新穎性那節推論出答案已發表
- **被排除的要點名**（`excluded_as_already_done`）：安靜地少寫一份報告，
  在輸出上跟「這個方向不存在」長得一模一樣
- **全排除時退回報告最好的一個並大聲標記**：空的執行讀起來像故障不像發現

**「沒驗過」不等於「新的」**——那些方向會被標成未驗證，不會被當成通過。

**四、取得清單守門是誤報**

上次報 `0/3`，但報告三項都寫了、而且比 W6 更詳細。是比對太嚴：
取前 24 字元做子字串比對，報告重新斷句就對不上。
改成取識別性關鍵字、要求半數以上出現且至少兩個。

**理由不是為了讓它變綠**：本文件自己寫過，**永遠是紅的指示燈會停止被閱讀**。

### 還沒驗證的

**W8 的攤平修正還沒實跑過。** 下次跑辯論時要看新那道守門
（`every selected direction was actually debated`）是不是 3/3。

---

## ⏸ 上一輪停在審閱點 ④（2026-09-03 深夜）

**專案 `88bb63ee-2c6a-4386-9377-608ef62d81bf`**，預算 $2，**已花約 $1.13，剩約 $0.87**。

W4 → W5B → W6 → W7 → W8 **整條鏈自己跑完了**，停在 ⏸④ 等審閱。
只剩 W9 報告（~$0.21）。

### 🔴 開機第一件事：查「為什麼 W8 只辯了 1 個方向」

W7 正確挑了 **3** 個（`n_selected: 3, n_eligible: 11`），但
**W8 的 `n_directions` 是 1**。`tiers: "B,C"` 有傳到，
但看起來 `max_ideas: 3` 沒有被 W8 的 `Pick The Directions` 套用。

**這件事會連累 W9**：不查清楚就放行，報告也只會寫 1 份，
測試就沒有走完該走的路。查 W8 執行 `428` 的 `Debate Request` 與
`Pick The Directions` 兩個節點輸出即可。

### W8 的結果本身是好的：漂移規則第一次在真實資料上咬到

唯一那場辯論（CLEC4G × CTSB × ferroptosis）**第 1 輪就因漂移被強制停止**：

| | |
|---|---|
| 漂移 | **0.778**（門檻 0.5）|
| 終止 | 「修訂後已經離原始敘述太遠，變成另一個方向」|
| 未解決反對 | 2 |
| 評分分布 | 3×2、4×1、**5×1** |

**PRD 說「十輪小小的通融可以把一個方向走成另一個方向」——這次它一步就走完了。**
系統當場停止並**拒絕採用那個修訂版**，這正是設計要的。
評分裡有 4 和 5，代表那兩個反對是真有力的，不是辯護方敷衍。

四道守門全過（每輪都存下、沒有捏造引用、每個反對都有回答、每場辯論都有論文可引）。

### W7 的結果

3 個方向、14 輪檢索、**7–9 種術語體系**、`longest_empty_run: 0`。
第一個方向判 **`scooped`**（胰臟癌 ferroptosis 是熱門題目，撈到前案合理）。

檢索計畫的角度確實分開，例如黏液性囊性腫瘤那個方向的第 9 輪是
**去卵巢文獻找同型病灶的監測結果**——那是關鍵字檢索結構上抓不到、
只有換術語體系才找得到的東西。

---

## ⏸ 審閱點 ③ 的結果（2026-09-03）

| 階段 | 結果 |
|---|---|
| W1 領域框架 | ✅ `observational` + **`measurement`**（Q2 強制）+ `clinical` |
| W2 文獻層 | ✅ 兩次，第二次 10 查詢（概念修正見下） |
| 採集 | ✅ 200 篇 / 全文 69 / **缺口句 112** |
| W3 想點子 | ✅ **15 個方向** |
| W4 去重 | ✅ 20 組候選，**0 重複**，11.5 秒 |
| W5B 錦標賽 | ✅ 15→11 個競爭，283 場，**$0.773**，順序翻轉率 18.6% |
| W6 可行性 | ✅ **無資料模式**，$0.079，四道守門全過 |
| **⏸③** | **停在這裡等使用者看分級看板** |
| W7 / W8 / W9 | ⬜ 未開始（合計約 $1.05，**剩餘預算幾乎剛好**）|

### 無資料模式第一次實跑，三項檢驗全過

| 檢驗 | 結果 |
|---|---|
| **A 級是 0** | ✅ `{A:0, B:1, C:10, D:0}` —— **模型沒有幻想資料集** |
| 有 B 級（有鑑別力） | ✅ 唯一的 B：大腸癌胰臟轉移手術，**申請 NCDB/SEER 幾週就能做** |
| `downstream_tiers` | ✅ `B,C` 而不是預設 `A,B`，W7/W8/W9 才不會中斷 |

C 級的去路寫得夠具體，而且**成本差異很大**——這正是 C 級該告訴人的事：
IPMN/MCN 登記聯盟只要談資料分享協議；TNFSF4 走 Vivli/YODA/CSDR 試驗平台；
膽道支架那條要從頭收前瞻世代（IRB + 定序 + 12–18 個月）。

### 放行方式，以及 `resume` 的一個缺口

`POST /compute/chain/resume {"project_id":"..."}` 會沿用上一段存下的交棒。

**但 `resume` 沒辦法在放行時調整參數**，而審閱點正是最該調整的時機——
你看完分級看板，才知道要驗幾個、辯幾輪。這次因此改用
`POST /compute/chain/start {"stage":"novelty","params":{...}}` 指定
`tiers` / `max_ideas` / `max_rounds`，代價是 ⏸③ 那列要另外用 `advance` 收掉。

**待辦：讓 `resume` 接受 `params`，覆蓋或合併存下的交棒。**

（為什麼非得指定 `max_rounds`：W8 的預算預估是
`max_rounds × max_ideas × $0.04`，預設 10 輪 × 3 個 = $1.20，
當時只剩 $1.09，護欄會直接 402 擋掉。）

---

### 交棒會被丟掉的兩個地方（都已修，但形狀值得記住）

**同一類缺陷出現兩次：中間那一段不在乎某個參數，就把它丟掉了。**

1. **`resume` 只傳 `{project_id}`。** 而停在審閱點時 `advance` 根本不會排
   下一段，所以交棒在當下就落地。W6 算出的 `tiers=B,C` 會消失，W7 退回
   預設 `A,B`——這個專案 A 是 0 個、B 只有 1 個，**等於安靜跳過 10 個 C 級方向**，
   而整條鏈看起來一路健康。修法：`advance` 存進 `params.handoff`，`resume` 讀回來。
2. **每一段的 `Tell The Chain` 只挑自己用得到的欄位往下傳。** 所以 `max_rounds`
   穿不過 W7——而它直接決定 W8 的預算預估。W7／W8 已改成把收到的 params
   原封留著、自己的疊在上面。**W4／W5B／W6／W9 還沒改，同樣的洞還在。**

放行的回應現在會列出 `carried_forward`——**交棒掉了要在這裡看得見**，
不然只表現在下一段的行為上，那看起來像「這一段沒找到東西」，
不像「沒有人告訴它要看什麼」。

---

## 這次真題目路上修掉的東西（2026-09-02 → 09-03）

**專案 `88bb63ee-2c6a-4386-9377-608ef62d81bf`**
題目：`是否有新的遺傳基因改變或突變可以讓胰臟癌患者在接受正規的治療後，有更長的存活率?`
預算上限 **$2**，已花 **$0.0124**。

| 階段 | 狀態 |
|---|---|
| W1 領域框架 | ✅ `observational` + **`measurement`**（Q2 強制）+ `clinical`，信心 high |
| W2 文獻層 | ✅ 跑了兩次，見下。第二次 10 個查詢 |
| 採集缺口句 | ✅ `ec209113`，200 篇 / **全文只有 58 篇** / 130 概念 / **82 句缺口** |
| **W3 想點子** | ⬜ **還沒跑**（$0.12），隨時可以 |
| W4 → W5B | ⬜ 之後 `POST /compute/chain/start` 自己接 |
| W6 可行性 | 🔴 **卡住：要先決定用什麼資料** |

**接下來第一件事是問使用者資料要走哪一條**（見下面「資料清單那題」），
然後就可以跑 W3 → `chain/start`。資料只在 W6 才咬到，
所以 W3／W4／W5B 可以先跑。

### W2 那次修正值得記：概念寫壞了整條鏈都會歪

第一次模型拆出 `genetic alteration mutation`——**三個詞黏在一起**，
MeSH 完全對不到，退而用了 `Mutant`（也不在 MeSH），所以那一軸**沒有階層可以展開**，
交叉只生出 6 個查詢（上限 10）。

用 `/compute/verify/terms` 一查就清楚了：

| 詞 | 在 MeSH | 論文數 |
|---|---|---|
| `genetic alteration mutation` | ❌ | **3** |
| `mutant` | ❌ | 404,939（太泛） |
| `mutation` | ✅ | 838,262 |
| `genetic variation` | ✅ | 61,631 |

改成 `Genetic Variation` 之後查詢數 6 → **10**。

**`/compute/verify/terms` 是零成本的事前檢查，以後在 W2 的概念確認頁猶豫時就打它。**
`(null)` 的 unique_id 就是警訊——那代表沒對到 MeSH 描述詞。

### 全文只有 58/200，這是 PubMed 封鎖的實際代價

缺口句只存在 Discussion 段落，摘要沒有。拿不到全文的 142 篇對 W3 是**靜音的**。
82 句夠用（W3 上限吃 60 句），但涵蓋面比正常窄，這點會一路帶到後面的方向品質。

### 資料清單那題（**待使用者決定，這是目前的阻塞點**）

W6 沒有欄位清單會直接 throw，而 **W7/W8/W9 都從 W6 的分級看板挑 A/B 級方向**——
所以鏈會在第三段（共六段）死掉。

**而且這不只是一個標籤**：資料集的選擇直接決定哪些方向拿得到後面昂貴的驗證。
拿 TCGA-PAAD 分級 = 在問「這個方向用 TCGA-PAAD 做不做得到」。

三個選項：把 `tournament` 標成 `pause_after` 讓鏈乾淨地停在 W5B ／
用公開資料集 ／ 用使用者自己的資料。

#### ✅ 已實作（2026-09-03）：W-DATA、provenance、鏈的前置條件

**W-DATA 資料清單上傳 `aAKjoUwsNypEJHto`**（已發布，`/form/w-data-inventory`）。
一張表單：專案 id、上傳 `inventory.json` 或填好的範本 CSV、選 pack。
存完會順手打 `/compute/chain/resume` 把卡住的鏈放行。

**刻意做成獨立工作流而不是塞進 W2**：資料清單通常不是開始文獻檢索時就備好的
（第一次跑胰臟癌就是這樣），而且之後會想用量測版取代描述版，那需要能再上傳一次。
W2 只加了一段說明和連結。

`tools/inventory_template.csv` **一列是一個欄位，不是一個病人**。
範本長得像資料表的話，遲早有人把真的病歷填進去然後上傳。

#### 沒有資料就換一個問題，不要中斷（2026-09-03）

W6 沒有資料清單時**不再中斷**。它改問「**要做到需要什麼**」而不是
「你做不做得到」——對還沒收資料的人，後者才是有用的答案，因為它說出該去弄什麼。

分級不會塌成一格。實測這批胰臟癌方向：黏液性囊性腫瘤預後用 SEER 就能做（B），
CLEC4G 那條要細胞株和小鼠模型（C），TP53 巴基斯坦族群要那個世代（C/D）。

**三件事必須跟著處理，少一件就會壞**：

1. **模型會幻想一個資料集。** 提示詞原本寫「你會拿到研究者的欄位清單」，
   沒有清單卻照跑，它會編一個然後照著評分——**比中斷糟得多，因為看起來完全正常**
2. **A 級結構上不可能**（定義是「這週就能開始分析」），加守門擋掉
3. **W7/W8/W9 預設只挑 A/B，而 A 是空的** → 後面三段會全部中斷在
   「沒有 A/B 級方向」。W6 現在把 `tiers` 往下傳（無資料時是 B,C），
   而且寫在守門輸出的 `downstream_tiers` 裡——**安靜地縮減下游看得到的範圍，
   從它們的輸出完全看不出來**

#### W9：C 級要寫出去弄什麼資料，而且有一份不經模型的版本

沒有自己資料時多數方向落在 C 級，而 C 級有用的不是那個字母，
是「要去弄什麼、跟誰要、多久、多少錢」。

提示詞對 B/C/D **強制要求** `feasibility` 那節開頭是逐項清單，每項五個欄位：
變項名稱（照資料申請時的寫法，不是類別）、來源、取得方式與所需權限、時間、費用。

**另外一份直接從 W6 存下來的 `missing` / `route_to_tier_a` 拉出來**，
放在守門輸出的 `data_to_acquire`。模型寫的那節是給人讀的散文，會漏；
這份不會，因為沒有東西重述它。**兩份不一致時以這份為準。**

多一道守門：B/C/D 的報告如果 `feasibility` 一個 missing 變項的名字都沒提到，
就是把該講的寫成了客套話。**比對變項本身，不是找標題**——找標題的話任何措辭都會過。

#### 鏈的前置條件檢查（`missing_precondition` 目前回 None）

`chain.missing_precondition` 在建立 run 列**之前**檢查。`feasibility` 需要
資料清單，沒有就標成 `awaiting_review` 並寫清楚要做什麼。

實際踩過才加的：W5B 跑完 → 鏈排 feasibility → 派工啟動 W6 → **0.3 秒後中斷**，
留下一列卡在 `running`、一次紅色執行、一則告警。**三樣都不是新聞**，
那個條件在派工之前就知道了。

**為什麼不是表單欄位**：表單在一開始問一次，問的是一個之後會改變的狀態。

**`resume` 裡有個陷阱**：兩種列都叫 `awaiting_review` 而意思相反——
一種是跑完停在審閱點，另一種是前置條件不足、**根本沒跑過**。
照舊邏輯處理第二種會把階段標成 done 並排下一段，**等於安靜地跳過 W6**。
用 `finished_at` 分辨（沒跑過的是 NULL），而且 `resume` 會重新檢查條件。

#### 使用者提出的需求（2026-09-02，已於 09-03 實作）

> 有時候我會使用公開資料集（這種情形希望你自動幫我去網路上準備好資料清單），
> 有時候我是用自己的資料（這種情形希望能讓我上傳我的資料清單，格式不限，
> 所以需要有 AI 幫忙解讀我的資料清單有哪些欄位）

**評估結論：兩個都做得到，但有一條紅線。**

`inventory.py` 的輸出分兩類，而 W6 大量依賴右邊那一類：

| 查得到的 | **只能量出來的** |
|---|---|
| 欄名、型別、可連結的鍵 | `missing_rate`、`n_unique`、`min`/`max`、`levels`、**列的結構** |

W6 的提示詞明說要分開檢查結構、`power_note` 要寫出實際列數、
A 級的定義是「這週就能開始分析」。**從論文或 data dictionary 抄一個 n 填進去，
等級就是錯的，而下游沒有任何東西分得出來。**

好消息：`save_dataset` 不強制那些欄位，**留 null 是合法的**，所以「不知道」表達得出來。

**需求一的誠實做法不是去網路上抄，是在使用者的機器上下載資料、實際跑 `inventory.py`。**
Bash 工具跑在本機，所以：下載 cBioPortal 打包檔 → 解壓 → `inventory.py` → 過目 → 上傳。
每個數字都是實測。

**需求二本來就安全，因為那個 AI 就是跑在本機的 Claude Code。**
使用者的檔案用 Read 讀、產出 inventory、只上傳最後那份欄位清單，
原始檔案從頭到尾沒離開電腦——跟「`profile.py` 永遠只在本機跑」相容。
分兩種：有實際資料檔就跑 `inventory.py`（目前只吃 csv，xlsx 要加）；
只有欄位說明就產出 inventory 但 **`missing_rate` / `n_unique` / `range` 必須留 null**。

#### `provenance: measured | documented`（已實作）

`inventory.py` 的輸出分兩類，而 W6 大量依賴右邊那一類：

| 查得到的 | **只能量出來的** |
|---|---|
| 欄名、型別、可連結的鍵 | `missing_rate`、`n_unique`、`min`/`max`、`levels`、**列的結構** |

三道防線：

1. **`save_dataset` 拒絕** `documented` 清單帶那五個欄位——出現就代表是編的，
   或是量測版被標錯了
2. **W6 明確告訴裁判**手上是哪一種，並要求 `documented` 時不得假設變項完整
3. **警語寫進每一列的 `power_note`**，跟 `has_profile` / `has_frame` 同一個機制。
   半年後看板子的人只會看到那一列

外加一道守門：**`documented` 清單不得出現 A 級**。A 級的定義是「這週就能開始
分析」，而沒有人查證過變項是否有值的時候，那是一個穿著量測外衣的猜測。

`tests/test_dataset_provenance.py` 離線釘住，22 項。

---

**跑一個新題目的完整流程**（這次驗證出來的正確順序）：
W2 表單（建專案 + 設預算上限）→ W1（要 `project_id`，所以在 W2 之後）→
`POST /compute/harvest/start` → W3 → `POST /compute/chain/start` →
剩下六段自己接續，只在**審閱點 ③ 和 ④** 停（`POST /compute/chain/resume` 放行）。

**n8n 那一半也驗過了**（零成本，用預算 402 擋在模型之前），過程抓到三個真的
問題，包括一個會讓 W4「去重 0 組然後回報成功」的 `run_id` 撞名——
細節見「階段自動接續」那一節。**六個階段工作流現在都是已發布狀態**，
它們的表單端點也因此在 production 生效了。

W8（唱反調）、W9（報告）、W10（撞題）三個的**模型那一半都還沒實跑過**，
而且卡在同一件事：這個專案沒有 A/B 級方向、只有一個方向跑過 W7。
跑完整條鏈會一次解掉三個。

理由不是進度，是驗證：這一天找到的缺陷幾乎全部在接縫上——`$("node").all()`
只回傳單一次執行、W4 不記存活者、欄位名與答案值撞在一起、可行性看板照 uuid 排
而兩個階段都以為它照名次排——**單獨測每個階段一個都看不到**。

而且 W8 現在卡著就是因為沒跑過整條鏈：這個專案的看板是 `{A:0,B:0,C:1,D:7}`，
一個 A/B 級方向都沒有，所以兩個模型還沒真的打過一場。跑完整條鏈之後
看板上自然會有 A/B，W7 跑完就有引用池，W8 才能真的跑。

順序：W1 → W2 → 採集 → W3 → W4 → W5 → W6 → W7 → W8。約 $3、約一小時。
建議題目：使用者自己的「環境賀爾蒙 × 肺腺癌第 0 期」。

（待辦第 0 項——清掉驗證用的假辯論資料——**已經在 2026-08-30 做完了**，
可以直接開始跑鏈。）

> **2026-08-30 還發生了一次憑證外洩處理**，7 把憑證和加密金鑰都換過了，
> 系統目前是通的。有兩個收尾沒做完（Google Drive 的 GCP 用戶端、Postgres 對外埠），
> 見「🔥 2026-08-30 憑證外洩處理」和待辦 0a。**動 `N8N_ENCRYPTION_KEY` 之前
> 一定要先讀那一節**——它曾經讓服務崩潰一小時。

先讀這一份，再讀 `CONTEXT.md`（詞彙表）和 `docs/adr/`（四份決策紀錄）。
完整規格在 `C:\Users\popo1\.claude\plans\n8n-prd-dreamy-teapot.md`——很長，
但**第七之二節（完整執行流程）和第十節（資料庫）是實作時的主要依據**。

---

## 這是什麼

使用者給一個廣泛的題目，系統找相關文獻，推導出**還沒被發表過**、值得投稿的研究方向。
PRD 定義了 S1–S11 共十一個階段，對應 n8n 的 W1–W10。

三個角色：n8n 排順序、`research-api`（FastAPI）做重活、Postgres 存所有決定。
n8n 用內網 `api.zeabur.internal` 呼叫 api，不經過公開網際網路。

---

## 現在做到哪

| 階段 | 狀態 |
|---|---|
| 第 2 階段 骨架 | ✅ Zeabur + Postgres + api + 備份 + 還原演練（真實資料 22 表 409 列） |
| **W2 文獻層** | ✅ 已發布，驗收通過。跑完會推 LINE 摘要 |
| **W-ALERT 失敗告警** | ✅ 已發布並實測（見下） |
| **W3 想點子** | ✅ 產出會寫進 `idea` + `novelty_check`，含 `method_sketch` 與 `required_variables`。素材已改成從 `/compute/harvest` 讀（`Load The Harvest` → `Shape The Material`），**寫死的 base64 已拿掉** |
| **W4 去重** | ✅ 正常運作（`922e3e3d` 20 組、執行 123 對 `a1b7e106` 再 20 組，全部 `distinct`）。它**只記配對、不記誰活下來**，那一半已用 `/compute/dedup/resolve` 補上 |
| **採集層** | ✅ 實跑通過，快取驗收見下 |
| **W6 可行性分級（S7）** | ✅ 端到端跑通並修正四項（執行 151，8 個方向 57 秒 **$0.059**）。三個守門全過，但書另計 |
| **W7 新穎性驗證（S8）** | ✅ 端到端跑通（執行 155，1 個方向 7 分鐘 **$0.061**）。四個守門全過 |
| **W8 唱反調迭代（S9）** | ⚠️ 已建、規則全部對著線上資料庫驗過，但**兩個模型還沒有真的打過一場**——這個專案沒有任何 A/B 級方向（看板是 `{A:0,B:0,C:1,D:7}`）。見下方「W8」 |
| **W9 最終報告（S10）** | ⚠️ 已建、資料層驗過（migration 012、`report` 表、三個端點），**但還沒實跑過**。實跑前修掉一個會讓它產出零引用報告的接縫，見下方「W9」 |
| **W10 撞題排程（S11）** | ⚠️ 已建、資料層驗過（migration 013、四個端點、`/compute/watch/list` 實測回 14 個查詢 44 個基線識別碼）。**預設未啟用**，也還沒實跑過 |
| 四個審閱介面 👁①–④ | ❌ 仍未建。**但前端規格已寫完**（`docs/frontend-spec.md` + `frontend-brief.md`，五個畫面），等 pen.dev 產出設計。見上方「🎨 前端」。註：👁①② 收進畫面 ③、⏸③④ 各自一個畫面 |
| 第 0 階段（修 domain-profile） | ✅ **已做完，本文件先前記錯**。skill 是 `v2.0.0`，四個修正都在 |
| 第 1 階段（16 項重驗） | ❌ 未做。PRD 寫「先驗證再蓋」，這一半仍是已知的偏離 |
| W1 領域框架 | ✅ 用 ECG 題目實跑通過（執行 142），`second_pack_forced: true`。已從 Sonnet 4.5 換到 **Sonnet 5**，實測 $0.0114／次 |
| **W5 錦標賽** | ✅ 滿場地實跑通過（執行 144，450 場 47 分鐘 **$2.661**）。漏判已查明並修掉（5.8% → 2.0%）。見下方「滿場地實跑」 |
| **W5B 錦標賽（批次）** | ✅ 冒煙測試通過（執行 200，40 場 10 分鐘 **$0.1387**）。判斷邏輯與 W5 逐字相同、已 diff 驗證。**滿場地還沒跑過**。見下方「W5B」 |

### 第 0 階段其實做完了（2026-08-28 更正）

本文件先前記載「第 0/1 階段未做」。**第 0 階段（修 domain-profile）實際上已完成**，
`~/.claude/skills/domain-profile/SKILL.md` 是 `version: 2.0.0`，PRD 第五節要求的
四個修正都在：

```
兩層架構        範式包（8）+ 領域模組（5）
路由自檢三問    Q1 主要主張靠什麼證明 / Q2 有沒有第二種東西也必須成立 / Q3 審稿人來自哪
Q2 強制第二包   neuro_18 就是死在這一條
盲點宣告        每個包的「這個包看不到什麼」
優點標記        每個包的「這個領域裡什麼算做得好」
```

**仍未做的是第 1 階段**：16 項 ScholarIdeas 重驗，確認領域落差有沒有收斂
（目前 0.489，要低於對照組的 0.344），以及神經科學不得再輸給對照組。

**這條記錯的代價是實際的**：不更正的話，下一個工作階段會重做一份已經存在的東西。

### W2 驗收數字（真的跑出來的，不是預估）

- `paper_reuse_rate` **1.00**（門檻 0.60）—— 同一題目第二次跑
- `within_run_overlap` 0.0682，兩次完全相同 —— 證明流程是決定性的
- 還原演練：22/22 資料表、409 列，**用真實資料**

---

## n8n 資產

工作流（Instance-level MCP 的 `Workflows exposed` 要勾到才叫得動）：

| ID | 名稱 | 狀態 |
|---|---|---|
| `cCni6Ds4qeKqI9s1` | **W2 文獻層** | 23 節點，已發布，表單 `/form/w2-literature`，`n8nUserAuth`。**整條鏈的預算上限在這張表單設**（欄位「預算上限」，預設 `2`）。已接預算護欄 |
| `WrV8vqhn4h65G5nE` | W-BACKUP | 啟用中，每日 `pg_dump` → Google Drive |
| `p3cbX6VXhxBHCskT` | W-DRILL | 還原演練 |
| `Nc6AjZZPSQZdoI6N` | W3-TEST 缺口組合推理 | 17 節點。素材已改成從 `/compute/harvest` 讀，題目與切點是表單欄位。表單 `/form/w3-directions`，`n8nUserAuth`。已接預算護欄 |
| `UobSYUAU2C4j38tY` | **W-ALERT 失敗推 LINE** | 已發布。W-BACKUP 與 W2 的 `errorWorkflow` 都指向它 |
| `5hjjy6sjMPBJaHGg` | W-LINE 通知測試 | ✅ 已驗證通過（執行 47） |
| `3kLQ9JvEdLBYnsWe` | **W-ADMIN research-api 診斷** | 表單觸發，下拉選任一 GET 端點。**這是從 Claude Code 呼叫 API 的唯一管道**（內網打不到），確認部署與讀回資料都靠它 |
| `Ob0O5ufSMHF3XZrU` | **W5B 錦標賽（批次）** | 26 節點。表單 `/form/w5b-tournament`。判斷邏輯與 W5 逐字相同（已 diff 驗證），只把 150 次即時呼叫換成一次 Message Batches。同樣的 token 半價。已接預算護欄 |
| `m0p2FLGSle4oU1OK` | **W10 撞題排程** | 17 節點。每日 08:00（Asia/Taipei）+ 表單 `/form/w10-watch`。**預設未啟用。** 檢索與比對免費，只有真的冒出新論文時才叫模型；被搶先才推 LINE |
| `FIWgMalCUagYln9M` | **W9 最終報告** | 10 節點。表單 `/form/w9-report`。八節缺一不可（資料庫 CHECK），每節至少 120 字元；引用寫入前逐筆比對，DOI 與 PMID 指向不同論文時兩個都不用 |
| `PSqvLA7DS4huNrSU` | **W8 唱反調迭代** | 19 節點。表單 `/form/w8-debate`。critic 是 Sonnet 5、辯護方是 Gemini 3 Flash。外圈一次一個方向，內圈一次一輪，**終止由 API 從紀錄算出來，不由模型自稱打完了** |
| `1PrxDrB7760V5vom` | **W7 新穎性驗證** | 13 節點。表單 `/form/w7-novelty`。十四輪、兩套以上術語，引用一律回頭比對實際檢索結果 |
| `xKB9e0sepZPaPTYM` | **W6 可行性分級** | 12 節點。表單 `/form/w6-feasibility`。輸入是本機產出的欄位清單，原始資料永遠不會到這裡 |
| `CqaYzcqjNNgI05AP` | **W5 錦標賽** | 20 節點。表單 `/form/w5-tournament`，`n8nUserAuth`。錯誤工作流指向 W-ALERT。執行 116 端到端通過 |
| `NRe3eCGX4bEDegvo` | W1 領域框架判定 | 6 節點。表單 `/form/w1-frame`。**Sonnet 5**，回傳帶 `cost` |
| `lzjAL1ONErAwLkoK` | W4 去重 | 見上：只記配對、沒記存活者，已用 `/compute/dedup/resolve` 補 |
| `LnIml88jxxjU5gSV` | W0 連線測試 | — |

**W3 目前的節點鏈**（`Direction Run Request` 是 form trigger，MCP 可直接執行）：

```
表單 → 載入素材(寫死) → Gemini 產方向 → 收集 → 查 MeSH 與論文數
     → Gemini 分組 → 掛回並驗證 → 數命中(三區帶) → 排序
     → Gemini 產方法草圖 → 掛回並驗證引用 → 寫入 DB
```

**執行 61 端到端驗證通過**（2026-08-28）：15 列存入，判決映射正確
（scooped 4／adjacent 8／no_prior_art 2／NULL 1），`code` 與 `method_sketch` 齊全。

**分組已兩次改變判決，兩次都朝安全方向**：
- `Afatinib` + `Gefitinib` 併成一個位置（同為 EGFR-TKI）
- `ROS1` + `RET` 併成一個位置 → `(ROS1 OR RET) AND Tomography` 查到切點前 63 篇、
  切點後 174 篇，判成 **ALREADY DONE**。不合併的話三個詞 AND 會是 0 篇，
  誤判成沒人做過。這就是設計上「錯誤方向要安全」的實例。

憑證 ID：

| ID | 名稱 | 型別 |
|---|---|---|
| `Pt36z1ZQwT84ARd5` | Research API Key | **httpTemplatedCustomAuth**（不是 httpHeaderAuth，本文件先前記錯） |
| `eCLOk0QB1CM31sM1` | Postgres | postgres |
| `tgUuL2avuGxFtJHi` | Google Drive | googleDriveOAuth2Api |
| `CZonQ0U8wL27CAKM` | Google Gemini (PaLM) | googlePalmApi |
| `ry2UKtnf3GjmXq8d` | OpenAI | openAiApi |
| `dAytbkY0WTl24Yjm` | LINE Messaging API | httpHeaderAuth |
| `cBicCMYnLzAZQyae` | **Anthropic account** | anthropicApi。W5 的兩個判斷節點用它 |

---

## 程式碼地圖

```
lib/search.py      MeSH RDF 展開（四路 UNION）、Europe PMC、render_query 分方言
lib/concepts.py    從摘要抽概念：最長匹配、UMLS 語意型別過濾、背景詞頻
lib/db.py          upsert、start_run（正規化題目重用專案）、ingest、health_metric
                   save_directions（寫 idea + novelty_check，判不了存 NULL）
lib/verify.py      機械查核：同義詞展開、單詞冷門閘門、三區帶
lib/triage.py      去重／賽程／Elo 的實作（ops.py 是它的 HTTP 包裝）
tools/build_mesh_dict.py    31,110 descriptor + 295,049 SCR = 807,239 詞，13.4MB
tools/build_background.py   11,000 篇 2005–2015 摘要算背景詞頻
tools/harvest_gaps.py       標題概念 + Discussion 缺口句
tools/verify_directions.py  lib/verify.py 的 CLI 前身，邏輯已搬進 lib
lib/harvest.py     缺口採集：從 paper 快取讀論文、抓 Discussion、存 paper_section
                   **PMCID 要能用 DOI 解析，不能只靠 PMID**——PubMed 被封鎖，
                   快取裡的論文多半只有 DOI。只認 PMID 的版本 40 篇一篇都沒查
migrations/002_w2_literature_layer.sql   已執行
migrations/003_harvest_layer.sql         已執行（2026-08-28，22→24 表）
```

### 採集層驗收（2026-08-28，40 篇論文）

```
第一次（只認 PMID）   全文  0   缺口句  0    2.1 秒   ← 一次外部請求都沒發
第二次（DOI 解析）    全文 17   缺口句 19   87.4 秒   ← 真的在抓
第三次（讀快取）      全文 17   缺口句 19    1.8 秒   ← 全部命中，結果相同
```

**87 秒 → 1.8 秒、結果完全相同**，這是把採集做成 job 並快取全文的整個理由。

**注意第一次和第三次都是約 2 秒，意義卻完全相反**：一個什麼都沒查，一個全部命中。
光看執行時間分不出來，所以 `harvest.result.lookup` 會記 `n_resolved` /
`n_without_identifier` / `n_with_fulltext`——採集找不到東西時，要說得出是哪一種找不到。

40 篇裡 17 篇有開放全文（42%），與 `harvest_gaps.py` 當初實測相符（60 篇 34 篇有 Discussion）。

### migration 怎麼跑

**`POST /admin/migrate`**，不是把 SQL 抄進 n8n 節點。

```json
{"file": "003_harvest_layer.sql", "expect_database": "research"}
```

端點讀 repo 裡 `migrations/` 的檔案執行，所以**檔案就是唯一的事實來源**——抄進工作流會變成兩份，而手抄的差異不會報錯。

`expect_database` 是必填且無預設：n8n 與本專案共用同一台 Postgres、各自一個資料庫，
**migration 下錯地方是靜默的而且很難回復**，所以這道檢查做成結構性的，不靠人記得。
回傳帶執行前後的表數，冪等地什麼都沒做和真的建了東西分得出來。

用 **W-ADMIN** 呼叫（它現在能發 POST）。「DB工具」工作流沒開放 MCP 存取，用不了。

**`applied: true` 不代表它改到了東西。** 回傳只說 SQL 跑完了、沒有丟例外；
`RAISE NOTICE` 不會回傳出來，表數對資料清理也不會變。所以做完之後
**一定要另外讀一次來確認**——011 那次就是靠 `/compute/debate` 回
`n_rounds: 0` 才知道真的刪掉了，而不是靠 `applied: true`。

### API 端點

```
GET  /healthz                      不需金鑰
POST /compute/search/query         多來源檢索與合併去重
POST /compute/search/expand        概念展開 + 查詢規劃
POST /compute/search/ingest        存檢索結果，回報重用率
GET  /compute/search/corpus        文獻快取大小
POST /compute/search/vocab         單詞彙展開
POST /compute/search/chain         引用鏈遍歷
POST /compute/run/start            建立或沿用專案與跑動
GET  /compute/run/{id}/done-queries
POST /compute/run/finish
POST /compute/verify/terms         每個詞的 MeSH 分類、同義詞、論文數
POST /compute/verify/directions    數命中數判新穎性，含三區帶
POST /compute/ideas/save           寫 idea + novelty_check
POST /compute/triage/dedup         近重複候選配對
POST /compute/triage/pairs         賽程，含批次隔離
POST /compute/triage/elo           Elo 與錨點校準
GET  /admin/config /admin/dbstats /admin/backup
POST /admin/restore-drill
```

**2026-08-28 新增**：

```
GET  /compute/projects              專案清單，含論文數與方向數
GET  /compute/projects/{id}/runs    某專案的跑動
GET  /compute/ideas                 方向 + 最新一次 novelty_check
POST /compute/ideas/save
GET  /compute/dedup                 候選配對，兩個完整題目都併進來
POST /compute/dedup/save
POST /compute/harvest/start         非同步採集，立刻回 id
GET  /compute/harvest/{id}          輪詢採集結果
GET  /compute/harvest?project_id=   最近一次採集
POST /admin/migrate                 見上
GET  /compute/packs                 路由選單（摘要，不是整包）
GET  /compute/packs/{key}           單一範式包／領域模組全文
POST /admin/sync-packs              把磁碟上的包灌進 skill_prompt
GET  /compute/prompts               目前生效的提示詞版本
POST /compute/frame/save            寫 project.domain_frame
GET  /compute/frame?project_id=     讀領域框架
GET  /compute/anchors[?origin=]     校準錨點
POST /compute/anchors/save
POST /admin/load-anchors            灌 repo 內附的 54 筆 ScholarIdeas 錨點
POST /compute/dedup/resolve         決定重複裡誰活下來（dry_run 給審閱介面看）
POST /compute/dedup/keep            人工指定存活者，推翻規則（👁① 的原語）
POST /compute/dataset/save          上傳本機產出的欄位清單（會擋帶 rows 的）
GET  /compute/dataset?project_id=   資料清單
POST /compute/profile/save          研究背景檔，逐版本存，舊版不覆寫
GET  /compute/profile?project_id=   目前版本，沒有就明說沒有
POST /compute/feasibility/save      A/B/C/D，B/C 沒去路會被拒
POST /compute/novelty/search        批次跑檢索輪次，論文附在找到它的那一輪
POST /compute/novelty/save          對抗式判決，證據撐不住的會被拒
GET  /compute/novelty?project_id=   最新一次對抗式檢查
GET  /compute/frame?section=A,B     範式包的指定段落（可多個，逗號分隔）
GET  /compute/feasibility?project_id=  分級看板，分組但不重排
GET  /compute/ideas/live            場上的方向，不含被合併掉的
POST /compute/tournament/start
POST /compute/tournament/matches    對局結果（錨點對局也存這裡）
POST /compute/tournament/rankings
GET  /compute/tournament/{id}       名次，每個參賽者的完整題目都併進來
```

`GET /admin/config` 現在會回 `build.routes`：**線上實際存在的路由清單**。
用它判斷推送有沒有部署完成，不要看時鐘——建置要三到六分鐘，而且推測錯過。

`GET /compute/ideas` 會把**最新一次的 `novelty_check` 併進來回傳**（verdict、rounds、
coverage_limits）。刻意如此：一個方向如果只有敘述沒有判決與警語，那正好是最會誤導人
的那一半——敘述永遠讀起來合理，警語才是決定該信多少的東西。
參數 `project_id` / `run_id` / `status` / `limit`，至少要給前兩者之一。

`GET /compute/dedup` 同理併進兩個**完整題目**，不是 id。PRD 的顯示規則不是裝飾：
判斷兩個方向是不是同一個，一定要兩個都讀得到，他們實跑時發現代號與截斷標題根本判不了。

`GET /compute/feasibility` 的 `assessments` **現在照錦標賽名次排**（2026-08-30 修）。
先前是 `DISTINCT ON (f.idea_id)` 的 uuid 順序，而 W7 和 W8 的 `Pick The Directions`
都寫著「取清單的頭就是取名次最高的」——兩邊都在騙自己，而且兩邊都會對那個「頭」
花錢（一次新穎性驗證、一場兩模型辯論）。現在 join 該專案**最新一場**錦標賽的
`ranking.rank`，沒有名次的排最後而不是最前。

**實測（執行 168）**：修好之後順序是 3, 4, 6, 7, 8, 9, 10, 12。
先前排在最前面的是 `0788a78a`——**它的名次是第 10**，排第一純粹因為 uuid 排最前。
W7 就是這樣挑到它的。

`GET /compute/debate/state?idea_id=` 回傳辯論現況**加上 critic 可以引用的論文池**
（該方向最新一筆 `adversarial` 檢查裡實際檢索回來的論文，最多 40 篇）。
`current_statement` 是最後一輪的修訂，`original_statement` 永遠是原文——
漂移一律對照後者。

---

### W5 錦標賽（`CqaYzcqjNNgI05AP`）

節點鏈：

```
表單 → 去重定案 → 讀場上的方向 → 讀錨點 → 選錨點(剝掉等級)
     → Sonnet 5 縮減場地 → 套用縮減 → 開賽 → 產生賽程 → 分批
     → 迴圈｛Sonnet 5 判一批 → 收判決｝→ 存對局 → Elo → 存名次
     → 守門 → 推 LINE
```

**四個設計決定，改之前先看理由：**

1. **裁判看不到錨點等級，也分不出誰是錨點。** 等級在 `Choose The Anchors` 就被剝掉，
   一路到 `Score The Tournament` 才從資料庫重新讀回來。這是 ScholarIdeas 自己的規定。
   **不要為了「省一次查詢」把等級留在賽程回應裡**——`/compute/triage/pairs` 本來就是
   那樣寫的，已經改掉了（見上方 `competitors`）。
2. **錨點強弱各半，不足就拋錯。** 只有單邊等級的話沒有下界，計分那步會拒絕宣稱校準帶
   （回 `calibration: null`），整場比完才發現就太晚了。
3. **縮減場地只准兩個理由**，資料庫 CHECK 也只收那兩個。工作流多做一層：
   模型回了第三種理由時**不淘汰、照樣留下**並記進 `unrecognised_grounds`。
   寫入會在開賽之後才發生，讓資料庫擋等於整場白跑。
4. **判不出來的對局存 `winner: null`，不猜。** 計分會跳過。猜一個贏家等於用不存在的
   證據去動 Elo 分數。

**已知的殘留洩漏**：錨點沒有文獻計數、方向有，光憑「有沒有數字」裁判就分得出來。
提示詞照實說明「沒有計數只代表沒人跑過那個查詢，跟新不新無關」，並要求單邊有計數時
第二判準直接視為平手。這跟對照組實驗一致——那些計數本來就幾乎沒有鑑別力，
本來就不該被重壓。**要真正修掉得對錨點也跑一次機械查核，而那個查核已經被證明沒用**，
所以不值得。

### W1 實跑通過，並修掉三個一起發生的問題（2026-08-29）

題目：「用深度學習從單導程 ECG 偵測無症狀心房顫動，並驗證它在基層診所人群的可用性」。
挑這個是因為它應該逼出 Q2 有答案——主要主張是模型效能，但**可用性宣稱**也必須成立。

結果（執行 142）：

```
q1 computational   模型在定義好的任務上打敗基準
q2 observational   可用性宣稱要靠有代表性的世代驗證；抽樣有偏誤的話
                   benchmark 再漂亮，可用性宣稱仍然不成立
q3 physiological-signal-ai
second_pack_forced true      pack_versions 齊全      confidence high
費用 輸入 1869 / 輸出 769 token = $0.0114
```

**Q2 強制第二個包這條規則成立了。** 這是 HANDOFF 先前列為待驗的那一項。

同時修掉三個必須一起改的東西：

1. **模型還停在 `claude-sonnet-4-5-20250929`。** 便利貼寫著「目前用 Gemini 暫代，
   憑證加了之後換掉」——憑證加了、節點也換成 Anthropic 了，但換成 4.5 而不是
   PRD 第十一節定的 Sonnet 5。已改。
2. **`temperature: 0` 還在。** Sonnet 4.5 收得下，Sonnet 5 會直接 400。
   換模型前不拿掉就會炸。已拿掉。
3. **`decided_by` 在程式碼裡寫死成 `claude-sonnet-4-5-20250929`。**
   換模型時沒跟著改的話，**每一份框架都會署名一個沒有參與判定的模型**。
   已改成從回應的 `model` 欄讀。會說謊的來源欄位比沒有更糟。

`Route With Sonnet` 的 `simplify` 也關掉了，所以 `Build The Frame` 會回傳 `cost`。
那個 `cost` **刻意放在 frame 外面**——`Save The Frame` 只送 `project_id` 與 `frame`，
一次跑動花多少錢不屬於「當初判了什麼」這份不可變紀錄。

### Anthropic 節點的兩個坑（2026-08-29 實測）

1. **`claude-sonnet-5` 不接受 `temperature`。** 送了會回
   `Bad request` + `temperature is deprecated for this model`，整個節點失敗。
   參數要**整個不存在**，設成 0 或 1 都沒用。W5 的兩個判斷節點都已拿掉。
   代價是輸出的一致性只能靠提示詞，不能靠 `temperature: 0`。
2. **Anthropic 節點沒有 Gemini 那個 `jsonOutput` 開關。** 回覆是純文字，
   所以 W3 那套搶救碼（挖巢狀字串、讀第一個平衡物件、任意深度撿完整物件）
   照抄過來是必要的，不是防禦性多寫。

### W5B 錦標賽（批次）：省一半，冒煙測試通過（2026-09-02，執行 200）

`Ob0O5ufSMHF3XZrU`，26 節點。**W5 沒有被改動**——W5B 是另一個工作流，
因為 W5 能跑、守門全過、費用有實測，而批次版是未驗證的。兩個並存才能
拿同一個場地做 A/B。

#### 判斷邏輯逐字相同，而且是用程式驗的

裁判提示詞從兩個工作流各自抓回來 diff：**3383 字元、38 行、byte for byte 相同**。
「我有小心複製」不算檢查。

**thinking／effort 刻意沒動。** 執行 116 和 121 一次動了兩件事，結果哪一邊都
歸因不了。這次只改交付方式，排名如果不一樣就知道是批次造成的。

#### 冒煙測試實測（5 方向 + 2 錨點 = 40 場）

```
批次      msgbatch_01T3BB3tFXSFa6g8xuD162CF   14 請求、0 出錯
時間      9 分 54 秒（含輪詢）
判決      37 / 40
翻轉率    0.176（門檻 0.05–0.20）✅
校準帶    5/5 ✅   錨點無反轉 ✅
快取      cache_read 13,715 token — **真的命中**
費用      $0.1387，每場 $0.00347
```

3 場未判決不是批次的錯：`n_errored_requests: 0` 證明傳輸乾淨，是模型漏寫
`winner` 欄位，跟 W5 修正後殘留的 2.0% 同一個失效模式（40 場樣本太小，無顯著差異）。

#### ⚠️ 更正一個我先前給錯的預測

我說滿場地批次會是 **$1.33**。這次每場 $0.00347 × 450 = **$1.56**，因為
每場的輸出 token 比 W5 那次多（637 vs 485）。

**可靠的結論只有「同樣的 token，批次是一半價」**——這個驗過了。
每場用多少 token 會隨場地變動，滿場地實際落在 **$1.33–$1.56**，要跑過才知道。

#### 三個批次特有的處理

- **靠 `custom_id` 對回**：JSONL 順序不保證，照位置讀會把判決配到錯的一批上
- **多一條守門「沒有請求出錯」**：一個 errored 請求一次吃掉三場，而未判決數
  分不出它跟「模型沒回答」的差別
- **快取是實測**：`cache_control` 掛了，但前綴太短時 API 安靜地不快取也不報錯，
  所以守門帶 `cache_worked`

#### 尚未處理的風險

**批次很久才完成的話，n8n 執行可能先逾時。** `batch_id` 記在 `Submit The Batch`
的輸出裡，所以結果不會消失，但**目前沒有「事後撈回結果」的路徑**。
這次 40 場花了 10 分鐘；450 場沒跑過。

### 預算護欄（2026-09-02）：PRD 三個貫穿機制之二，先前一行程式碼都沒有

`run.token_budget` / `token_spent` / `token_usage` 從第一天就在 schema 裡，
**但整份程式碼沒有任何一行碰過它們**。所以在此之前，這個系統沒有任何東西
會攔住失控的花費——一個寫錯的迴圈可以一路燒到帳單上才被發現。

migration 014 加了 `run.usd_budget` / `usd_spent`，以及 `token_usage` 的
`stage` / `cache_read_tokens` / `batch`。

#### 四個設計決定

**單位是美元不是 token。** 不同模型每個 token 差五倍（Opus 5 輸出 $25／
Haiku 4.5 $5），所以「還剩多少 token」回答不了唯一有意義的那個問題。
token 數繼續記在 `token_usage` 供分析。

**價目表只放在 `lib/budget.py`。** 十個工作流各帶一份副本，就是十份會走樣的
副本，而**走樣的副本不會報錯，只會安靜地算錯**。工作流回報 token，伺服器算錢。

**沒有價格的模型直接拒絕，不估也不記 0。** 一個對未定價模型記 $0 的跑動，
看起來跟一個便宜的跑動一模一樣——護欄會放行它本來要擋的那件事。

**檢查問的是「這個階段可不可以開始」，不是「是不是已經超支」。**
後者會讓一個 $2.66 的錦標賽在只剩 $0.10 時照樣起跑。所以
`GET /compute/run/budget?run_id=&estimate=2.66` 要帶預估值，塞不下就在
**開始前**拒絕。檢查點在階段邊界，不在階段中間——在第 300 場砍斷錦標賽，
你會付掉三分之二的錢換一個沒有意義的半套排名。

#### 價目表釘在真實帳單上

`tests/test_budget.py` 用執行 144 的實際數字（151 次呼叫、230,925 輸入、
219,917 輸出、Sonnet 5）驗算，得到 **$2.66102**，實測是 $2.661。
**一份「看起來合理」的價目表正是護欄失效的方式**，所以它被釘在一張真的帳單上。

#### 端點

| | |
|---|---|
| `GET /compute/run/budget?run_id=&estimate=` | 階段開始前問「可不可以跑」 |
| `POST /compute/run/spend` | 階段結束後回報用量，回傳有沒有超支 |
| `POST /compute/run/budget` | 設定或調高上限（調高會解除 `paused_budget`）|
| `GET /compute/run/quote?model=&input_tokens=&output_tokens=` | 試算即時／批次價差，不寫入 |
| `POST /compute/run/start` | 多了 `usd_budget` 參數 |

超支 → `run.status = 'paused_budget'`。

#### 一個實跑才抓得到的低估（執行 200 之後修）

W5B 第一次批次跑完，工作流自己算 **$0.1387**、護欄記 **$0.137379**。
差額 $0.001318 **全部**來自 1,055 個寫入快取的 token——`budget.py` 沒有這一項。

金額很小，但**方向是固定的**：快取寫入比一般輸入**貴** 1.25 倍，所以漏掉它
一定是往低估錯。而護欄唯一不能犯的錯就是報得比實際低。

migration 015 加了 `token_usage.cache_write_tokens`，`price` / `quote` /
`record_spend` 與端點都串起來。實測 `/compute/run/quote` 用同一組 token 現在回
**$0.138697**，跟工作流對上了。測試把它釘在那次實跑上。

#### 十個工作流都接上了（2026-09-02 完成）

形狀一律是兩個節點：開頭一個 `May We Afford This`
（`GET /compute/run/budget?enforce=true&estimate=…&project_id=…`，`enforce=true`
會在塞不下時回 402 直接中止），結尾一個 `Record The Spend`
（`POST /compute/run/spend`，`onError: continueRegularOutput`——
**記帳失敗不可以把一次成功的跑動標記成失敗**）。

| 工作流 | 階段預估 | 來源 |
|---|---|---|
| W1 領域框架 | $0.011 | ✅ 實測 |
| W2 文獻層 | $0.02 | ~估 |
| W3 想點子（缺口組合） | $0.12 | ~估（三次 Gemini） |
| W4 去重（S5） | $0.05 | ~估 |
| W5B 錦標賽（S6） | 場數 × $0.00295 | ✅ 實測 |
| W6 可行性分級（S7） | $0.059 | ✅ 實測 |
| W7 新穎性驗證（S8） | $0.061 × 方向數 | ✅ 實測 |
| W8 唱反調（S9） | $0.04 × 輪 × 方向 | ~估 |
| W9 最終報告（S10） | $0.07 × 方向數 | ~估 |
| W10 撞題巡查（S11） | $0.05 | ~估 |

**上限在 W2 設，因為 W2 是整條鏈的入口。** 別的工作流表單都收 `project_id`，
只有 W2 自己呼叫 `/compute/run/start` 建專案——所以表單多了一格「預算上限」
（預設 `2`，留白＝沒有護欄），值透過 `run/start` 的 `usd_budget` 參數寫進
`project.usd_budget`。也因此 W2 的檢查點插在 `Start Run` **之後**，不是接在
觸發器後面：接在前面的時候還沒有專案可以問。

#### 一個接的時候才發現的坑：`simplify: true` 會讓記帳記 0

W2 的 `Split Topic Into Concepts`、W3 的三個 Gemini 節點、W4 的兩個，
原本 `simplify` 都是開的（W3 那三個是沒寫、吃預設值）。
**開著就整塊 `usageMetadata` 都不會出現**，記帳只能記 0 ——
而對護欄來說，一次記成 $0 的跑動跟一次便宜的跑動長得一模一樣。全部改成 `false`。

下游那些 Code 節點不受影響：它們的 `dig()` 本來就是遞迴挖任意形狀的
（當初為了吃掉模型亂加的括號寫的），原始回應照樣挖得到。

W3 另外多一個 `Add Up The Tokens` 把三次呼叫加總，並且**把
`thoughtsTokenCount` 算進輸出**——Gemini 的思考 token 是照輸出計價的，
漏掉它就是系統性低估。三個節點加起來是 0 時它會標 `usage_missing: true`，
而不是安靜地送一筆 $0 出去。

#### 兩個仍然是估的地方

W8 / W9 / W10 / W4 的預估**沒有實測**，因為那幾個的模型段從來沒跑過。
第一次真的跑完之後要回頭把上表的數字換成實測值——
**預估偏低的護欄，擋不住它存在的理由**。

W3 的記帳掛在 `harvest_project_id` 上，也就是被檢查的那個專案。
但 `Save The Directions` 是用 `topic` 呼叫 `/compute/ideas/save`，
方向可能落在另一個專案——**這個不一致是既有的，不是護欄造成的**。
現在的取捨是讓「檢查誰」和「扣誰的錢」是同一個專案，這一點不能歪。

### 階段自動接續（2026-09-02）：PRD 三個貫穿機制之三

`run.pause_after` 和 `run.auto_advance_to` 從第一天就在 `schema.sql` 裡，
**沒有任何一行程式碼碰過**——跟預算護欄之前一模一樣。在此之前每一段都要人去
點下一張表單。

#### 鏈是這六段

```
W4 去重 ──①跑過去──▶ W5B 錦標賽 ──②跑過去──▶ W6 可行性 ──⏸③停──▶
W7 新穎性 ──▶ W8 唱反調 ──⏸④停──▶ W9 報告
```

`lib/chain.py` 的 `STAGE_PLAN` 是**唯一**知道這個順序的地方。順序複製到六個
工作流裡，就是六份會走樣的副本，而走樣的副本會安靜地跳過一段。

**W1／W2／採集／W3 刻意不在鏈上。** 不是還沒做，是不該做：
**W2 中間有一張人工確認檢索概念的表單**（`Confirm Concepts`，等 30 分鐘逾時），
自動跑進去只會產生一個掛著等人、然後死掉的執行——正是 PRD 設計一要避免的。

**③④ 停、①② 不停**（使用者 2026-09-02 決定）。理由是下游成本：分級決定哪些
方向要花 $0.061 一個去驗，辯論是報告的原料。去重和排名事後看得懂、也重跑得起。

#### 四個設計決定

**鏈的狀態存在 `run` 列裡，不存在掛著的執行裡。** 一個停在那裡等人的工作流，
重開機就死、會逾時、而且把工作一起帶走。所以階段寫完結果就結束，
下一段是**另一個人撿起來的一列**。停電最多賠掉正在跑的那一段。

**鏈不重算預算。** 每個階段的工作流開頭本來就有自己的 `May We Afford This`，
帶著它看得到的場地大小算出來的預估。在這裡再算一次就是第二份會走樣的副本。
所以鏈只問粗的那題（「還有沒有錢」），精確的那題留給階段自己拒絕自己。

**派工的認領是一句原子的 UPDATE，不是「先讀再寫」。** 兩個節拍差一秒讀到
同一列就會把同一段啟動兩次，**而錦標賽跑一次是 $2.66**。

**排序規則抽成純函式 `decide_next`，`tests/test_chain.py` 離線釘住。**
理由跟 `debate.decide_termination` 同一條：只能靠花錢實跑才驗得到的規則，
實際上不會被驗到。

#### 端點

| | |
|---|---|
| `POST /compute/chain/start` | 把專案放上鏈，預設從鏈頭 `dedup` |
| `POST /compute/chain/advance` | 階段跑完自己回報，回傳下一段是什麼（接受 `run_id` 或 `project_id`）|
| `POST /compute/chain/claim` | 派工用。**是 POST 因為它會寫**——認領和讀取是同一個動作 |
| `GET /compute/chain/state` | 這個專案每一段的狀態、卡在哪 |
| `GET /compute/chain/plan` | 鏈本身：順序、工作流 id、哪幾段會停 |
| `POST /compute/chain/resume` | 放行卡在審閱點或預算的鏈 |
| `POST /compute/chain/pause` | 在鏈走到之前標「這裡停一下」 |

#### migration 017 不加欄位，加兩個讓做錯變成不可能的約束

- `run_one_active_chain_stage_per_project`：同一專案同一階段只能有一列在
  `pending`／`running`。索引只涵蓋鏈上那六段，**W2 的 `lit_search` 不在裡面
  是刻意的**——鏈在跑的時候另外開一次文獻檢索是合理的
- `run_auto_advance_is_a_known_stage`：`auto_advance_to` 拼錯不會報錯，
  只會讓鏈**安靜地走到死路**，而那看起來跟「本來就跑完了」一模一樣

**六個階段名在 `STAGE_PLAN` 和 migration 017 各有一份，測試會比對兩邊。**

#### n8n 這一半

新工作流 **W-CHAIN 階段派工 `UJiYf5NJRM0uVXew`**（8 節點，**已啟用**）。
兩個觸發器：階段跑完自己來敲的 Execute Workflow Trigger，以及十分鐘一次的
排程安全網（撿預算調高、審閱放行、認領了但沒起來三種卡住）。
`waitForSubWorkflow: false`——等的話六段會巢狀在同一次執行裡。

六個階段工作流各多四個東西：`Called By The Chain`（Execute Workflow Trigger，
**表單觸發器叫不動，所以一定要第二個入口**）、一個正規化節點、
`Tell The Chain`、`Kick The Dispatcher`。

**接線時發現的省事做法：`renameNode` 不會改寫運算式引用。** 所以把表單觸發器
改名成 `<X> Form Request`，再讓正規化節點接下**原本那個名字**，下游所有
`$("Grading Request")` 之類的具名引用就自動指向正規化節點，一行 Code 都不用重送。
W6／W7／W8／W9／W5B 都是這樣接的。**只有 W4 是例外**——它先接好了，
正規化節點叫 `Chain Or Form`，兩處 jsCode 是整段重送改的。

**表單的預設值要在正規化節點裡重寫一次。** 從鏈進來時沒人填表單，
而 `max_ideas`／`max_rounds` 缺了會讓預算預估算成 **0**——
**預估 0 的階段，護欄一定放行。** W5B 的 `max_ideas` 另外要小心：
`0` 是「不限」的真值，被 `|| 8` 之類吃掉就會把滿場地變成冒煙測試，
差別是 $1.56 對 $0.12。

#### ✅ 控制流程整條走過一遍（2026-09-02，零成本）

在 `ed3f8f68`（本來就是預算護欄的探測專案）上把整條鏈的控制邏輯走完，
**沒有呼叫任何模型，花費是零**：

| 驗的東西 | 結果 |
|---|---|
| `chain/plan` | 六段順序、⏸③⏸④、六個工作流 id 全對 |
| **唯一索引真的擋得住** | 重複排 `dedup` → **400**「already queued or running」 |
| 原子認領 | 第一次回 1 筆、**第二次回 0 筆** |
| `params` 往下傳 | 認領回來同時帶 `run_id`（呼叫者給的）和 `project_id`（`_queue` 自動注入的）|
| `advance` 一般情形 | `dedup` → 收成 `done`、排出 `tournament` |
| **⏸③ 真的會停** | `feasibility` → `awaiting_review`，**`next_stage: null`**，訊息指名下一段是 W7 |
| `chain/state` | `parked` 正確指向 `feasibility` / 審閱點 ③ |
| `resume` | 放行後排出 `novelty`，**沒有在同一點再停一次** |

**驗唯一索引的方式是直接去做那件不該被允許的事，不是查系統目錄。**
`applied: true` 從來不代表約束存在（本文件記過），而「重複排會被 400 擋下來」
證明的是行為。

探測列已經收乾淨：最後那筆 `novelty` 用 `advance` 加 `ok: false` 收成 `failed`
（失敗的階段不排下一段，所以不留 `pending`），`error` 欄寫明是探測。
收完再認領一次確認**全庫 0 筆待辦**，然後才啟用 W-CHAIN。
**這個順序不能顛倒**：留著 `pending` 就啟用，十分鐘內 W7 會真的跑在探測專案上。

#### 實跑才抓得到的 bug：psycopg3 沒有 `IN %s`

第一次呼叫 `/compute/chain/claim` 直接 500：

```
SyntaxError: syntax error at or near "$1"
LINE 1: ...WHERE status = 'pending' AND stage IN $1 ORDER B...
```

psycopg2 會把 tuple 展開成 `IN` 清單，**psycopg3 不會**——它把整個參數當成
一個值送出去。`claim`／`advance`／`state`／`resume`／`set_pause` 五處我全寫錯，
也就是**除了 `start` 以外的鏈端點全都是壞的**。改成 `= ANY(%s)` 配 list。

**這是離線測試結構上抓不到的**：沒有資料庫，SQL 字串永遠不會被 Postgres 剖析。
`tests/test_chain.py` 驗的是排序規則，它看不到這個。

`grep` 過了，**其他 lib 檔本來就都用 `ANY(%s)`**，是 `chain.py` 一個人寫錯。
以後在這個專案寫多值條件，一律 `= ANY(%s)`。

#### ✅ n8n 那一半也驗過了，而且抓到三個真的問題（2026-09-02，零成本）

驗法：**把專案預算設成 $0.002**——剛好夠通過排隊時的粗檢查，但遠低於 W4 的
$0.05 預估。於是正規化節點會執行（看得到它實際輸出什麼），
下一個 `May We Afford This` 帶 `enforce=true` 回 402 把工作流擋掉，
**模型一個都沒被呼叫**。

**這個驗法是這一輪最值得複製的東西**：直接跑真題目的話，下面第三個問題會
一路綠燈通過，沒有人會發現。

##### 問題一：六個階段工作流當時沒發布

`Start The Stage` 回 `Workflow is not active and cannot be executed`。
**Execute Sub-workflow 在 production 執行裡叫不動未發布的工作流。**
六個都發布了。

##### 問題二：派工失敗是無聲的

`Start The Stage` 設 `onError: continueRegularOutput`，所以問題一發生時
**W-CHAIN 回報「成功」，而 `run` 停在 `running` 再也沒人碰**——階段沒發生，
鏈默默斷掉，`chain/state` 看起來像「還在跑」。

`onError` 不能拿掉：同一批認領到多筆時，一筆派工失敗不該連累其他筆。
所以改成 `Which Ones Did Not Start` 把錯誤撿出來，回報
`/compute/chain/advance` 加 `ok: false`，讓那一段被標成 `failed` 並寫下原因。

##### 問題三：`run_id` 撞名（最危險的一個）

**Execute Workflow Trigger 的 passthrough 把整個項目扁平送進去**，
所以派工的記帳欄位跟階段的領域欄位並排。實測收到的形狀：

```json
{ "chain_run_id": "…", "project_id": "…", "stage": "dedup",
  "label": "…", "workflow_id": "…",
  "params": { "run_id": "…", "project_id": "…" } }
```

原本頂層那個叫 `run_id`，而它的意思是**鏈為這個階段建的記帳列**；
`params.run_id` 才是**要處理的那次研究跑動**。正規化節點的 `pick()` 偏好頂層，
所以挑到記帳列。

後果：W4 拿它去查 `/compute/ideas?run_id=…`，**查到 0 筆、去重 0 組、
回報成功**——綠燈、沒有錯誤、什麼都沒做。**W7 和 W9 更糟**：
它們會把這個 id 寫進 `novelty_check` 和 `report`，存下錯誤的歸屬。

三道修法：

1. **源頭改名**：`Spread The Claims` 現在送 `chain_run_id`，衝突不存在了
2. **六個正規化節點一律 `params` 優先**——`params` 是內容，頂層是信封。
   規則六個一致，是為了擋住「以後有人往派工 payload 加欄位」這一類意外
3. **W4／W5B／W7／W9 額外直接擋掉** `run_id === chain_run_id`。
   這個錯誤的後果是看不見的，所以值得讓它「不可能發生」而不只是「已修好」

修完重跑，正規化節點輸出 `run_id: SHAPE-PROBE-9F3A`（`params` 裡的值），確認。

##### 順手修掉的：不是 uuid 的 id 會回 500

探測用的假 `run_id` 讓 `/compute/run/budget` 回 **500 加一段裸的 Postgres
`InvalidTextRepresentation`**。這兩個 id 都是人手貼進 n8n 表單的，
所以格式錯誤是常態不是例外，而 **500 讀起來像「服務壞了」，事實是「那不是一個 id」**。
`budget.project_of` 現在先驗 uuid 格式，回 400 並說明 run id 長什麼樣。

##### 探測殘留

都在 `ed3f8f68`（`budget guardrail probe 2026-09-02`）這個專案上，
`run.error` 每一列都寫明是探測、沒有呼叫任何模型。
**這個專案的預算刻意留在 $0.002**，這樣它永遠跑不動任何要花錢的階段。

#### 部署當時卡住了（已解決，留著是因為它會再發生）

**程式碼推上去了（`35aa354`），但連續三次推送被 Zeabur 互相取消掉了**——
本文件早就記過「快速連續推送前一次會被取消」，而這次連推三次正好踩滿。
使用者手動按重新部署之後，Zeabur 開始建 `35aa354`（分支 `main`，狀態正確）。

**一個判讀陷阱：建置中的時候，舊容器照常服務。** 所以「API 活得好好的但路由
還是舊的」不是故障，是正常行為——不要因為 API 回得動就以為部署完了。

#### 怎麼一句話判斷線上跑的是哪個 commit

`/admin/config` 的 `build.n_routes` 就是答案，因為路由集合每個 commit 都不同：

| n_routes | 對應 commit |
|---|---|
| 72 | `f54d88a`（以及 `b1e5ad0`、`8329a44`）— 預算護欄做完、**階段接續之前** |
| **79** | `6511eed` / `2062ad0` / `35aa354` — 階段接續（多七條 `/compute/chain/*`）|

（自己算：`git show <commit>:main.py` 抓 `@app.(get|post)("...")` 的相異路徑，
再加 4——`/docs`、`/docs/oauth2-redirect`、`/openapi.json`、`/redoc` 是自動加的。）

**實測回 72，所以線上是 `f54d88a`，三個 chain commit 一個都沒上。**

#### 真正的原因：Dockerfile 有一步要連外網，而它連不到

建置紀錄的結論：

```
#6 1032.3 curl: (56) Recv failure: Connection timed out
#6 ERROR: process "/bin/sh -c set -eux; apt-get update; ... curl -fsSL
          https://www.postgresql.org/media/keys/ACCC4CF8.asc ..."
```

抓 PGDG 簽章金鑰**卡了 1032 秒（17 分鐘）才逾時**。第一次推送那個「17 分鐘
沒動靜」多半是同一個死法。

**這個失敗特別難認，有兩層偽裝**：卡住的時候看起來只是建置慢；失敗之後舊容器
繼續服務，所以 API 一直活著、只是路由是舊的。**兩層加起來就是「部署卡住」的
外觀，而實際上是建置壞了。**

修法不是重試，是把那一步拿掉。當初加 PGDG 是因為 base image 是 Debian 12
（bookworm，預設 PostgreSQL 15），而 `pg_dump` 不能比伺服器舊。
**現在 `python:3.13-slim` 已經是 Debian 13（trixie），內建就是 17**——
建置紀錄裡的 `deb13u1` / `deb13u4` 就是證據。所以 PGDG repo、簽章金鑰、
`curl`、`gnupg` 全部不需要了，直接 `apt-get install postgresql-client-17`。

版本照樣釘 17，不用 `postgresql-client` 這個 metapackage：
**以後 base image 換成預設更舊的版本時，要在這裡大聲失敗，不要安靜地裝一個
讀不動伺服器的 pg_dump。**

拿掉之後，Dockerfile 裡**沒有任何一步需要公開網際網路**（`pip install` 走
PyPI，那條是通的）。

已經排除的：GitHub 上東西是齊的（`origin/main` 有 `lib/chain.py` 與
migration 017，分支 `main`）；`main.py` 與 `chain.py` 都通過語法檢查；
**Dockerfile 沒有跑測試**，只有 `pip install` 和 `COPY . .`，所以新增的三個
Python 檔不可能讓建置失敗。

**下次開機第一件事：測 `n_routes`。是 79 就照下面五步驗；還是 72 就去看
Zeabur 的部署狀態——「建置中」等就對了，「部署失敗」去看建置紀錄最後一行。**

部署好之後要做的，按順序：

1. `/admin/config` 確認路由變成 78（多了六條 `/compute/chain/*`）
2. 套 **migration 017**（W-ADMIN → POST `/admin/migrate`，
   body `{"file":"017_chain_can_only_queue_a_stage_once.sql","expect_database":"research"}`）
3. `GET /compute/chain/plan` 看六段回得對不對
4. `POST /compute/chain/start` 放一個專案上鏈，再 `POST /compute/chain/claim`
   確認認領得到、而且**連續兩次認領第二次要回 0 筆**（那是唯一索引在做事）
5. 這些都過了，**才**啟用 W-CHAIN

**六個工作流的鏈接線一次都沒實跑過。** 尤其沒驗過的是：
Execute Workflow Trigger 的 passthrough 到底把 `params` 放在哪一層
（正規化節點同時讀 `j[k]` 和 `j.params[k]` 就是為了吃掉這個不確定性，
但那是防禦，不是驗證）。

### W10 撞題排程（S11）：已建，預設未啟用（2026-09-02）

migration 013 已套用（新增 `method = 'collision_watch'`），四個端點都活著。
`/compute/watch/list` 實測：1 個方向、14 個查詢、**44 個基線識別碼**
（42 個 DOI ＋ 2 個沒有 DOI 的用標題前 80 字元遞補）。工作流 `m0p2FLGSle4oU1OK`，17 節點。

#### 成本設計：安靜的日子是零元

每天問的是一個很窄的問題——**有沒有出現上次沒有的論文**。不是「這個還新不新」，
那是判斷、需要模型，而每天為沒有變化的方向重複買同一個答案是浪費。

所以節點順序是：重跑查詢（免費）→ 機械比對（免費）→ **IF 有新論文** →
才叫模型。**這個順序就是整個設計**：會在安靜的日子花錢的排程會被關掉，
而關掉的排程找不到任何東西。

#### 三個容易做錯的地方

**比對識別碼，不比對數量。** 命中數變多只代表今天檢索比較吵；出現新的識別碼
才代表現在存在一篇以前沒有的論文。

**基線會併入先前巡查已經報過的論文。** 不這樣做的話，第一篇新論文會在往後
每一天都被重新當成新的，然後每天推一次 LINE，然後排程被關掉。

**安靜的日子照樣寫入資料庫。** 那些紀錄是「巡查真的有在跑」的唯一證據——
沒有它們的話，**一個月前就默默停掉的排程，看起來會跟一個沒被人搶先的方向
一模一樣**。

#### 兩個結構性拒絕

- 重跑結果存成 `method = 'collision_watch'`，理由跟 `debate_recheck` 同一條：
  存成 `adversarial` 會把 W7 十四輪的判決蓋掉，而且從欄位上看不出來
- **`no_prior_art` 直接拒收**。這輪巡查重跑的是原檢查用過的同一組查詢，
  查不到新東西只代表那組查詢沒查到新東西

#### 要改監看哪個專案

改 `Which Project To Watch` 那個 Set 節點。排程觸發沒有輸入，所以專案 id 寫在
那一個地方；表單手動執行時可以覆寫。時區已設 `Asia/Taipei`，否則 08:00 會是 UTC。

### W9 最終報告（S10）：已建，尚未實跑（2026-09-02）

migration 012 已套用（表數 25 → 26），`report` 表存在，三個端點都活著。
工作流 `FIWgMalCUagYln9M`，10 節點。**兩個模型都還沒寫過任何一份報告。**

#### 八節缺一不可寫成 CHECK，不是提示詞叮嚀

```sql
CHECK (sections ?& array['title','background','method','references',
                         'novelty','feasibility','objections','prework'])
```

少一節的報告最危險的地方不是資訊不全，**是它讀起來完整**——一份沒有
「未解決的反對意見」那一節的報告，看起來就像一個沒有未解決反對的方向。
另外每節至少 120 字元：PRD 要的是白話段落不是條列摘要，因為讀它的是人。

#### ⚠️ 實跑前抓到的接縫：`ops.search_query` 完全不寫資料庫

`/compute/report/inputs` 第一次實測回 **`citable_papers: []`**，但那個方向的
新穎性檢查裡明明有 40 篇真論文。

原因：**W7 十四輪檢索找到的論文從來沒有進 `paper` 表，也沒進 `search_hit`。**
`ops.search_query` 只回傳結果，不持久化。

後果有兩層，第二層比第一層糟：

1. 引用池是空的 → 寫報告的模型沒有東西可以引用
2. `verify_citations` 只查 `paper` 表 → **就算模型引用對了，也會被判成捏造全部丟掉**

改成 `citable_set()`：新穎性檢查的 `rounds`／`closest_papers` ∪ `search_hit` 撈到的。
**關鍵性質是：給模型看的池子，和驗證時用的集合，現在由同一個函式產生。**
兩者不同正是「模型引用了你給它的東西、然後被判定捏造」的成因——
這個系統一再踩到的就是這種接縫。

順帶把驗證範圍收緊：先前比對整張 `paper` 表（含其他專案的論文），
現在只認「這個方向的檢索實際回傳過的」。

**這件事對 W2 有一個沒解掉的含意**：如果之後希望新穎性檢索的論文能被重複使用、
被引用計數、被 harvest 拿去抓全文，那就要讓 `/compute/novelty/search` 真的
ingest。目前沒做——因為那會改變 W7 的行為而且需要回填。

### W8 唱反調迭代（S9）：規則驗過了，模型還沒打過（2026-08-30）

**已建**：migration 010、`lib/debate.py`、四個端點、n8n `PSqvLA7DS4huNrSU`（19 節點）。

**卡在哪**：W8 預設只打 A/B 級，而這個專案的看板是 `{A:0, B:0, C:1, D:7}`——
**一個 A/B 都沒有**。所以 `Pick The Directions` 正確地擋下來了
（執行 165），兩個模型還沒有真的打過一場。這是資料狀態的問題，不是 W8 的缺陷，
但它意味著**模型那一半的鏈路（攻擊 → 解析 → 辯護 → 解析 → 重跑 → 寫入）尚未實跑過**。

唯一有引用池的方向是 C 級那個（`0788a78a`，Noise x Smog），而它的辯論
已經被下面那組驗證用的假回合關掉了。要真的跑一場，需要先有一個
**A/B 級、而且跑過 W7 的方向**。

#### 五條規則逐條對著線上資料庫驗過（執行 160–164，零成本）

用 C 級那個方向當夾具，直接打 `/compute/debate/round`：

| 驗的東西 | 結果 |
|---|---|
| 一輪三個反對，只有一個站得住 | `n_objections_saved: 1`，另外兩個逐筆退回並附理由 |
| 3 分想讓步（`resolved_by_evidence`） | 退回：「At 3 or below the objection is plausible but unevidenced」 |
| 標 `strong` 卻沒有附論文 | 退回：「Without one it is an opinion」 |
| 兩邊同一個模型 | 400，整輪拒收 |
| 漂移 1.0（把題目換成另一個題目） | `terminated: true`，理由是漂移——**壓過那個還開著的、有引用的反對** |
| 漂移停之後想採用修訂版 | 400，拒絕。「它不是任何東西的改進版」 |
| 已經停了還想再送一輪 | 400，「reopening it would append rounds after a recorded ending」 |

**這組夾具留下的痕跡已經清掉了**（2026-08-30，執行 170）。當時 `0788a78a` 上留下
兩筆人工造的 `debate_round` 和一筆 objection，而且該方向的辯論被標成終止——
留著的話 W8 會永遠跳過它，而且從輸出上看不出來原因是假資料而不是真的辯完了。

`migrations/011_remove_debate_fixture_rows.sql` 刪掉它們（`objection` 隨 cascade）。
**確認方式是另外讀一次 `/compute/debate` 拿到 `n_rounds: 0`，不是 `applied: true`**——
後者只代表 SQL 跑完沒丟例外。

#### 三個設計決定，都是為了擋一種「看起來完成了」的失效

**沒有引用的反對不能結束辯論。** 只有 `citation_support='strong'` 的反對算進
終止條件。純推理的反對照樣記錄、照樣要回答，只是不能決定「還需要再一輪」。
而且引用只能從**該方向實際檢索回來的論文池**（W7 存的 `adversarial` 檢查）裡挑，
`Read The Attack` 逐筆比對，對不上的**降級成 irrelevant 而不是丟掉**。

**修訂存成子方向，不覆蓋原文。** `apply_revision` 寫的是一列新的 `idea`，
帶 `parent_idea_id` 和 `generation + 1`。覆蓋會讓已記錄的漂移全部回溯變成 0，
而且讀者要比較的「進去的版本 vs 出來的版本」少了一半。

**每輪重跑的新穎性另立 `method='debate_recheck'`。** 那個重跑是三個查詢、
沒有模型判決，只為了量距離。存成 `adversarial` 會把 W7 十四輪推不翻的判決蓋掉，
而且從欄位上看不出來。引用池也只從 `adversarial` 取，同一條分界順便擋住
「拿重跑結果當證據」。

#### `DRIFT_MAX = 0.5` 還沒有校準過

離線量到：收緊一個子句 → 0.053；換成另一個題目 → 0.966。0.5 落在中間一大段空白裡，
但**沒有任何真實辯論軌跡支持這個數字**。每一輪都會記下原始漂移值，所以之後可以
從資料重設，不用重跑。如果早期辯論全都在第 2 輪因漂移停掉，那就是這個數字錯了，
而 `termination_reason` 會直接把這件事說出來。

#### 已部署但**沒有驗過**的一項

`objection.cited_paper_id` 兩筆都是 `null`。DOI 依規格大小寫不敏感、來源之間
大小寫並不一致，所以精確比對對大多數真實引用都會安靜地找不到。已改成 `lower()`
比對（commit `f6c7141`），**但沒有驗證過**——它唯一的影響是那個選填的外鍵，
而要驗它就得再往真實方向寫一筆假回合，不值得為此再污染一次。
引用本身存在 `cited` jsonb 裡，比對沒中也不會遺失任何東西。

W-ADMIN 的下拉選單也補上了四個 `/compute/debate/*`、`/compute/feasibility`、
`/compute/novelty`，不用再手打 `endpoint_override`。

#### 貢獻性是主軸，不是四選一

PRD S9 寫「判準以貢獻性為主」，第一版提示詞卻把四個軸並列。已改：critic 被要求
**最好的那個反對要放在貢獻性上**——「假設這個研究跑得完美、答案是 yes，那會改變什麼？」
一個扛過所有健全性攻擊、卻回答不了這個問題的方向，仍然是倒下了；
反過來，一個重要問題上的設計缺陷是要修的東西，不是把它殺掉的理由。

#### 評分是辯護方自己給的

`rebuttal_score` 由持有想法的那一方打，這在結構上就偏向自己。沒有辦法讓它中立
（讓 critic 自己評自己的反對只是偏另一邊），所以做法是**把分數分布攤在守門結果裡**，
全場沒有任何一個 4 分以上就出但書。假裝它中立比較糟。

### W7 新穎性驗證（S8）實跑通過（執行 155，2026-08-29）

一個方向、14 輪檢索、7 分鐘、**$0.061**。四個守門全過，判 `adjacent`。

#### 一個靜默失敗，以及它為什麼值得記

第一次跑（執行 153）三個守門全過、產出漂亮的判決、五筆真實引用——
**但整個判決是在沒有領域新穎性慣例、也沒有盲點清單的情況下做出來的。**

原因：`/compute/frame?section=` 支援多個段落的那段程式碼**我寫了、編譯了、本機測了，
但從來沒有 commit**。部署上的舊版把 `"Novelty conventions,What this pack cannot see,..."`
當成單一標題去比對，一個都沒配到。

`has_frame` 是 true（框架確實存在），所以連「沒有框架」那句但書都沒觸發。
**跑動看起來完整，而讓它變好的東西不在場。**

已加第四個守門「領域新穎性慣例有沒有真的送到判決」，以及一句但書：
框架存在但沒有可用段落時，會寫進 `coverage_limits`。

#### 修好之後的差別，看檢索行為就知道

```
              修正前          修正後
術語體系        4 套            10 套
最接近的論文     切線相關         2005 Medicare、2011 Stroke、2017 China case-crossover
                             ——空污與出血性中風的奠基文獻
```

**第 12、13、14 輪的角度直接來自範式包的新穎性慣例**：
environmental-health 那份寫著「genuine novelty: a critical window nobody has resolved,
a susceptible subgroup with a mechanistic reason, a policy change that provides
identification」——而修正後的計畫就出現了 critical window identification、
susceptible subgroup mechanistic、policy natural experiment identification 三輪。

那三輪分別命中 0、1、5 篇。**針對「這個領域認可的新穎路徑」去打，幾乎全空**，
這比十四輪隨便打都有東西回來要有意義得多。

#### 這一層的四個硬約束

1. **預設立場是已經有人做過**，不是修辭。查不到的第一個解釋是查錯了。
2. **角度不得重複**，寫入時會被拒——那是換了編號的同義句。
3. **`scooped` / `incremental` 必須引用實際檢索到的論文**；
   `no_prior_art` 必須帶 `coverage_limits`（資料庫 CHECK 強制）。
4. **三輪空手且只用一套術語就宣稱新穎，直接拒絕。** 那是假新穎性宣稱最主要的產生方式。

引用另外還會在工作流裡**回頭比對實際檢索結果**，對不上就丟掉並記進 coverage_limits。
提示詞有叫模型不要捏造，但遵守不是控制手段，這個比對才是。

### W6 可行性分級（S7）實跑通過（執行 149，2026-08-29）

8 個方向對照 11 欄的測試世代，79 秒，**$0.08**（輸入 2,977／輸出 7,404 token）。

```
A 0    B 0    C 1    D 7
守門 4 過 3（缺的那條是「沒有研究背景檔」——真的沒有，不是缺陷）
```

全部 D 是**正確答案**：方向來自 PM2.5×腦中風的缺口採集，而測試世代只有年齡、
抽菸、fev1_fvc、二元中風結果。分級的品質從細節看得出來：

- 「`outcome_stroke` 不區分出血性與缺血性」——看出二元結果撐不起亞型問題
- 「只有 `fev1_fvc` 這個 proxy，沒有診斷碼」——**明確拒絕把 proxy 拉伸成 COPD 診斷**，
  那正是 skill 裡寫的「最誘人的失敗」
- C 那筆寫出了 join key：「district × visit_date，來自國家環境監測網，公開，約一天」
- 每一則 power note 都點名 n=60、4 個行政區，並指出交互作用／亞群設計需要數倍樣本

#### 這一層的三個硬約束都實測過

1. **原始資料永遠不會到這裡。** `tools/inventory.py` 在本機產出欄位清單。
   對一份**故意塞滿個資**的測試資料驗過：11 欄裡 4 欄標為個資（姓名、身分證字號、
   chart_no、clinical_note），**輸出 JSON 裡找不到任何一個原始值**
   （扣掉宣告過的 levels 與 min/max 之後為 0）。
2. **上傳端點會擋。** 帶 `rows` 鍵的 payload 回 400；「標了個資卻還帶 levels」的
   也回 400（那個形狀代表清單在剖析後被手動改過）。兩條都實測過。
3. **B/C 沒有去路就寫不進去。** migration 008 的 CHECK 強制
   `tier IN ('A','B','C','D')`，且 B/C 必須同時有 `missing` 與 `route_to_tier_a`。

#### 本機剖析器抓到的兩個錯，值得記住

**中文病歷整段被當成 level 輸出。** 自由文字門檻原本是 80 字元——那是照英文校的。
一段完整的中文病歷（主訴、抽菸史、理學檢查）只有 44 個字，直接穿過去。
已改成**加權長度，CJK 算兩倍**，並補上 note／主訴／病摘 等欄名比對。

**`clinical_note` 被標成 `joins_on=site`**，因為它包含 `clinic`。
加 `` 不能修——`_` 是 word character，所以 `date` 配不到 `visit_date`、
`lat` 配不到 `latitude`。欄位名絕大多數是 snake_case，**改成切詞比對**，
12 個測試名稱全部正確。

檔名是 `tools/inventory.py` 不是 `profile.py`——後者會遮蔽標準庫模組。

#### 四項修正已驗（執行 151，2026-08-29）

先給 PM2.5 專案補跑 W1（`observational` + `measurement` + `environmental-health`），
再重跑 W6。`n_tier_b_sources: 3`，三個包的 Tier B 段落都進去了。

**範式包確實改變了判斷，不只是多送了字。** 修正前後對照：

```
修正前  「SO2 could join via district × visit_date ...（days, free）」
修正後  「SO2 itself is Tier B ... but is not the binding constraint here」
```

**「什麼才是真正的瓶頸」這句話是修正後才出現的**——而 skill 說那正是這一步最常見的錯誤。
另外它也開始用包裡才有的來源名稱（satellite AOD、national noise maps），
以及把 GBD 那筆判成「**a fundamental scope mismatch, not just a missing variable**」。

守門與但書拆開之後 `all_gates_pass: true`（三個守門全過），
「沒有研究背景檔」移到 `caveats`。指示燈不再永遠是紅的。

費用反而降了：**$0.0593**（修正前 $0.0800）。輸入從 2,977 升到 3,969（多了 Tier B 段落），
但輸出從 7,404 降到 5,137——有包可依據時，模型少推理了。單次觀察，不要過度解讀。

**仍未驗**：`datasets_ignored` 那條路徑（目前只有一份資料清單，多份時的行為沒被走到）。

### 滿場地實跑：規模、費用、翻轉率（執行 144，2026-08-29）

15 個方向 ＋ 8 個錨點，`reduce_field=off` 釘死場地，**450 場、47 分鐘**。

#### 場次是二次方的，而且我先前算錯了

```
23 位參賽者 → C(23,2) − C(8,2) = 225 對 → 兩個順序 = 450 場 → 150 批
```

先前寫的「330 場」是錯的。**規劃跑動時用這個公式，不要用記憶中的數字。**

#### 實測費用 $2.661

```
151 次呼叫   輸入 230,925 token   輸出 219,917 token
每次呼叫     輸入 ~1,529          輸出 ~1,456
每場         $0.0059
```

**輸出裡約 82% 是 thinking token。** 可見的 JSON 回覆只有約 262 token，
其餘一千二百多都是不顯示但要計費的推理。這是先前估算範圍橫跨五倍的唯一原因。

我的估算換算到 450 場是 $0.83（不計 thinking）／$1.73（600/批）／$3.83（2000/批）。
**實測 $2.66 落在最高情境附近**——thinking 比我想的多。

**每次跑動都會自己回報 `cost`**（`Gather Every Verdict` 加總 `usage`，守門輸出帶
token 數、美元、每場多少錢）。不要再估算了。

#### 順序翻轉率：203 對，這次才有意義

```
本次單獨   40 / 203 = 0.197    95% 區間 0.142 – 0.252
合併六次   64 / 350 = 0.183    95% 區間 0.142 – 0.223
                                門檻 0.05 – 0.20
```

**點估計在門檻內但貼著上界，而區間跨過去了。** 誠實的讀法是：
**沒有嚴重的位置偏誤，但也不能宣稱穩穩在 20% 以下。** 要收窄還得再跑。

#### 錨點分離大幅拉開，且零錯位

```
strong 平均 1388.4（4 個）    weak 平均 1001.0（4 個）    間距 387
16 組強弱配對，0 組錯位
```

4 強 4 弱比先前的 2＋2 是強得多的檢查。第四個守門在這個規模下才真的有力量。

#### 兩個方向排在所有強錨點之上

rank 3（elo 1432.4）與 rank 4（elo 1415.3）標成 `at or above the strong anchors`，
高於四個強錨點的平均。這是這套系統第一次做出「**這個方向比我們的強基準還強**」
這種絕對判斷——**錨點預設開啟就是為了讓這句話說得出口**。

#### 漏判已查明並修掉（5.8% → 2.0%）

完整紀錄：`docs/experiments/2026-08-29-unjudged-matches.md`。從執行 144 的資料裡查的，
沒有重跑。

**不是截斷**——150 次呼叫的 `stop_reason` 全部是 `end_turn`，`maxTokens` 沒被碰到。

兩個獨立原因：

1. **欄位名跟答案值撞在一起。** 輸入用 `A` / `B` 當競爭者的鍵，答案又要 `"winner":"A"`。
   模型於是把標籤寫成欄位名：`{"match":58,"A":"A","reason":...}`。
   已改成 `option_a` / `option_b`，答案值改小寫 `"a"` / `"b"` / `"tie"`。
2. **模型會自我更正，解析器只讀第一個物件。** 有兩批先寫了壞的、說
   「Wait, I need to redo this properly」、再寫對的一份——搶救碼每次都拿到被作廢的。
   已改成取「可用答案最多」的物件，平手取最後一個。

**在 150 份真實回應上離線驗證：424 → 441（漏 26 → 漏 9）。** 改名那一項無法離線驗，
解析器那一項已驗。

**剩下的 2.0% 刻意不修。** 三批模型整個沒寫欄位，只在理由的白話裡講了勝負
（「so A wins on conclusiveness」）。解析白話有機會**把勝負判反**，而判反比判不出來糟——
判不出來會被計分跳過，判反會拿捏造的證據去動 Elo。跟「判不了就存 NULL」同一條原則。
要收掉這 2% 的做法是**重判那幾個批次**（約 2% 成本），不是再加提示詞。

### ⚠️ 對照實驗：錨點計數**沒有**改善校準（2026-08-29）

執行 126／127。除了計數開關之外**每一項都相同**：同一個專案、同一次跑動、
同樣 4 個錨點、同樣 shuffle_seed、`reduce_field=off` 把場地釘死在 15 個。

| | A：計數開（126） | B：計數關（127） |
|---|---|---|
| 順序翻轉率 | 0.167 | 0.067 |
| 錨點帶 strong／weak | 1320.0／1121.3（差 198.7） | 1331.6／1119.1（**差 212.5**） |
| CGM（弱，已被發表那筆）的 Elo | 1180.1 | **1177.8** |
| 強弱配對錯位 | 0／4 | **0／4** |
| 四個守門 | 全過 | 全過 |

**CGM 差 2.3 分，帶間距關掉計數反而寬一點。計數什麼都沒改變。**

#### 那執行 116 的錯位是什麼造成的

**錨點集合換了，不是計數。** 執行 116 的第二個強錨點是「用基因變異當工具變數」
（孟德爾隨機化），它輸給了 CGM。之後每一次跑動（121／125／126／127）第二個強錨點
都是量子那筆，全部零錯位。

量子那筆的改框直到執行 120 才真的寫進資料庫，在那之前它在庫裡還是 middling，
所以執行 116 選不到它。

**所以真正的發現是：有些錨點對這個裁判來說是壞錨點。** 孟德爾隨機化被寫成一個抽象的
方法（「利用配子形成時等位基因的隨機分配，把基因變異當作工具變數…」），
跟一句具體的研究問題並排時讀起來不像強方向。這跟它在領域裡的實際地位無關。

#### 那計數還要留著嗎

**留著，但理由要換掉。** 它原本的正當性——修好錯位——**沒有成立**。
現在剩下的理由只有一個，而那個是結構性的：

在加計數之前，**錨點沒有計數、方向有，光憑「有沒有數字」裁判就分得出誰是錨點**。
那是身分洩漏，跟它有沒有改變這次排名無關。代價是每次跑動多一次 HTTP 呼叫。

**不要再宣稱計數修好了校準。** 這裡有一次乾淨的對照說它沒有。

#### 這一次也示範了為什麼要固定場地

執行 125（第一次嘗試對照）**不算數**：縮減場地那次砍了 4 個（15 → 11），
而執行 121 砍 0 個。場地不同，`max_ideas=5` 取到的前五個也可能不同，
兩組根本不是在比同一件事。`reduce_field=off` 就是為此加的，**只在量測時用**。

#### 樣本數的限制

每組只跑一次。翻轉率 0.167 對 0.067 換算成 30 對是 5 次翻轉對 2 次——
這個差距完全在雜訊範圍內，**不要讀成「關掉計數比較穩定」**。

### W5 兩次跑動（2026-08-29）### W5 兩次跑動（2026-08-29）

冒煙測試設定都一樣：5 個方向（`max_ideas`）＋ 4 個錨點，60 場、20 批、約 8 分鐘。

| | 執行 116 | 執行 121 |
|---|---|---|
| 順序翻轉率 | 0.233 ❌ | **0.167 ✅** |
| 錨點帶 strong／weak | 1291.0／1184.7（差 106） | **1310.5／1121.8（差 189）** |
| 強弱配對排序 | 4 組錯 1 組 | **4 組全對** |
| 守門 | 2 過 1 敗 | **3 個全過** |

執行 121 的名次（錨點與方向混排）：

```
1. VLA 主動式超音波導航          strong   1335.6
2. intra-arterial thrombolytic   —        1286.1   落在兩帶之間
3. 量子增強特徵建模（已改框）    strong   1285.5
4. propionic acid × HRV × COPD   —        1257.3   落在兩帶之間
5. Smog × Clay × microbiome      —        1200.8   落在兩帶之間
6. CGM × 腸道菌相                weak     1179.1
7. Intersectional × Rehab × AP   —        1127.2   落在兩帶之間
8. 再做一個營養素觀察性研究      weak     1064.4
9. Celiac × Climate × 發炎       —        1063.9   在弱錨點之下
```

#### 修法：錨點也帶文獻計數，切點逐筆

執行 116 的錯位不是雜訊。CGM 那筆之所以 weak，理由是「已被 Zeevi et al. 佔據」，
而那件事寫在 `evidence` 欄，**裁判看不到**。凡是「弱在已經被做過」的錨點，
裁判在結構上不可能判對；「弱在設計本身」的那筆就準確落到最後段。

實測命中數（`SRC:MED`，各自切點之前）：

```
strong   VLA 超音波          0（詞太罕見，記 NULL）
strong   量子增強特徵建模    5
strong   SGLT2 心血管         9
strong   孟德爾隨機化         0
strong   CRISPR               1
strong   mRNA 核苷修飾        0
weak     CGM × 菌相          23
weak     營養素觀察性        91
weak     aprotinin 重複試驗 248
```

**強的全部 ≤ 9，弱的全部 ≥ 21。** 這就是裁判先前缺的鑑別訊號。

**切點必須逐筆。** 拿共用切點 2015 量 CRISPR（2012 提出）會得到幾千篇，
讀成「早就有人做了」，把要修的刻度反向弄壞。資料庫的 CHECK 強制「有詞就要有切點」。

**`papers_after` 已從裁判看得到的東西裡整個拿掉**（雙方都是）。CRISPR 的切點之後有
36,227 篇——那是事後影響力，等於把答案換個樣子交給裁判。

**三筆錨點刻意沒有檢索詞**：「在沒有事前分析計畫的資料集裡搜尋關聯」是**設計**不是題目，
沒有誠實的檢索詞能代表它，硬編一組就是捏造。這三筆是 1 強 2 弱，
所以「沒有計數」不再指向任何等級。

#### ⚠️ 這個比較不乾淨，不要當成受控實驗

兩次跑動之間**同時改了兩件事**：加了錨點計數，而且**錨點集合也變了**——
量子那筆的改框直到執行 120 才真的寫進資料庫（2026-08-28 只更新了 HANDOFF，
沒有 POST），在那之前它在庫裡還是 middling，所以執行 116 選到的是孟德爾隨機化。
執行 121 選到量子。**改善不能全歸因於計數。**

#### 縮減場地不是決定性的

同樣 15 個方向，執行 115 淘汰 1 個（`not_feasible`，理由具體），116 與 121 都淘汰 0 個。
拿掉 `temperature` 之後沒有任何一致性保證。不是錯，但報告要說得出當次淘汰了什麼、
為什麼——`field_reduction` 表就是為此存在。

### ⚠️ 一個查錯的教訓：0 clusters 不等於沒有配對（2026-08-29 更正）

本文件一度寫著「W4 沒有真的寫進資料庫，那 20 列查不到」。**那是錯的。**

`dedup_pair` 一直都在。run `922e3e3d` 有 20 列，寫入時間 2026-08-28T14:00:49，
`verdict` 全部是 `distinct`。執行 123 對 run `a1b7e106` 又寫了 20 列，同樣全是 distinct。

**錯在哪**：對 `922e3e3d` 只跑了 `/compute/dedup/resolve`，看到 `n_clusters: 0`
就當成「沒有配對」。但 **`resolve` 只數 `verdict = 'duplicate'` 的列**——那 20 組全是
distinct，所以 0 clusters 是完全正確的答案。真正該跑的
`/compute/dedup?run_id=922e3e3d` 從頭到尾沒跑過。

拿一個**分不出「沒有配對」和「沒有重複」**的查詢，去斷言整張表是空的。
這跟「`STILL OPEN` 不是新穎性證據」是同一種錯：把一個回傳零的查詢當成否定的證明。

**規則**：斷言「某個東西不存在」之前，先確認手上的查詢**看得見**它。
`resolve` 回 0 的意思是「沒有重複」，不是「沒有資料」。

### 去重合併已驗證（2026-08-29）

造了一組真的重複方向跑過一遍，六個行為全部成立：遞移合併、存活者取記錄最完整的、
同分決勝是決定性的、`uncertain` 不合併、`distinct` 不合併、`/compute/ideas/live`
確實把合併掉的擋在錦標賽外。人工覆寫也另外驗過。

完整紀錄：`docs/experiments/2026-08-29-resolver-duplicate-fixture.md`。
測試專案 `7d495464`，**是測試資料，不要拿它當真實跑動的樣本**。

順帶修掉兩個缺陷：

- **`created_at` 當不了決勝鍵**。一次跑動的方向在同一個 statement 裡插入，
  時間戳精確到微秒都相同（七筆全是 `10:23:36.900265`），所以「同分取先寫的」
  在正常情況下**完全沒有鑑別力**，存活者實際上由字典迭代順序決定。
  已再退到 `code` 與 `id`。
- **人工覆寫分支到不了**。它檢查 `merge_decided_by = 'human'` 且 `merged_into IS NULL`，
  而沒有任何端點能產生那個狀態——用 `decided_by='human'` 跑 resolve 標記的是**敗方**。
  補了 `POST /compute/dedup/keep`，那也是去重審閱介面 👁① 需要的原語。

**跨語言重複也驗過了**（第二組測試資料，專案 `c4e71649`）。三組英文三組中文，
其中兩組是互相的翻譯：

- **腳本完全看不到。** `score_range` 是 `[0, 0.064]`，而且那兩組真正的重複
  **連候選配對都沒進**——挑出的五組候選全是不相干的組合。詞彙相似度對跨語言
  不是「分數低」，是**排不進候選**。
- **`Sweep The Whole List` 兩組都抓到**，理由自己寫出「translated between English
  and Chinese」。這是那一步存在的唯一理由，而它成立了。

**仍未驗**：中文與中文之間的近似重複（換句話說，不是翻譯）。

### 去重缺一半：只記重複，沒記誰活下來（2026-08-28 發現並補上）

`dedup_pair` 記了「這兩個是重複」就結束了。`idea.status` **從建表到現在沒有被寫過一次**，
資料庫裡每個方向都還是 `candidate`。所以沒有任何地方記錄一對重複裡哪一個留在場上。

**W4 看不出這個問題**——它的產出是配對清單，而配對清單是對的。
它會在 W5 爆掉，而且完全沒有症狀：一對重複的方向同時進場，互相分掉勝場，
兩邊落在中段，排名讀起來完全合理。**錨點也抓不到**，因為被拉低的 Elo 是真的分數。

補法（migration 006 + `POST /compute/dedup/resolve`）：

- `idea.merged_into` 為 NULL＝還在場上；指向另一個 idea＝被它取代。
  用欄位而不是把 `status` 改成 `duplicate`，因為「這個方向去哪了」跟「它是重複的」
  是兩個不同的問題，半年後看報告會問前者。
- **遞移合併**：A~B 且 B~C 就三個裡留一個，即使 A 與 C 從未直接比過。
  否則只因為某一次配對沒觸發，兩個幾乎一樣的方向就都留下來了。
- **只有 `verdict = 'duplicate'` 會合併。** NULL 是模型說它判不出來，PRD 要那些進人工審閱；
  把「不確定」當成「重複」，丟掉的正好是最需要人看的那些。
- **存活者取記錄較完整的，同分取先寫的。** 兩個雙胞胎沒有誰比較正確，所以規則不能假裝
  在比高下——它比的是丟掉哪個損失比較小，因為裁判讀的是敘述，記錄完整的給裁判的東西比較多。
- **人的決定不會被後續自動跑動蓋掉，而且不刪任何東西**（PRD 給了去重審閱介面 👁①，
  要有東西可以推翻）。

**`/compute/ideas/live` 與 `/compute/ideas` 是兩個端點，不要合併成一個參數。**
審閱介面必須看得到被合併的列；錦標賽必須看不到。後者失敗時沒有症狀，
預設參數擋不住這種錯。

### 錨點：已灌 66 筆（2026-08-28）

| 來源 | 筆數 | `origin` | 等級怎麼來的 |
|---|---|---|---|
| ScholarIdeas | 54（27 strong／27 weak） | `scholarideas` | **專家 rubric**：`net = 重大優點 − 重大缺點`，再按樣本四分位切 |
| 使用者的實際決定 | 3 | `local` | PRD 第十五節，使用者自己的採用／否決與理由 |
| 已發表研究方向 | 9（5 strong／4 weak） | `published` | **外部可查事實**：被引數、指引採納、或有文獻明講這條線不再增加資訊 |

領域：AI 13、神經 16、生化 14、生態 11、臨床醫學 3、流病 3、生技 3，加上三筆醫學影像／代謝。

灌法：`POST /admin/load-anchors`，body `{"set":"scholarideas"}` 或 `{"set":"published"}`。
兩份都在 `data/`。**不要改成吃檔名參數**——那等於讓呼叫端讀行程摸得到的任何檔案。

**三件會被忘掉、忘掉就出錯的事：**

1. **裁判不可以看到錨點的等級，也不該知道誰是錨點。** 這是 ScholarIdeas 自己的
   使用說明寫的：等級只在事後計分時揭露。看得到刻度的裁判不是在被校準。
   跟「判斷輸入剝除作者訊號」是同一條原則。
2. **ScholarIdeas 的 `grade_feasibility` 全部是 NULL，這是刻意的。** rubric 評的是
   審稿人眼中這個想法好不好，那是貢獻性；它完全沒講使用者拿不拿得到資料。
   自己填一個進去，等於把模型的猜測放進字典序裡必須跟貢獻性分開的那一軸。
3. **等級詞彙是混的**：ScholarIdeas 與 published 只有 strong／weak 兩級，本地錨點有
   strong／middling／weak 三級。計分那一步要能吃兩種，不要假設三級。
   `published` 那份刻意不給 middling——中間帶找不到乾淨的外部證據，硬給一個等於把
   猜測混回來，而那正是整份檔案要避開的事。

**`published` 這份的 weak 判準，不要讀錯。** weak **不是**「後來被證明是錯的」——
一個能給出結論的方向，結論是正是負貢獻性都高（PRD 第十五節對量子那筆就是這個論證，
VITAL 兩個主要終點全陰性卻標 strong，就是這條規則的實例）。這裡的 weak 一律是
**有文獻明講這條線不再增加資訊**：aprotinin 在第 12 個試驗後又做了 52 個非必要試驗、
營養素觀察性關聯分不開營養素與健康行為、單一細胞株標靶驗證 53 個里程碑只有 6 個重現得出來。

還有一組是刻意配的：Karikó 的核苷修飾（被引 2074）與 CRISPR（被引 11954）**同樣標 strong**。
貢獻性不等於當下的關注度——這正是對照組實驗用比較痛的方式學到的那件事。

**本地錨點永遠不進 repo。** 那是使用者的研究策略——在做什麼、缺哪些資料——
而這個 repo 是公開的。它們只能經由 n8n 內網用 `POST /compute/anchors/save` 灌進去，
payload 留在 scratchpad。ScholarIdeas 是 MIT 公開資料，所以 `data/` 底下那份沒問題。

**第三筆（量子增強醫療 MLLM）已改框，使用者 2026-08-28 同意。**
從「用 QCNN 對舌診影像做 MASLD 預警」改成「檢驗量子增強特徵建模宣稱的優勢，
在高維度微小局部變化的醫學影像上是否真的成立」，`grade_contribution` 由 middling 改為
**strong**。`grade_feasibility` 維持 middling——改框動的是貢獻性那一軸，PRD 只講了那一軸。

改框的理由留著，因為它是這個錨點的用途：同一件事換個框法，貢獻性就不一樣。
第一種框法是「新方法套舊任務」，屬架構變體；第二種是在驗證一個有爭議、被廣泛引用
卻證據薄弱的宣稱，**成立與否都有價值**。這跟 `published` 那份把 VITAL 標 strong
是同一條規則。

**`published` 那 9 筆的等級，使用者 2026-08-28 逐筆看過並同意。** 不要再自行改動；
要改先問。

**錨點的識別鍵是 `external_id`，不是 `title`。** 改框會換標題，用標題當鍵會讓 UPDATE
變成 INSERT，資料庫裡就有同一個錨點的兩個等級在互相校準。已修（`3788897`）。

---

## ⚠️ 已經失敗過、不要重蓋的東西

**Swanson ABC 文獻探索：事前註冊、實測 FAIL，已放棄。**

門檻 `top20_over_control >= 2.0`，實測 **1.11**。診斷寫在
`docs/experiments/2026-08-28-timeslice-lung-adenocarcinoma.md`。

原因：肺腺癌是 hub 文獻（35,065 篇標題/摘要命中），透過 B 詞能到達的東西
就是「癌症生物學的其餘部分」，沒有鑑別力。**不要因為覺得參數沒調好就重試**——
這是事前註冊的失敗，記錄下來就是它的價值。

**改走的路：缺口採集 + LLM 組合推理。** 管線會動，但**下面那條「已示範可行」的舊結論
在有對照組之後站不住，不要再引用它**。

### ⚠️ 2026-08-28 對照組實驗：機械查核沒有鑑別力

完整紀錄在 `docs/experiments/2026-08-28-verify-directions-control.md`（六次測試）。

**做法**：把 Gemini 產出的方向用過的所有詞倒進袋子隨機重抽，組成假方向。
**詞完全相同，只有「誰決定哪些詞放一起」不同。**

```
                     還沒人做
Gemini 的配對         11 / 15
隨機重組              12 / 15
```

**判得動的方向裡兩邊都是 100% 判成「還沒人做」。** 換成逐對檢查、換成全文檢索，
三種問法都分不開推理與隨機——逐對那次隨機組合甚至更好。

**所以：`STILL OPEN` 不是新穎性證據，是「這樣問搜不到東西」。不准拿它排序。**

**唯一站得住的是否定訊號**（n=58，去重後，p≈0.003）：

```
從不相遇（概念在全文裡從未共現）  28 個   後來被發表 0 個
相鄰（概念共現但沒人當主題）      30 個   後來被發表 8 個
```

但**最可能的機制是注意力不是橋接**——共現高的概念本來就受關注。隨機組合落在
「相鄰」的比例比推理過的還高，這支持注意力的解釋。**`相鄰` 只代表這些概念正在
被研究，不代表題目好。**

**還有一個人工審閱時的實用線索**：三個詞的方向被判「還沒人做」，可信度天生低於
兩個詞的（發表率 6% 對 28%）。四次執行之間判決分布差那麼多，主因是模型剛好用了
幾個詞，不是方向品質。

### 已修好的兩個弱點

1. **假的「還沒人做」（縮寫問題）** — 已修，但修法與原本設想的不同。
   根因不是缺括號模式表，是 `query_terms` **按長度排序取最短同義詞**：
   `T-Lymphocytes, Regulatory` 的最短四個是 `tr1 cell` / `cell tr1` / `cell th3` /
   `th3 cell`，把 cap 佔滿，真正的 `regulatory t cells`（第 18 短）永遠進不去。
   修法：同義詞**按 token 集合去重**（消掉倒裝）、**按與描述詞的重疊度排序**再論長度；
   人工同義詞表改用 **MeSH UI 當索引鍵**（原本用拼寫，`regulatory t cells` 這個鍵
   從 `T-Lymphocytes, Regulatory` 這個拼法根本搆不到）。
   實測：S100A11 × 調節性 T 細胞 從 0 篇「沒人做」翻成 4 篇「後來有人做了」。
2. **詞太冷門導致判決是算術必然** — 新增 `TERM TOO RARE`。`MLH1 V384D` 全文獻 5 篇，
   任何含它的 AND 查詢上限就是 5，判決在搜之前就注定了。門檻 `MIN_TERM_PAPERS = 25`。

### 仍未解決

- **新方法沒有乾淨的事前註冊驗證。** 時間切片會被污染（Gemini 讀過 2015 後的文獻）。
  上面那個 n=58 的結果**只驗證了區帶能預測發表，沒有驗證方向的品質**。
- **方向品質從未被獨立評估。** 所有測試都在問「檢查有沒有鑑別力」，
  沒有一個在問「這些方向好不好」。後者要人讀。

---

## 待辦（依阻塞程度排序，2026-08-29 重寫）

**先前的第 1～3 項（Anthropic 憑證、建 W4、建 W1）都已完成，已從清單移除。**

0. ~~跑 `011_remove_debate_fixture_rows.sql`~~ ✅ **已完成（2026-08-30，執行 170）。**
   驗證用的兩列假 `debate_round` 已刪除，`objection` 隨 cascade 一起走。
   確認方式不是 `applied: true` 而是另外讀一次 `/compute/debate`（執行 171），
   回 `n_rounds: 0`。`0788a78a` 的辯論狀態回到未開始，W8 不會再無聲跳過它。

0a. **外洩處理的兩個收尾**（見「🔥 2026-08-30 憑證外洩處理」）：
   - **Google Drive**：授權已撤銷，但 **GCP 的 OAuth 用戶端還沒重建**，
     所以 W-BACKUP 每晚都會失敗。重建時**只勾 `drive.file`**——
     舊的那組給了「所有雲端硬碟檔案」外加 **Google 相簿**，遠超過備份需要。
   - **Postgres 對外埠 `43.133.34.49:30155`**：使用者選擇先不關。要關的話
     零風險（沒有元件走那條路），關掉那把被偷的密碼就等於作廢。

0b. **W8 需要一個 A/B 級、而且跑過 W7 的方向才能真的打一場。**
   規則全部驗過了，但兩個模型還沒有交手過。最省的做法是併進第 1 項：
   真題目跑完整條鏈之後，看板上自然會有 A/B 級方向，W7 跑完就有引用池。

1. **用一個真題目跑完整條鏈：W1 → W2 → 採集 → W3 → W4 → W5。**
   每個階段都各自驗過了，**但整條鏈從來沒有從頭到尾跑過一次**。
   這一整天找到的缺陷幾乎全部在接縫上——`$("node").all()` 只回傳單一次執行、
   W4 不記存活者、欄位名與答案值撞在一起——**單獨測每個階段都看不到那些**。
   費用約 $3、時間約一小時。建議用使用者自己的題目：環境賀爾蒙 × 肺腺癌第 0 期。

2. **四個審閱介面 👁①–④**（使用者 2026-08-28 確認要做）。
   現在唯一的閱讀方式是透過 W-ADMIN 看原始 JSON。已經有東西在等人看：
   去重判不出來的配對（NULL verdict）、錦標賽名次與校準帶、場地縮減的理由。
   **排在第 1 項之後**，這樣可以照真實資料設計，而不是照想像。

3. **S7 可行性分級（W6）+ 👁③。** 前 8 名 × `dataset.inventory` → A/B/C/D。
   **卡在研究背景檔上傳流程還沒做**——PRD 已把它從全域設定改成每個專案上傳一份
   （`project.research_profile`）。沒上傳也要能跑，但分級要標記
   「未提供背景檔，此判定為通用預設」。

4. **第 1 階段：16 項 ScholarIdeas 重驗。** PRD 寫「先驗證再蓋」，這一半仍是已知的偏離。
   目前領域落差 0.489，要低於對照組的 0.344，且神經科學不得再輸給對照組。

4b. ~~把預算護欄接到其餘工作流上~~ ✅ **W1–W10 十個全部接完了（2026-09-02）。**
   細節在上面「十個工作流都接上了」。**剩下的不是接線，是校準**：
   W4／W8／W9／W10 的階段預估目前是用估的，因為那幾段從來沒實跑過。
   第 1 項跑完整條鏈之後，回頭把那張表的數字換成實測值。

5. ~~S8–S11 尚未建~~ ✅ **W6–W10 全部建好了（2026-08-29 至 09-02）。**
   PRD 的 S1–S11 對應的 W1–W10 現在都存在。**但 W8／W9／W10 三個的模型那一半
   都還沒實跑過**——它們全部卡在同一件事：這個專案沒有 A/B 級方向，
   而且只有一個方向跑過 W7。第 1 項（真題目跑完整條鏈）會一次解掉三個。

6. 選配：寫信請 NCBI 解封 `43.133.34.49`（草稿寫好了，沒寄）。
   **2026-08-28 實測仍在封鎖中**，NCBI 直接回封鎖診斷頁：

   ```
   eutils.ncbi.nlm.nih.gov returned non-JSON (3872 bytes):
   <title>NCBI - WWW Error Blocked Diagnostic</title>
   ```

   **測試方法很重要：必須從容器裡打，不能從本機。** 封鎖是針對 Zeabur 的出口 IP，
   本機測一定會成功而且什麼都證明不了。用 W-ADMIN 打
   `POST /compute/search/query`，body 指定 `{"sources": ["pubmed"]}`，
   看回傳的 `attempt.failed`。

   這條封鎖是**採集層必須用 DOI 解析 PMCID 的原因**：少了 PubMed，W2 的結果
   來自 Europe PMC／OpenAlex／Crossref，那些帶 DOI 不一定帶 PMID。

### triage 端點已實測（2026-08-28，15 個真方向）

三個端點在此之前**從來沒有被任何工作流呼叫過**。實測結果：

```
dedup   15 個候選配對，最高 0.271 抓到兩個都用 MLH1 V384D 的方向
pairs   210 場 = 105 對 x 兩種順序，batch_size 3，70 批，同批次違規 0
elo     順序翻轉不一致率 0.0（確定性裁判下的預期值），排名遞減正確
```

**批次隔離（PRD 驗收硬條件之一）確認成立。**

順帶修掉一個 bug：`idea.title` 原本存成 `statement` 的前綴，而 `triage.idea_text`
會把 title 與 statement 串起來比對，等於句首的問句樣板被算兩次權重。
改成用詞組當標題（`MLH1 V384D x Gefitinib`）後，真重複從 0.118 升到 0.165
（**過了 0.15 門檻，原本會被漏掉**），無關配對從 0.090 降到 0.073。

---

## ✅ 已定案 — 不要再改、不要再蓋

**這一節存在的原因**：2026-08-28 使用者指出「你一直在重複修改已經改過的地方，
這樣會錯亂」。當天真的發生了三次，所以每項決定連同**為什麼**寫在這裡，
只寫「已完成」擋不住下一次重做。

| 項目 | 定案 |
|---|---|
| **Zeabur 部署** | **接了 GitHub，推 main 就自動部署**（GitHub deployments API 26 筆全是 `Deployed by Zeabur`）。**不要再叫使用者手動部署** |
| **`ACADEMIC_MAILTO` / `NCBI_API_KEY`** | **兩個都已設定**。不要再加「回報選配設定有無」的端點——加過又撤掉了（`0b84350` → `dac5d6a`） |
| **部署版本回報** | **不要加 commit hash**（`0b84350` 加了，使用者四分鐘後用 `dac5d6a` 撤掉）。`/admin/config` 改回報 `build.routes`——線上實際存在的路由清單。**這是不同的東西，不要再把它當成被撤掉的那個一起刪** |
| **模型分工** | 生成走 Gemini；**錦標賽對局判斷、可行性分級走 Anthropic Sonnet 5**；新穎性最終判定 Opus 5；唱反調 critic 必須與生成端不同家。理由是設計二的獨立性，不是避免干擾 |
| **`idea.title`** | 用**詞組**（`MLH1 V384D x Gefitinib`），不是 statement 的前綴。`triage.idea_text` 會串接 title 與 statement，前綴會讓句首問句樣板被算兩次權重 |
| **判不了時的 `novelty_check.verdict`** | 存 **NULL**。schema 那四個詞（scooped/incremental/adjacent/no_prior_art）任一個都是在斷言未經確立的事 |
| **`STILL OPEN`** | **不是新穎性證據，不准拿來排序**。見上方對照組實驗 |
| **審閱介面 👁①–④** | 要做，用更新後的資訊（使用者 2026-08-28 確認） |
| **公開 repo** | 這個 repo 是 **public**。不要把個資寫進原始碼——聯絡信箱走 `ACADEMIC_MAILTO` 環境變數，已從 `lib/verify.py` 與 `tools/verify_directions.py` 清除 |

### 同日已修，不要重修

- `save_directions` 讀 `verdict` / `rank` 讀不到 → `Report Verdicts` 刻意改名成
  `verdict_tag` / `rank_from_model`（把判決降級成標籤）。**兩種名字現在都接受。**
- 同義詞排序取最短 → 已改成按 token 集合去重、按與描述詞重疊度排序。
- 人工同義詞表用拼寫當鍵 → 已改用 MeSH UI。
- LLM 回覆截斷整批丟棄 → 已改成逐物件搶救（堆疊追蹤任何深度）。
- `addNode` 丟掉 `executeOnce` → 已用 `setNodeSettings` 補齊並確認。
- `/compute/triage/pairs` 把錨點等級回給呼叫端 → **已移除**。回應現在只有一個
  `competitors`（id → 文字），錨點與方向長得一模一樣。不要為了「方便組提示詞」加回去。
- 賽程預設判準是五條無序的 `contribution / novelty / expected effectiveness /
  clarity / feasibility` → 已改成字典序四條 `contribution / novelty /
  conclusiveness / feasibility`。**`clarity` 不准加回來**：寫得漂亮的弱方向會贏過
  寫得粗的強方向，而句子怎麼寫不是研究的性質。
- `order_flip_rate` 的分母算了只判過一次的配對（那種配對結構上不可能翻） →
  已改成只算兩個順序都判過的配對。分母灌水會讓有位置偏誤的裁判看起來正常。
- 只有單邊等級的錨點也會被標「between the anchor bands」 → 已改成回 `null`
  加一句說明。沒有下界卻宣稱落在區間內，跟 verdict 斷言查詢沒確立的事是同一種錯。
- `list_feasibility` 照 uuid 排，W7／W8 卻都寫著「取頭就是取名次最高的」 →
  已 join 最新一場錦標賽的名次再排（2026-08-30）。**不要改回去**：兩個階段
  都會對那個「頭」花錢，排錯等於把錢花在隨機一個方向上。

## 🔥 2026-08-30 憑證外洩處理

Zeabur 通知「n8n 上的 API key 全部被偷」。以下是實際做了什麼、以及踩到的坑。
**這一節不含任何金鑰值——這個 repo 是公開的。**

### 已完成

| 項目 | 狀態 |
|---|---|
| `N8N_ENCRYPTION_KEY` | ✅ 已換，舊的作廢 |
| Research API Key（`API_KEY` + n8n 憑證，成對） | ✅ 已換，W-ADMIN 獨立驗證 200 OK |
| Anthropic / OpenAI / Gemini | ✅ 已換，憑證測試綠燈 |
| LINE Messaging API | ✅ 已換（通用 header 憑證，n8n 測不了，綠燈只代表存檔） |
| Postgres 憑證 | ✅ 已重填（密碼**沒換**，但換了加密金鑰所以要重輸入），連線測試通過 |
| Google Drive OAuth | ⚠️ 已撤銷授權，**GCP 用戶端尚未重建** |
| 公開 repo git 歷史掃描 | ✅ 無 `sk-ant-` / `sk-` / `AIza` / `ghp_` / `Bearer` 樣式 |
| 16 個工作流檢查 | ✅ 無陌生工作流、無無法解釋的修改時間 |

**工作流檢查不是清白證明**：攻擊者要的是讀憑證，讀不留修改痕跡。

### ⚠️ 尚未處理：Postgres 對外埠仍開著

`postgresql` 服務的「網路」分頁有一筆公開對應：

```
43.133.34.49 : 30155  →  容器 TCP : 5432     （root / 密碼未換）
```

`43.133.34.49` 就是 HANDOFF 別處記著、被 PubMed 封鎖的那個 Zeabur 對外 IP。

**沒有任何內部元件在用這條路**（research-api 走 `service-6a8d...3836`，n8n 憑證走
`postgresql.zeabur.internal`，兩邊都確認過），所以**關掉它不會弄壞任何東西**。

留著的後果：資料可被讀寫、Postgres 超級使用者可用 `COPY ... FROM PROGRAM`
在主機上執行指令、以及全網掃描器會找到它。使用者 2026-08-30 選擇先不關，
改以換加密金鑰阻斷「憑證被重複竊取」那條鏈。**這是有意識的取捨，不是遺漏。**

### 把服務搞掛一小時的那個坑

**n8n 把加密金鑰同時記在兩個地方**：環境變數 `N8N_ENCRYPTION_KEY`，
以及容器裡的 `/root/.n8n/config`。**開機時會比對，不一致就拒絕啟動**：

```
Error: Mismatching encryption keys. The encryption key in the settings file
/root/.n8n/config does not match the N8N_ENCRYPTION_KEY env var.
```

只改環境變數 → 崩潰重試迴圈 → Zeabur 最後把服務暫停。而舊金鑰在容器裡、
使用者手上沒有，一度以為救不回來。

**救回來的方法**：把 `N8N_ENCRYPTION_KEY` **整筆刪掉**（不是清空）。
沒有環境變數時 n8n 只讀檔案，沒有東西可以對不起來，服務立刻恢復。

**正確的換法（實際做成功的）**：

1. 先 `cp /root/.n8n/config /root/.n8n/config.bak` 留退路
2. `cat /root/.n8n/config` **把舊值讀出來存好**——這一步不做就會像上面那樣卡住
3. `echo '{"encryptionKey":"新金鑰"}' > /root/.n8n/config`（單引號包住，`+ / =` 才安全）
4. **不要設環境變數**——只用檔案這一個來源，那個失效模式就從結構上不存在
5. 重啟 → n8n 正常開機，7 把憑證變成解不開的亂碼（**這是預期的**）
6. 逐一**編輯**憑證填新值

### 幾個具體事實，下次不要重新踩

- 路徑是 **`/root/.n8n/config`**，不是 `/home/node/.n8n/config`（這個 image 以 root 跑）
- 容器裡是 **`sh` 不是 bash**（`bash: not found`），指令要用 POSIX 寫法
- `config` 權限是 **644** 而 n8n 跑得好好的 → **不要去 `chmod`**，多改一個變數就多一個失敗面
- 憑證一律**點開改值**，**不要刪除重建**：ID 被寫死在幾十個節點裡，
  例如 `Pt36z1ZQwT84ARd5` 出現在 W1–W8 幾乎每個 HTTP 節點
- 換完加密金鑰的**驗證方法**：故意跑一個用到憑證的工作流，看它是不是回
  `Credentials could not be decrypted` ——**那個錯誤就是換成功的證據**。
  執行 173（解不開）→ 重填憑證 → 執行 174（200 OK），這一組對照就是完整驗證

### 驗證要用免費的手段

n8n 的**憑證測試按鈕會對 provider 發一個最小請求**，Anthropic / OpenAI / Gemini /
Postgres 亮綠燈就代表金鑰真的能用。**不需要為了驗證去跑真的工作流燒錢**——
跑 W1 只是重複證明同一件事。

測不了的兩種：`httpHeaderAuth` 和 `httpTemplatedCustomAuth`（通用型，沒有可測的端點）。
Research API Key 是後者，改用 W-ADMIN 打 `/admin/config` 驗，也是免費的。

## 🔒 不可妥協的規則

這些不是偏好，是硬規則。違反了要停下來講，不要自己權衡。

- **`profile.py` 永遠只在本機跑。** 只上傳欄位清單 JSON。
  **原始資料列永不上傳；被標為個資的欄位連範例值都不上傳。**
- **引用永不捏造。** 每個 DOI / PMID 都要來自實際檢索回傳，取不到就標「未取得」。
  DOI 與 PMID 同時存在時要交叉驗證。
- **`N8N_ENCRYPTION_KEY` 弄丟 = 所有憑證報廢**，無法回復。
  金鑰同時記在環境變數和 `/root/.n8n/config`，**開機時比對，不一致就拒絕啟動**。
  只改一邊 = 服務崩潰迴圈（2026-08-30 實際發生，見上一節）。
  **要動它之前先 `cat /root/.n8n/config` 把現值讀出來存好**，
  而且正確做法是**只留檔案、不設環境變數**。
- **不要動 Zeabur 的 `PASSWORD` 環境變數。**
- **唱反調的模型必須與生成的模型不同家。**（PRD 設計二）
- **`/admin/config` 永不回傳密碼**，只回長度和是否為未解析的 `${...}`。
- **資料庫憑證用 PG\* 環境變數傳給 `pg_dump` / `psql`，不要放進 argv 的 URI。**
- **`d:\n8n_Claude` 不可以變成 git repo** —— 裡面有 `加密金鑰.docx`、
  `api key.txt`、和 54MB 的 `cloudflared.exe`。
- **不要叫使用者截圖 API key 或 token。**（已經發生過一次，那把 NCBI key 已作廢重發）
- 排序用**字典序**：貢獻性 → 新穎性 → 能否得出結論 → 可行性。
  **不准用加權平均**，也不准在縮減場地時用「不適合你」當理由。

---

## 環境備忘

- Python 一律用 `python`，**不要用 `python3`**（本機的 python3.exe 是空殼）
- Zeabur 已升到 **8GB**，PRD 第九節的 2GB 對策大多失效——
  **但錦標賽批次維持 3 組，那條有獨立理由**
- n8n Workflow SDK 限制：**不能用 `.join()`、不能用箭頭函式、只能用 `const`**
- **Gemini 3 的 thinking token 算在 `maxOutputTokens` 裡**——回覆被截斷多半是這個原因。
  **這一條 2026-08-28 又踩了一次**（`Group The Terms` 設 8000 卻只產 308 token 就
  `MAX_TOKENS`，`thoughtSignature` 佔了 28,376 字元）。機械性任務把
  `thinkingBudget` 壓到 512，`maxOutputTokens` 給寬。
- **任何吃 LLM JSON 回覆的 Code 節點都要能搶救被截斷的回覆。** 掃描時要收
  **任何深度閉合的物件**（用堆疊追蹤）——只收 depth 0 的話，外層包裝在截斷時
  永遠不會閉合，一個都救不到。**這個 bug 在同一天寫了兩次**。
  這個模型還會在合法 JSON 後多吐一個 `}`，要改成讀第一個平衡的物件而非整個字串。
- **`update_workflow` 的 `addNode` 會靜默丟掉 `executeOnce`。** 它的 node schema
  只收 name/type/typeVersion/parameters/position/credentials/disabled/notes/id。
  要另外用 `setNodeSettings` 補，**而且加完要用 `get_workflow_details` 回頭確認**——
  `appliedOperations` 照樣會算成功。漏掉的代價：接在多筆輸入後面的 HTTP 節點會
  每筆各跑一次，15 個方向就是對外部 API 打 450 次。
- **`update_workflow` 偶爾會把 `operations` 判成字串而拒絕**（大段 jsCode 或某些
  全形標點會觸發）。拆成多次小的 update 就會過。
- Zeabur 重新建置要 **3–6 分鐘**，不要等 150 秒就重測（會拿到舊程式碼的假失敗）。
- **推 main 就自動部署，而建置期間 API 是真的斷的。** 不要一邊推程式碼一邊跑工作流：
  執行 59 就是這樣死的（`Look Up The Terms` 收到 ECONNRESET / socket hang up）。
  W3 呼叫 API 的節點現在都有重試（3 次、間隔 5 秒）來吸收這種短暫斷線。
- **GitHub deployments API 的 `success` 不代表服務已就緒**——它在登記的同一秒就出現，
  只代表「推送被接走了」。要確認服務活著就打 `/healthz`（用 W-ADMIN）。
- 在 n8n 的 SDK 程式碼裡嵌 JSON 會引號打架，**用 base64 + `Buffer.from(b64,"base64")`**
- **git commit 訊息含雙引號會打壞 PowerShell here-string**，改用 `git commit -F 檔案`
- **Claude Code 沒有 Zeabur 工具**，部署一定要人做
