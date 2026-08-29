-- ============================================================
-- 讓錨點也能被機械查核
-- ============================================================
--
-- 首跑（執行 116）抓到的：一個 weak 錨點排到第二名，贏過一個 strong 錨點。
--
-- 錯位不是隨機的。CGM × 腸道菌相之所以標 weak，理由是「已被 Zeevi et al.,
-- Cell 2015 佔據」——這件事寫在 `evidence` 欄，而**裁判看不到 evidence**。
-- 它只讀得到那句敘述，而那句敘述本身完全合理。凡是「弱在已經被做過」的錨點，
-- 裁判在結構上不可能判對。相對地「弱在設計本身」的那筆（營養素觀察性研究）
-- 就準確落到最後段。
--
-- 修法是讓錨點也帶文獻計數，跟方向一樣。順帶解掉先前記錄的殘留洩漏：
-- 錨點沒有計數、方向有，光憑「有沒有數字」就分得出誰是錨點。
--
-- **切點必須逐筆存，不能共用。** 拿跑動的切點 2015 去量 CRISPR（2012 提出），
-- `papers_before` 會是幾千篇，裁判讀成「早就有人做了」——一個 strong 錨點被打到底，
-- 剛好把要修的刻度反向弄壞。正確語意是「這個方向被提出的當下，這條線做了多少」。
--
-- `term_groups` 為 NULL 是合法的。有些錨點是**設計**而不是題目
-- （「在沒有事前分析計畫的資料集裡搜尋關聯」），沒有任何檢索詞能誠實代表它，
-- 硬編一組出來就是捏造。那些錨點的弱本來就寫在敘述裡，不需要計數也判得對。

ALTER TABLE anchor ADD COLUMN IF NOT EXISTS term_groups jsonb;
ALTER TABLE anchor ADD COLUMN IF NOT EXISTS cutoff integer;

-- 切點要嘛沒有、要嘛是個年份。存了 20 或 202026 會讓計數安靜地變成垃圾。
ALTER TABLE anchor DROP CONSTRAINT IF EXISTS anchor_cutoff_is_a_year;
ALTER TABLE anchor ADD CONSTRAINT anchor_cutoff_is_a_year
    CHECK (cutoff IS NULL OR (cutoff BETWEEN 1800 AND 2100));

-- 有檢索詞就必須有切點：沒有切點的計數不知道是哪一年之前的，讀不出意思。
ALTER TABLE anchor DROP CONSTRAINT IF EXISTS anchor_terms_need_a_cutoff;
ALTER TABLE anchor ADD CONSTRAINT anchor_terms_need_a_cutoff
    CHECK (term_groups IS NULL OR cutoff IS NOT NULL);
