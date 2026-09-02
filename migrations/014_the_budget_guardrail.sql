-- ============================================================
-- Token 預算護欄（PRD 第七節「三個貫穿全流程的機制」之二）
-- ============================================================
--
-- `run.token_budget` / `token_spent` / `token_usage` 這三樣在 schema 裡從第一天
-- 就存在，但**整份程式碼沒有任何一行碰過它們**。所以到今天為止，這個系統跑起來
-- 沒有任何東西會攔住失控的花費——一個寫錯的迴圈可以一路燒到帳單上才被發現。
--
-- 這次補的是真的會擋的那一版。
--
-- **單位改成美元。** 原本的 `token_budget` 是 bigint token 數，但不同模型每個
-- token 的價錢差五倍（Opus 5 輸出 $25／Haiku 4.5 輸出 $5），所以「還剩多少 token」
-- 回答不了「還剩多少錢」這個唯一有意義的問題。token 數繼續記在 `token_usage`
-- 裡供分析，護欄本身用美元。
--
-- **檢查點在階段邊界，不在階段中間。** 這是 PRD 明寫的，而且是對的：
-- 在第 300 場砍斷錦標賽，你會付掉三分之二的錢、拿到一個沒有意義的半套排名。
-- 要停就停在下一個階段開始之前。

ALTER TABLE run ADD COLUMN IF NOT EXISTS usd_budget numeric;
ALTER TABLE run ADD COLUMN IF NOT EXISTS usd_spent numeric NOT NULL DEFAULT 0;

ALTER TABLE run DROP CONSTRAINT IF EXISTS run_budget_not_negative;
ALTER TABLE run ADD CONSTRAINT run_budget_not_negative
    CHECK ((usd_budget IS NULL OR usd_budget >= 0) AND usd_spent >= 0);

-- 哪一個階段花的。沒有這欄就只知道「這次跑動花了 $3」，
-- 不知道錢在哪裡——而這個專案已經證明了，答案幾乎全在 W5。
ALTER TABLE token_usage ADD COLUMN IF NOT EXISTS stage text;

-- 快取讀取另計：命中的部分大約只算十分之一價，混進 input_tokens 會讓
-- 帳算得比實際貴，然後護欄會提早擋住一個其實還有預算的跑動。
ALTER TABLE token_usage ADD COLUMN IF NOT EXISTS cache_read_tokens bigint NOT NULL DEFAULT 0;

-- Batch API 是 50% 價。同一組 token 走批次或即時，價錢差一倍，
-- 不記下來就無法事後驗證改造到底省了多少。
ALTER TABLE token_usage ADD COLUMN IF NOT EXISTS batch boolean NOT NULL DEFAULT false;

CREATE INDEX IF NOT EXISTS token_usage_run_idx ON token_usage(run_id, recorded_at);
CREATE INDEX IF NOT EXISTS token_usage_stage_idx ON token_usage(stage);
