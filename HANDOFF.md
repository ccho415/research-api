# 交接文件 — 研究方向發想系統

**寫給：接手這個專案的任何一個新的 Claude Code 工作階段。**
最後更新：2026-08-28（第二次，含對照組實驗結果）

> **先讀完這一份再動手。** 上一個工作階段沒讀，結果重新踩了一次「thinking token
> 算在 maxOutputTokens 裡」——那條在本文件的環境備忘裡本來就寫著。

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
| **W3 想點子** | ✅ 產出會寫進 `idea` + `novelty_check`，含 `method_sketch` 與 `required_variables`。**素材仍是寫死的 base64**，見下方採集層 |
| **W4 去重** | ✅ 端到端通過（執行 67，20 組寫入 `dedup_pair`） |
| **採集層** | ✅ 實跑通過，快取驗收見下 |
| W1 領域框架 | ❌ 未建。**這是方法軸的前置**，沒有它 S3 的方法軸跑不了 |
| S5–S11 | ❌ 未建。W4（S5 去重）的計算端點已備妥且實測過 |
| 四個審閱介面 👁①–④ | ❌ 完全未建，沒有任何前端 |
| 第 0/1 階段（修 domain-profile + 重驗） | ❌ 未做。PRD 寫「先驗證再蓋」，實際上跳過了，這是已知的偏離 |

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
| `Pt36z1ZQwT84ARd5` | Research API Key | httpHeaderAuth |
| `eCLOk0QB1CM31sM1` | Postgres | postgres |
| `tgUuL2avuGxFtJHi` | Google Drive | googleDriveOAuth2Api |
| `CZonQ0U8wL27CAKM` | Google Gemini (PaLM) | googlePalmApi |
| `ry2UKtnf3GjmXq8d` | OpenAI | openAiApi |
| `dAytbkY0WTl24Yjm` | LINE Messaging API | httpHeaderAuth |

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
```

`GET /compute/ideas` 會把**最新一次的 `novelty_check` 併進來回傳**（verdict、rounds、
coverage_limits）。刻意如此：一個方向如果只有敘述沒有判決與警語，那正好是最會誤導人
的那一半——敘述永遠讀起來合理，警語才是決定該信多少的東西。
參數 `project_id` / `run_id` / `status` / `limit`，至少要給前兩者之一。

`GET /compute/dedup` 同理併進兩個**完整題目**，不是 id。PRD 的顯示規則不是裝飾：
判斷兩個方向是不是同一個，一定要兩個都讀得到，他們實跑時發現代號與截斷標題根本判不了。

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

## 待辦（依阻塞程度排序）

1. **取得 Anthropic 憑證。** PRD 第十一節整套配置是 Sonnet 5 / Opus 5，
   但 n8n 目前只有 Gemini 與 OpenAI 兩組。**使用者已同意提供，待加入 n8n Credentials。**
   MCP 只能列出憑證不能寫入密鑰，所以這一步一定要人做。
2. **建 W4（S5 去重）+ 👁①**。計算端點 `/compute/triage/dedup` 已實測（見下），
   `GET /compute/ideas` 已備妥。
   PRD 要求三步：腳本提候選 → AI 逐組判 → **AI 自己再掃一遍全清單**
   （腳本抓不到跨語言重複，分數是 0.0）。中文門檻要另外校準。
   **W4 要用這個跑動的資料**：
   `run_id = 922e3e3d-ec97-436c-be37-c5a243028d9a`（執行 61，2026-08-28，15 列完整）。
   同一個專案 `cab10537-8a27-4993-b850-db4a825184bd` 裡另有 15 列來自跑動
   `1cfe06e8-...` 的**降級資料**（verdict/code 為 NULL，原因見下方已修項）。
   **用 `run_id` 過濾，不要用 `project_id`**，否則會把壞資料一起拿去去重。
3. **建 W1 領域框架**（S1）——沒有它，S3 的方法軸和 S4 的交叉都做不了。
   也是 `method_sketch.paradigm_source` 目前只能標 `inferred` 的原因。
5. 把缺口採集器產品化（現在是本機工具 `tools/harvest_gaps.py`，
   每篇論文要抓一次全文 XML，300 篇好幾分鐘，**不適合做成同步端點**）。
6. 用使用者自己的題目跑完整流程：環境賀爾蒙 × 肺腺癌第 0 期，2016–2026。
7. 選配：寫信請 NCBI 解封 `43.133.34.49`（草稿寫好了，沒寄）。
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
| **部署版本回報** | **不要加 build/commit 標記到 `/admin/config`**。同上，加過又撤掉 |
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

## 🔒 不可妥協的規則

這些不是偏好，是硬規則。違反了要停下來講，不要自己權衡。

- **`profile.py` 永遠只在本機跑。** 只上傳欄位清單 JSON。
  **原始資料列永不上傳；被標為個資的欄位連範例值都不上傳。**
- **引用永不捏造。** 每個 DOI / PMID 都要來自實際檢索回傳，取不到就標「未取得」。
  DOI 與 PMID 同時存在時要交叉驗證。
- **`N8N_ENCRYPTION_KEY` 弄丟 = 所有憑證報廢**，無法回復。
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
