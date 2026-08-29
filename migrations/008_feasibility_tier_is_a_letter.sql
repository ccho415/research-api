-- ============================================================
-- 可行性分級：級別限定四個字母，B／C 必須寫出去路
-- ============================================================
--
-- `feasibility.tier` 原本是自由文字。存進 "maybe"、"A-"、"tier B" 都不會報錯，
-- 而分級看板是按 A／B／C／D 分組的——存錯的那幾筆會安靜地從三個分組裡全部消失。
--
-- **B 與 C 的意思是「還不行，但這是去路」。** 沒有缺什麼變項、沒有怎麼拿到，
-- 它們的意思就變成「不行」卻長得像「也許」——而讀的人會照著一個他其實到不了的
-- B 級去規劃。PRD 的守門寫著「B/C 必須寫出缺哪個變項、從哪拿、怎麼 join、要多久」。
--
-- 寫在提示詞裡的規則會被安靜違反，寫成約束就不會。

ALTER TABLE feasibility DROP CONSTRAINT IF EXISTS feasibility_tier_allowed;
ALTER TABLE feasibility ADD CONSTRAINT feasibility_tier_allowed
    CHECK (tier IN ('A', 'B', 'C', 'D'));

ALTER TABLE feasibility DROP CONSTRAINT IF EXISTS feasibility_bc_needs_a_route;
ALTER TABLE feasibility ADD CONSTRAINT feasibility_bc_needs_a_route
    CHECK (tier NOT IN ('B', 'C')
           OR (missing IS NOT NULL AND route_to_tier_a IS NOT NULL));

CREATE INDEX IF NOT EXISTS feasibility_idea_idx ON feasibility(idea_id);
