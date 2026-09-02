-- ============================================================
-- 最終報告（S10）
-- ============================================================
--
-- PRD 第七節：**所有 A/B 級方向**，每個 8 節，每節都是白話段落而不是條列摘要。
--
-- 這張表存的是一份**要能單獨閱讀**的東西。PRD 的原話是：半年後回頭看，
-- 不需要重跑系統就能知道當初為什麼選這個、排除了什麼、還有哪些沒解決。
-- 所以報告不是指向其他資料表的一組 id，它是把當時的判斷**抄寫下來**——
-- 那些資料表之後會被新的執行覆蓋，報告不會。
--
-- **八節缺一不可，寫成約束而不是提示詞裡的叮嚀。** 少一節的報告最危險的地方
-- 不是資訊不全，是它讀起來完整：一份沒有「未解決的反對意見」那一節的報告，
-- 看起來就像一個沒有未解決反對意見的方向。

CREATE TABLE IF NOT EXISTS report (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    idea_id     uuid NOT NULL REFERENCES idea(id) ON DELETE CASCADE,
    run_id      uuid REFERENCES run(id) ON DELETE SET NULL,

    -- 八節。鍵名固定，值是整段白話文字。
    sections    jsonb NOT NULL,

    -- 通過查證的引用：每筆都在實際檢索回傳的結果裡找得到。
    citations   jsonb,
    -- 沒通過的：捏造的、或 DOI 與 PMID 互相矛盾的。留著是為了讓讀者知道
    -- 模型**試圖**引用什麼卻被擋下來——刪掉就看不出這份報告被修剪過。
    dropped     jsonb,

    -- 報告產出當下的等級與名次，抄寫而非參照，理由同上。
    tier        text,
    rank        integer,
    model       text,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS report_idea_idx ON report(idea_id, created_at DESC);

-- 八個鍵一個都不能少。`?&` 是「所有鍵都存在」。
-- 空字串擋不住，那一層在 lib/report.py 用比較好的錯誤訊息處理；
-- 這一層擋的是「整節不見」——那是唯一會讓報告讀起來完整卻不完整的情況。
ALTER TABLE report DROP CONSTRAINT IF EXISTS report_has_all_eight;
ALTER TABLE report ADD CONSTRAINT report_has_all_eight
    CHECK (sections ?& array['title', 'background', 'method', 'references',
                             'novelty', 'feasibility', 'objections', 'prework']);
