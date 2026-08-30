-- ============================================================
-- 清掉 2026-08-30 驗證用的假辯論回合
-- ============================================================
--
-- 執行 160–164 用 `0788a78a`（Noise x Smog x Hemorrhagic Stroke）當夾具，
-- 直接餵構造好的回合給 `/compute/debate/round`，驗證五條規則。那是刻意的，
-- 而且是零成本驗證資料庫約束的唯一辦法——但它留下兩列**人工造的** `debate_round`，
-- 而且把該方向的辯論標成了終止。
--
-- 留著會有兩個具體後果：
--   1. `debate_state` 讀到 `terminated: true`，W8 對這個方向永遠只會跳過，
--      而且從輸出上看不出來原因是假資料而不是真的辯完了。
--   2. 之後任何人讀 `/compute/debate` 會看到一份讀起來像真的逐字稿——
--      裡面的反駁是我隨手寫的，`rebuttal_score` 也是我指定的。
--
-- **這是資料清理，不是結構變更。** 借用 migration 的機制是因為它是唯一
-- 版本控制過、在交易裡跑、而且會擋錯資料庫的路徑；手打 SQL 進生產資料庫
-- 沒有這三樣的任何一樣。
--
-- `objection` 對 `debate_round` 是 ON DELETE CASCADE，所以那兩列反對會一起走。

DO $$
DECLARE
    removed integer;
BEGIN
    -- 指名到 id，不是「刪掉這個方向的所有回合」。如果之後真的跑過一場辯論，
    -- 這條不會碰到它——刪除的範圍必須是我知道自己造了什麼，而不是一個條件。
    DELETE FROM debate_round
     WHERE idea_id = '0788a78a-0d63-49f4-8318-c89a829d43da'
       AND id IN ('9df242e5-871c-4e52-8af9-923fef9c3cc5',
                  '45dded0d-7066-49d4-9ec8-f7308f1685af');
    GET DIAGNOSTICS removed = ROW_COUNT;

    IF removed = 2 THEN
        RAISE NOTICE '已刪除兩列假回合及其反對（cascade）。';
    ELSIF removed = 0 THEN
        RAISE NOTICE '沒有東西可刪，這個檔案先前已經跑過了。';
    ELSE
        -- 刪到一半代表資料庫的狀態跟我以為的不一樣。交易會回滾，
        -- 沒有把握就不要動——半刪掉的辯論比留著假資料更難查。
        RAISE EXCEPTION
            '預期刪除 0 或 2 列，實際刪除 % 列。資料庫狀態與預期不符，已回滾。',
            removed;
    END IF;
END $$;
