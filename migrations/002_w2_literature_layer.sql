-- W2 文獻層所需的 schema 變更。全部可重複執行。
-- 在 n8n 的「DB 工具」workflow 貼上執行一次即可。

-- 1) 論文去重的第三把鑰匙：既無 DOI 也無 PMID 時，用正規化後的標題。
--    部分唯一索引，所以之後補到 DOI 的記錄不會被誤併進標題相符的那一列。
ALTER TABLE paper ADD COLUMN IF NOT EXISTS title_key text;

CREATE UNIQUE INDEX IF NOT EXISTS paper_title_key_idx ON paper(title_key)
    WHERE doi IS NULL AND pmid IS NULL AND title_key IS NOT NULL;

-- 2) 詞彙展開的歷史。每次跑動重新展開並與前一版比對（ADR-0003），
--    所以這裡累積所有版本，不是只存最新的一版。
ALTER TABLE project ADD COLUMN IF NOT EXISTS vocab_expansion jsonb
    NOT NULL DEFAULT '[]'::jsonb;

-- 3) 中斷後續跑要問「這個跑動已經跑過哪些查詢」，那是 run_id 上的查詢（Q21）。
--    論文重用率的基準線也走這條路。
CREATE INDEX IF NOT EXISTS search_query_run_idx ON search_query(run_id);

-- 4) 指標查詢一律是「某個跑動的某個指標」，兩欄一起走。
CREATE INDEX IF NOT EXISTS health_metric_run_idx ON health_metric(run_id, metric);
