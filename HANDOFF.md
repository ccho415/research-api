# 交接文件 — 研究方向發想系統

**寫給：接手這個專案的任何一個新的 Claude Code 工作階段。**
最後更新：2026-08-30（W8 唱反調建好、規則驗過、可行性看板改照名次排序）

> **先讀完這一份再動手。** 上一個工作階段沒讀，結果重新踩了一次「thinking token
> 算在 maxOutputTokens 裡」——那條在本文件的環境備忘裡本來就寫著。

## ⏭️ 下次開機從這裡接

**W1–W10 全部建好了**（PRD 的 S1–S11 都有對應的工作流）。
**接下來唯一該做的是第 1 項待辦：用一個真題目跑完整條鏈。**

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
| 四個審閱介面 👁①–④ | ❌ 完全未建，沒有任何前端 |
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
| `cCni6Ds4qeKqI9s1` | **W2 文獻層** | 已發布，表單 `/form/w2-literature`，`n8nUserAuth` |
| `WrV8vqhn4h65G5nE` | W-BACKUP | 啟用中，每日 `pg_dump` → Google Drive |
| `p3cbX6VXhxBHCskT` | W-DRILL | 還原演練 |
| `Nc6AjZZPSQZdoI6N` | W3-TEST 缺口組合推理 | 11 節點。**素材仍寫死**，但題目與切點已改成表單欄位。表單 `/form/w3-directions`，`n8nUserAuth` |
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

**⚠️ 除了 W5B，其他工作流還沒接上去。** W5B 兩處都接了（提交前問、結束後記），
但 **W1–W4、W6–W10 目前沒有任何一個**會呼叫 `/compute/run/budget` 或
`/compute/run/spend`。

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

4b. **把預算護欄接到其餘工作流上。** W5B 已經接了兩處可以照抄，
   但 **W1–W4、W6–W10 還沒有任何一個會呼叫它**。要接兩處：
   - 每個工作流**開頭**打 `GET /compute/run/budget?estimate=<該階段預估>`，
     `may_start` 是 false 就不要跑
   - 每個工作流**結尾**（守門節點已經算好 token 了）打 `POST /compute/run/spend`

   W5 的預估用 `場次 × $0.0059`，場次公式是 `2 × [C(方向數,2) + 方向數 × 錨點數]`。

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
