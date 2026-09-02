-- ============================================================
-- 預算的單位是專案，不是 run
-- ============================================================
--
-- migration 014 把預算放在 `run` 上。那是錯的鍵，而證據是工作流自己：
-- 九個工作流裡只有 W5 和 W5B 有 `run_id`，其餘七個（W1、W6、W7、W8、W9、W10⋯⋯）
-- 都只認 `project_id`。
--
-- 使用者要的是「**跑一次完整流程**的上限」。那條鏈是 W1 → W10，全部掛在同一個
-- 專案底下——`run` 是其中某一段的紀錄，不是整條鏈。把上限放在 run 上，等於
-- 要嘛改七個表單逼使用者到處貼 run_id，要嘛七個階段根本沒有護欄。
--
-- **兩個地方各存一份預算會走樣，而走樣的那份不會報錯。** 所以 run 上的那兩欄
-- 直接移除，不留「之後再說」的第二事實來源。它們只存在三個小時，唯一寫過值的
-- 是驗證用的探測跑動。
--
-- `token_usage.run_id` 留著——它是明細，不是預算的歸屬。

ALTER TABLE project ADD COLUMN IF NOT EXISTS usd_budget numeric;
ALTER TABLE project ADD COLUMN IF NOT EXISTS usd_spent numeric NOT NULL DEFAULT 0;

ALTER TABLE project DROP CONSTRAINT IF EXISTS project_budget_not_negative;
ALTER TABLE project ADD CONSTRAINT project_budget_not_negative
    CHECK ((usd_budget IS NULL OR usd_budget >= 0) AND usd_spent >= 0);

-- 明細照樣按專案查得動，不必每次都繞過 run。
ALTER TABLE token_usage ADD COLUMN IF NOT EXISTS project_id uuid REFERENCES project(id) ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS token_usage_project_idx ON token_usage(project_id, recorded_at);

-- 把 014 記在 run 上的那筆探測資料搬到它的專案，再拆掉那兩欄。
UPDATE project p SET usd_spent = p.usd_spent + COALESCE(
    (SELECT sum(r.usd_spent) FROM run r WHERE r.project_id = p.id), 0)
WHERE EXISTS (SELECT 1 FROM run r WHERE r.project_id = p.id AND r.usd_spent > 0);

UPDATE token_usage tu SET project_id = r.project_id
  FROM run r WHERE r.id = tu.run_id AND tu.project_id IS NULL;

ALTER TABLE run DROP CONSTRAINT IF EXISTS run_budget_not_negative;
ALTER TABLE run DROP COLUMN IF EXISTS usd_budget;
ALTER TABLE run DROP COLUMN IF EXISTS usd_spent;

-- `paused_budget` 現在是專案層的狀態。留在 run.status 上的那個值沒有意義了，
-- 因為擋住下一階段的判斷不再看 run。
UPDATE run SET status = 'pending' WHERE status = 'paused_budget';
