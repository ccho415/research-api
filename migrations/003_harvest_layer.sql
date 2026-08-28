-- ============================================================
-- 缺口採集層：把 tools/harvest_gaps.py 從本機工具變成非同步 job
-- 全部 IF NOT EXISTS，重複執行不會出錯
-- ============================================================

-- Europe PMC 的全文要用 PMCID 取，不是 PMID。W2 存的 metadata 沒有這一欄，
-- 所以每次採集都得重新解析一次；存下來之後就不用了。
ALTER TABLE paper ADD COLUMN IF NOT EXISTS pmcid text;
CREATE INDEX IF NOT EXISTS paper_pmcid_idx ON paper(pmcid) WHERE pmcid IS NOT NULL;

-- 全文段落另開一張表，不塞進 paper。
-- 一段 Discussion 動輒數十 KB，放進 paper 會讓每一次論文查詢都拖著它走，
-- 而絕大多數查詢只要標題與摘要。
--
-- 這張表是採集成本的真正來源：一篇論文的全文要打一次 Europe PMC，
-- 300 篇就是好幾分鐘。存下來之後，同一批論文的第二次採集不用再抓。
CREATE TABLE IF NOT EXISTS paper_section (
    paper_id    uuid NOT NULL REFERENCES paper(id) ON DELETE CASCADE,
    kind        text NOT NULL,          -- discussion / conclusions
    content     text,                   -- NULL = 抓過了但這篇沒有全文
    fetched_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (paper_id, kind)
);

-- content 為 NULL 也是結果，不是缺資料：代表這篇論文抓過、確認沒有可取得的
-- 全文。沒有這個區別的話，每次採集都會對同一批沒有全文的論文重抓一次。

CREATE TABLE IF NOT EXISTS harvest (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id       uuid REFERENCES project(id) ON DELETE CASCADE,
    run_id           uuid REFERENCES run(id) ON DELETE CASCADE,      -- 採集自己的跑動
    source_run_id    uuid REFERENCES run(id) ON DELETE SET NULL,     -- 論文來自哪一次 W2
    status           text NOT NULL DEFAULT 'running',                -- running / done / failed
    n_papers         integer,
    n_with_fulltext  integer,
    n_gap_sentences  integer,
    n_concepts       integer,
    result           jsonb,      -- title_concepts + gaps，W3 直接吃這個
    error            text,
    started_at       timestamptz NOT NULL DEFAULT now(),
    finished_at      timestamptz
);
CREATE INDEX IF NOT EXISTS harvest_project_idx ON harvest(project_id, started_at DESC);
