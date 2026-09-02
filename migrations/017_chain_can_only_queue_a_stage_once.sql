-- ============================================================
-- 階段自動接續：把 schema 裡躺了一整個專案的兩個欄位接上去
-- ============================================================
--
-- `run.pause_after` 和 `run.auto_advance_to` 從第一天就在 `schema.sql` 裡，
-- **沒有任何一行程式碼碰過**——跟預算護欄之前一模一樣。這份 migration 不新增
-- 欄位，它加的是兩個「讓做錯這件事變成不可能」的約束。
--
-- ### 一、同一個專案，同一個階段，只能有一列在排隊或執行中
--
-- 派工是「讀出待辦、再啟動」兩個動作。兩個節拍差一秒讀到同一列，就會把同一個
-- 階段啟動兩次——**而錦標賽跑一次是 $2.66**。程式碼那邊已經改成用一句原子的
-- UPDATE 來認領，這個索引是第二道：就算認領邏輯以後被改壞，資料庫也不會讓
-- 第二列存在。
--
-- 索引只涵蓋鏈上那六個階段。W2 的 `lit_search` 不在裡面是刻意的——使用者在鏈
-- 跑的時候另外開一次文獻檢索是合理的，不該被擋。
--
-- ### 二、`auto_advance_to` 只能是認得的階段名，或 null
--
-- 這一欄拼錯不會報錯，只會讓鏈**安靜地走到死路**：下一階段永遠不會被排進去，
-- 而看起來就跟「這個專案本來就跑完了」一模一樣。名字寫在 CHECK 裡，
-- 拼錯的當下就寫不進去。
--
-- 六個名字與 `lib/chain.py` 的 `STAGE_PLAN` 必須一致。**改動順序時兩邊要一起改**
-- ——這是這份 migration 唯一需要人記住的事。

ALTER TABLE run DROP CONSTRAINT IF EXISTS run_auto_advance_is_a_known_stage;
ALTER TABLE run ADD CONSTRAINT run_auto_advance_is_a_known_stage
    CHECK (auto_advance_to IS NULL OR auto_advance_to IN (
        'dedup', 'tournament', 'feasibility', 'novelty', 'debate', 'report'));

CREATE UNIQUE INDEX IF NOT EXISTS run_one_active_chain_stage_per_project
    ON run (project_id, stage)
    WHERE status IN ('pending', 'running')
      AND stage IN ('dedup', 'tournament', 'feasibility', 'novelty',
                    'debate', 'report');

-- 派工每次都要問「有沒有待辦」，而 `run` 會隨著每次跑動長大。
CREATE INDEX IF NOT EXISTS run_pending_chain_idx
    ON run (stage, id) WHERE status = 'pending';
