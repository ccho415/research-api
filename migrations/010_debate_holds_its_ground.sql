-- ============================================================
-- 唱反調迭代（S9）：把讓步門檻寫成約束
-- ============================================================
--
-- `debate_round` 與 `objection` 的欄位註解已經寫了規則，但註解擋不住任何東西。
-- 這場辯論的每一條規則都是**為了對抗一個具體的失效方式**而存在的，而那些失效
-- 全部長得像正常運作。
--
-- **反對必須引用。** 純推理的反對不計入終止條件：「我覺得混淆沒處理好」不算，
-- 「這篇 2024 世代研究顯示這個混淆會反轉效應方向」才算。所以
-- `citation_support = 'strong'` 卻沒有引用任何東西，是一個沒有根據的斷言
-- 穿著證據的衣服——資料庫直接拒絕。
--
-- **三分以下不讓步。** devils-advocate 的評分表：1 是重申、2 是訴諸權威、
-- 3 是有道理但沒證據、4 才是「具體證據或設計改動處理掉了反對的機轉」。
-- 只有 4 分以上能讓步。寫成約束之後，「這點說得有道理，不過⋯⋯」式的軟化
-- 就寫不進去。
--
-- **兩個模型必須不同家。** 同一個模型自己跟自己辯論，共用同一組盲點，
-- 產出的是一場看起來很認真的獨白。

ALTER TABLE objection ADD COLUMN IF NOT EXISTS cited jsonb;

-- 每輪辯論後要重跑新穎性、記錄距離軌跡。那個重跑是**三個查詢**，不是 S8 的十四輪，
-- 而且沒有模型判決——它只是量「修訂後的敘述離最近的論文變遠還是變近」。
--
-- 如果它也存成 `adversarial`，`list_novelty` 只取最新一筆，十四輪推不翻的判決
-- 就會被一個三查詢、沒有判決的檢查蓋掉，而且從欄位上看不出來。
-- 引用池也只從 `adversarial` 取，所以這條分界同時擋住「用重跑的結果去當證據」。
ALTER TABLE novelty_check DROP CONSTRAINT IF EXISTS novelty_method_allowed;
ALTER TABLE novelty_check ADD CONSTRAINT novelty_method_allowed
    CHECK (method IS NULL
           OR method IN ('mechanical', 'adversarial', 'debate_recheck'));

ALTER TABLE objection DROP CONSTRAINT IF EXISTS objection_severity_allowed;
ALTER TABLE objection ADD CONSTRAINT objection_severity_allowed
    CHECK (severity IS NULL OR severity IN ('major', 'minor'));

ALTER TABLE objection DROP CONSTRAINT IF EXISTS objection_axis_allowed;
ALTER TABLE objection ADD CONSTRAINT objection_axis_allowed
    CHECK (axis IS NULL OR axis IN ('contribution', 'novelty', 'soundness',
                                    'feasibility'));

ALTER TABLE objection DROP CONSTRAINT IF EXISTS objection_support_allowed;
ALTER TABLE objection ADD CONSTRAINT objection_support_allowed
    CHECK (citation_support IS NULL
           OR citation_support IN ('strong', 'weak', 'irrelevant'));

-- strong 代表「這個反對站在一篇真的存在的論文上」。沒有那篇論文，它就是意見。
ALTER TABLE objection DROP CONSTRAINT IF EXISTS objection_strong_needs_a_paper;
ALTER TABLE objection ADD CONSTRAINT objection_strong_needs_a_paper
    CHECK (citation_support IS DISTINCT FROM 'strong'
           OR cited_paper_id IS NOT NULL OR cited IS NOT NULL);

ALTER TABLE objection DROP CONSTRAINT IF EXISTS objection_score_in_range;
ALTER TABLE objection ADD CONSTRAINT objection_score_in_range
    CHECK (rebuttal_score IS NULL OR rebuttal_score BETWEEN 1 AND 5);

ALTER TABLE objection DROP CONSTRAINT IF EXISTS objection_status_allowed;
ALTER TABLE objection ADD CONSTRAINT objection_status_allowed
    CHECK (status IS NULL OR status IN ('resolved_by_evidence',
                                        'resolved_by_revision', 'unresolved'));

-- 三分以下不讓步，寫成結構而不是寫在提示詞裡。
ALTER TABLE objection DROP CONSTRAINT IF EXISTS objection_concede_needs_four;
ALTER TABLE objection ADD CONSTRAINT objection_concede_needs_four
    CHECK (status IS DISTINCT FROM 'resolved_by_evidence'
           OR (rebuttal_score IS NOT NULL AND rebuttal_score >= 4));

ALTER TABLE debate_round DROP CONSTRAINT IF EXISTS debate_models_differ;
ALTER TABLE debate_round ADD CONSTRAINT debate_models_differ
    CHECK (proposer_model IS NULL OR critic_model IS NULL
           OR proposer_model <> critic_model);

-- 漂移與距離都是 0 到 1 的比例。存了 87 會讓「超標強制停」那條規則永遠觸發。
ALTER TABLE debate_round DROP CONSTRAINT IF EXISTS debate_ratios_in_range;
ALTER TABLE debate_round ADD CONSTRAINT debate_ratios_in_range
    CHECK ((drift_from_original IS NULL
            OR drift_from_original BETWEEN 0 AND 1)
           AND (closest_paper_distance IS NULL
                OR closest_paper_distance BETWEEN 0 AND 1));

ALTER TABLE debate_round DROP CONSTRAINT IF EXISTS debate_round_no_positive;
ALTER TABLE debate_round ADD CONSTRAINT debate_round_no_positive
    CHECK (round_no >= 1);

CREATE INDEX IF NOT EXISTS objection_round_idx ON objection(debate_round_id);
