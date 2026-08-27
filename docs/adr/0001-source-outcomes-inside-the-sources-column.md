# 來源結果記在 `sources` 欄位裡，不另開欄位

PubMed 對本系統在 Zeabur 的出口 IP（Tencent Cloud，`43.133.34.49`）是永久封鎖，
所以 `clinical`、`biomed`、`publichealth`、`env` 四個領域的每一次檢索都會有一個
來源失敗，而且永遠都會。若不記錄，未來的讀者分不出「三個來源的結果」和
「這個領域本來就只有三個來源」。

考慮過在 `search_query` 加 `failed_sources jsonb`，但決定不動 schema。改成把既有的
`sources` 欄位從一個扁平陣列，改成一筆嘗試結果紀錄：

```json
{
  "attempted": ["pubmed", "europepmc", "openalex"],
  "answered":  ["europepmc", "openalex"],
  "failed":    [{"source": "pubmed", "error": "eutils.ncbi.nlm.nih.gov returned non-JSON …"}]
}
```

## 為什麼會讓人意外

`sources` 這個欄位名稱看起來就該裝一個字串陣列，而它裝的是一個物件。一個未來的讀者
看到會想「為什麼不乾脆加一欄」——答案是這個決定做的時候表是空的、加欄位的成本雖然低，
但每加一次就是一次要在正式環境上跑的遷移，而這一項資訊本來就屬於「這次檢索發生了什麼」，
和 `sources` 是同一件事的兩面。

## 代價

以來源篩選查詢（「列出所有 PubMed 失敗的檢索」）變成 jsonb 查詢而不是索引欄位查詢。
在目前的規模上無所謂；如果之後這種查詢變頻繁，加一個 GIN 索引即可，不必改欄位。
