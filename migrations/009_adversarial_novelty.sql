-- ============================================================
-- 對抗式新穎性檢查（S8）
-- ============================================================
--
-- `novelty_check` 現在存的是 W3 的機械查核：數命中數、分三區帶。
-- 2026-08-28 的對照組實驗已經證明**那個檢查沒有鑑別力**——同樣的詞隨機配對，
-- 跟有推理的組合，判決分布分不出來。它唯一還站得住的用途是「大量命中＝已經被做過」。
--
-- S8 是完全不同的東西：預設立場是「已經有人做過」，用十種**不同角度**的檢索去推翻它，
-- 再做 facet 級（purpose／mechanism／evaluation）撞題比對。
--
-- **兩種檢查會寫進同一張表，而 `list_ideas` 只取最新一筆。** 沒有 `method` 欄位的話，
-- 讀的人分不出手上這個 `adjacent` 是機械數出來的還是十輪檢索推不翻的——
-- 那兩件事的可信度差很多。

ALTER TABLE novelty_check ADD COLUMN IF NOT EXISTS method text;
ALTER TABLE novelty_check ADD COLUMN IF NOT EXISTS facets jsonb;
ALTER TABLE novelty_check ADD COLUMN IF NOT EXISTS query_angles jsonb;

-- 既有的列全部來自 W3 的機械查核。標記回去，否則它們會混進 S8 的結果裡。
UPDATE novelty_check SET method = 'mechanical' WHERE method IS NULL;

ALTER TABLE novelty_check DROP CONSTRAINT IF EXISTS novelty_method_allowed;
ALTER TABLE novelty_check ADD CONSTRAINT novelty_method_allowed
    CHECK (method IS NULL OR method IN ('mechanical', 'adversarial'));

-- 判決只有四個詞，或者 NULL。
--
-- NULL 是「判不出來」，而且是刻意保留的：schema 那四個詞任何一個都是在斷言
-- 一件沒被確立的事。W3 對 TERM TOO RARE／NO TERMS／CHECK FAILED 一律存 NULL，
-- 這條約束不能把那個行為擋掉。
ALTER TABLE novelty_check DROP CONSTRAINT IF EXISTS novelty_verdict_allowed;
ALTER TABLE novelty_check ADD CONSTRAINT novelty_verdict_allowed
    CHECK (verdict IS NULL
           OR verdict IN ('scooped', 'incremental', 'adjacent', 'no_prior_art'));

-- 「沒找到前案」是一個**有邊界的否定**，不是「不存在前案」。
-- 沒有寫出查了哪些資料庫、哪些年份、哪些語言查不到，這個判決就是在冒充後者。
ALTER TABLE novelty_check DROP CONSTRAINT IF EXISTS novelty_negative_needs_bounds;
ALTER TABLE novelty_check ADD CONSTRAINT novelty_negative_needs_bounds
    CHECK (verdict IS DISTINCT FROM 'no_prior_art' OR coverage_limits IS NOT NULL);

CREATE INDEX IF NOT EXISTS novelty_idea_method_idx
    ON novelty_check(idea_id, method, checked_at DESC);
