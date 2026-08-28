-- ============================================================
-- 記錄重複的方向裡，哪一個活下來
-- ============================================================
--
-- `dedup_pair` 記了「這兩個是重複」，但**沒有任何地方記錄哪一個留下**。
-- `idea.status` 從建表到現在沒有被寫過一次，每個方向永遠是 `candidate`。
--
-- 這在 W4 看不出來——去重的產出是配對清單，配對清單是對的。它會在 W5 爆掉，
-- 而且是安靜地爆：一對重複的方向同時進場，會互相分掉勝場，兩邊都落在中段，
-- 排名看起來完全正常。錨點也救不了，因為它們的 Elo 是真的被拉低了。
--
-- `merged_into` 為 NULL 代表還在場上。指向另一個 idea 代表被它取代。
-- 用欄位而不是把 `status` 改成 'duplicate'，是因為要留下**被誰**取代——
-- 半年後回頭看報告，「這個方向去哪了」跟「它是重複的」是兩個不同的問題。
--
-- 可逆是刻意的。誰是重複的由模型判、誰活下來由規則選，兩者人都可以推翻，
-- 而 PRD 給了去重一個審閱介面（👁①）。把敗方刪掉就沒得改了。

ALTER TABLE idea ADD COLUMN IF NOT EXISTS merged_into uuid
    REFERENCES idea(id) ON DELETE SET NULL;

-- 自己併進自己會讓存活者查詢無限迴圈。
ALTER TABLE idea DROP CONSTRAINT IF EXISTS idea_not_merged_into_self;
ALTER TABLE idea ADD CONSTRAINT idea_not_merged_into_self
    CHECK (merged_into IS NULL OR merged_into <> id);

-- 誰做的決定、什麼時候。`decided_by = 'human'` 的不可以被後續自動跑動蓋掉。
ALTER TABLE idea ADD COLUMN IF NOT EXISTS merge_decided_by text;
ALTER TABLE idea ADD COLUMN IF NOT EXISTS merge_decided_at timestamptz;

CREATE INDEX IF NOT EXISTS idea_live_idx ON idea(project_id)
    WHERE merged_into IS NULL;
