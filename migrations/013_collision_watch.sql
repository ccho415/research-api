-- ============================================================
-- 撞題排程（S11）
-- ============================================================
--
-- PRD：定期重跑已選定方向的新穎性檢查，被搶先就通知。每日嘗試，成功即止。
--
-- 重跑的結果**另立 method**，理由跟 `debate_recheck` 同一條：`list_novelty`
-- 只取最新一筆，一次每日巡查如果存成 `adversarial`，就會把 W7 十四輪推不翻的
-- 判決蓋掉，而且從欄位上看不出來。引用池也只從 `adversarial` 取。
--
-- 這一輪巡查是**同樣的查詢再跑一次**，比對的是「有沒有出現上次沒有的論文」。
-- 它不重新判決新穎性——那需要模型，而每天為了多半沒有變化的結果付錢是浪費。
-- 只有真的冒出新論文時才叫模型來看，這件事寫在 W10 的節點順序裡。

ALTER TABLE novelty_check DROP CONSTRAINT IF EXISTS novelty_method_allowed;
ALTER TABLE novelty_check ADD CONSTRAINT novelty_method_allowed
    CHECK (method IS NULL
           OR method IN ('mechanical', 'adversarial', 'debate_recheck',
                         'collision_watch'));

CREATE INDEX IF NOT EXISTS novelty_watch_idx
    ON novelty_check(idea_id, method, checked_at DESC);
