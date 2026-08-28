-- ============================================================
-- 讓錦標賽存得下錨點對局
-- ============================================================
--
-- `tournament_match` 的兩邊原本都是 NOT NULL 且外鍵指向 `idea`，`ranking` 也只有
-- `idea_id`。但錨點住在 `anchor` 表，不是 idea——所以錨點參與的對局與它拿到的
-- Elo 分數都存不進去。
--
-- 這不是小事。PRD 說錨點預設開啟，理由是「沒有錨點的話排名只有相對意義，你永遠
-- 不知道第一名是不是絕對夠好」，而校準用的對局如果不留紀錄，**排名就無法從資料庫
-- 重建**——那違反「報告要能單獨閱讀，半年後回頭看不需要重跑系統」這條硬規則。
--
-- 兩邊各自改成「idea 或 anchor 二選一」，用 CHECK 強制恰好一個。允許兩個都填或
-- 都不填的話，那些列在讀取時的意義要靠猜。

ALTER TABLE tournament_match ALTER COLUMN left_idea  DROP NOT NULL;
ALTER TABLE tournament_match ALTER COLUMN right_idea DROP NOT NULL;
ALTER TABLE tournament_match ADD COLUMN IF NOT EXISTS left_anchor  uuid REFERENCES anchor(id) ON DELETE CASCADE;
ALTER TABLE tournament_match ADD COLUMN IF NOT EXISTS right_anchor uuid REFERENCES anchor(id) ON DELETE CASCADE;

ALTER TABLE tournament_match DROP CONSTRAINT IF EXISTS match_left_one_side;
ALTER TABLE tournament_match ADD CONSTRAINT match_left_one_side
    CHECK ((left_idea IS NULL) <> (left_anchor IS NULL));
ALTER TABLE tournament_match DROP CONSTRAINT IF EXISTS match_right_one_side;
ALTER TABLE tournament_match ADD CONSTRAINT match_right_one_side
    CHECK ((right_idea IS NULL) <> (right_anchor IS NULL));

ALTER TABLE ranking ALTER COLUMN idea_id DROP NOT NULL;
ALTER TABLE ranking ADD COLUMN IF NOT EXISTS anchor_id uuid REFERENCES anchor(id) ON DELETE CASCADE;
ALTER TABLE ranking DROP CONSTRAINT IF EXISTS ranking_one_side;
ALTER TABLE ranking ADD CONSTRAINT ranking_one_side
    CHECK ((idea_id IS NULL) <> (anchor_id IS NULL));

-- 縮減場地的理由要留下來，而且只有兩個是合法的。
--
-- PRD 設計五記了一次實跑抓到的錯誤：把「不在你的方法學內」當成淘汰理由，等於把
-- 個人限制條件偷渡進學術價值判斷。判準是字典序、貢獻性優先，可行性只在最後平手時
-- 才進來——淘汰階段用可行性理由會讓那個順序失效。
--
-- 存成欄位而不是只寫在提示詞裡，才查得出來有沒有被違反。
CREATE TABLE IF NOT EXISTS field_reduction (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tournament_id  uuid REFERENCES tournament(id) ON DELETE CASCADE,
    idea_id        uuid NOT NULL REFERENCES idea(id) ON DELETE CASCADE,
    reason         text NOT NULL,   -- already_published / not_feasible
    detail         text,
    decided_by     text,
    decided_at     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT reduction_reason_allowed
        CHECK (reason IN ('already_published', 'not_feasible'))
);
CREATE INDEX IF NOT EXISTS reduction_tournament_idx ON field_reduction(tournament_id);
