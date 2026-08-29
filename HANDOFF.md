# 交接文件 — 研究方向發想系統

**寫給：接手這個專案的任何一個新的 Claude Code 工作階段。**
最後更新：2026-08-29（W5 錦標賽建好、66 筆錨點入庫）

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
| **W4 去重** | ✅ 正常運作（`922e3e3d` 20 組、執行 123 對 `a1b7e106` 再 20 組，全部 `distinct`）。它**只記配對、不記誰活下來**，那一半已用 `/compute/dedup/resolve` 補上 |
| **採集層** | ✅ 實跑通過，快取驗收見下 |
| S7–S11 | ❌ 未建。S5 去重＝W4、S6 錦標賽＝W5，兩個都已建 |
| 四個審閱介面 👁①–④ | ❌ 完全未建，沒有任何前端 |
| 第 0 階段（修 domain-profile） | ✅ **已做完，本文件先前記錯**。skill 是 `v2.0.0`，四個修正都在 |
| 第 1 階段（16 項重驗） | ❌ 未做。PRD 寫「先驗證再蓋」，這一半仍是已知的偏離 |
| W1 領域框架 | ⚠️ 工作流已建（`NRe3eCGX4bEDegvo`），**還沒用真題目跑過**。要拿一個 ECG 題目驗 Q2 有答案時真的會載入第二個包 |
| **W5 錦標賽** | ✅ 執行 121 **三個守門全過**，錨點排序零錯位。仍未驗：場地放大後的表現。見下方「W5 兩次跑動」 |

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
| `CqaYzcqjNNgI05AP` | **W5 錦標賽** | 20 節點。表單 `/form/w5-tournament`，`n8nUserAuth`。錯誤工作流指向 W-ALERT。執行 116 端到端通過 |
| `NRe3eCGX4bEDegvo` | W1 領域框架判定 | **尚未用真題目跑過** |
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

### Anthropic 節點的兩個坑（2026-08-29 實測）

1. **`claude-sonnet-5` 不接受 `temperature`。** 送了會回
   `Bad request` + `temperature is deprecated for this model`，整個節點失敗。
   參數要**整個不存在**，設成 0 或 1 都沒用。W5 的兩個判斷節點都已拿掉。
   代價是輸出的一致性只能靠提示詞，不能靠 `temperature: 0`。
2. **Anthropic 節點沒有 Gemini 那個 `jsonOutput` 開關。** 回覆是純文字，
   所以 W3 那套搶救碼（挖巢狀字串、讀第一個平衡物件、任意深度撿完整物件）
   照抄過來是必要的，不是防禦性多寫。

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
