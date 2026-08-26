-- ============================================================
-- 研究方向發想系統 · 資料表結構
-- 目標資料庫：research（不是 n8n 自己用的 zeabur）
-- 全部使用 IF NOT EXISTS，重複執行不會出錯
-- ============================================================
-- 注意：資料表 tournament_match 原本在 PRD 裡叫 match，
-- 但 MATCH 是 PostgreSQL 的保留字，用它當表名每次都要加引號，
-- 所以改名。其他表名都沒有這個問題。
-- ============================================================


-- ─── 第 1 批：專案與執行 ────────────────────────────────────
CREATE TABLE IF NOT EXISTS project (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    title         text NOT NULL,
    topic         text NOT NULL,
    domain_frame  jsonb,
    constraints   jsonb,
    status        text NOT NULL DEFAULT 'created',
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS run (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id       uuid NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    stage            text NOT NULL,
    status           text NOT NULL DEFAULT 'pending',
    params           jsonb,
    error            text,
    pause_after      boolean NOT NULL DEFAULT false,
    auto_advance_to  text,
    token_budget     bigint,
    token_spent      bigint NOT NULL DEFAULT 0,
    started_at       timestamptz,
    finished_at      timestamptz
);
CREATE INDEX IF NOT EXISTS run_project_idx ON run(project_id, stage);

CREATE TABLE IF NOT EXISTS skill_prompt (
    key         text NOT NULL,
    version     integer NOT NULL DEFAULT 1,
    content     text NOT NULL,
    updated_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (key, version)
);


-- ─── 第 2 批：文獻快取 ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS paper (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    doi          text,
    pmid         text,
    openalex_id  text,
    title        text NOT NULL,
    abstract     text,
    year         integer,
    venue        text,
    authors      jsonb,
    citations    integer,
    url          text,
    source       text NOT NULL,
    mesh         jsonb,
    fetched_at   timestamptz NOT NULL DEFAULT now()
);
-- 同一篇論文只存一次；DOI 與 PMID 各自唯一（NULL 不受限制）
CREATE UNIQUE INDEX IF NOT EXISTS paper_doi_idx  ON paper(doi)  WHERE doi  IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS paper_pmid_idx ON paper(pmid) WHERE pmid IS NOT NULL;

CREATE TABLE IF NOT EXISTS search_query (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id       uuid REFERENCES run(id) ON DELETE CASCADE,
    query_text   text NOT NULL,
    domain       text,
    sources      jsonb,
    query_angle  text,   -- 這一輪用什麼角度查（強制不重複）
    axis_source  text,   -- topic / method / crossed
    n_hits       integer,
    executed_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS search_hit (
    search_query_id uuid NOT NULL REFERENCES search_query(id) ON DELETE CASCADE,
    paper_id        uuid NOT NULL REFERENCES paper(id) ON DELETE CASCADE,
    rank            integer,
    PRIMARY KEY (search_query_id, paper_id)
);


-- ─── 第 3 批：資料清單與研究背景檔 ──────────────────────────
CREATE TABLE IF NOT EXISTS dataset (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id   uuid NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    filename     text,
    pack         text,
    inventory    jsonb NOT NULL,   -- 只存欄位資訊，永不存原始資料列
    pii_columns  jsonb,
    profiled_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS research_profile (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id   uuid NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    version      integer NOT NULL DEFAULT 1,
    content      jsonb NOT NULL,
    uploaded_at  timestamptz NOT NULL DEFAULT now(),
    derived_from uuid REFERENCES research_profile(id)
);


-- ─── 第 4 批：研究方向與去重 ────────────────────────────────
CREATE TABLE IF NOT EXISTS idea (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          uuid NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    code                text,
    title               text NOT NULL,
    statement           text NOT NULL,
    axis                text,
    track               text,        -- asset-driven / data-blind
    origin              text NOT NULL DEFAULT 'generated',  -- generated / external
    source_note         text,        -- 外部來源說明
    required_variables  jsonb,
    method_sketch       jsonb,       -- 三個具名關鍵組件
    grounding           jsonb,
    why_matters         text,
    how_could_fail      text,
    parent_idea_id      uuid REFERENCES idea(id) ON DELETE SET NULL,
    generation          integer NOT NULL DEFAULT 0,
    status              text NOT NULL DEFAULT 'candidate',
    created_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idea_project_idx ON idea(project_id, status);

CREATE TABLE IF NOT EXISTS dedup_pair (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id      uuid REFERENCES run(id) ON DELETE CASCADE,
    idea_a      uuid NOT NULL REFERENCES idea(id) ON DELETE CASCADE,
    idea_b      uuid NOT NULL REFERENCES idea(id) ON DELETE CASCADE,
    score       numeric,
    cosine      numeric,
    jaccard     numeric,
    verdict     text,      -- duplicate / distinct
    decided_by  text,      -- ai / human
    decided_at  timestamptz
);


-- ─── 第 5 批：錦標賽 ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS anchor (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source              text,
    external_id         text,
    title               text NOT NULL,
    statement           text,
    evidence            jsonb,
    grade_contribution  text,   -- 只有這一欄拿來校準 Elo
    grade_feasibility   text,   -- 這一欄校準 A/B/C/D 分級
    origin              text NOT NULL DEFAULT 'local',  -- scholarideas / local
    field               text,
    added_at            timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tournament (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id  uuid NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    run_id      uuid REFERENCES run(id) ON DELETE CASCADE,
    criteria    jsonb,
    k_factor    numeric NOT NULL DEFAULT 32,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tournament_match (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tournament_id  uuid NOT NULL REFERENCES tournament(id) ON DELETE CASCADE,
    batch          integer,   -- 同一對的兩個順序必須落在不同批次
    left_idea      uuid NOT NULL REFERENCES idea(id) ON DELETE CASCADE,
    right_idea     uuid NOT NULL REFERENCES idea(id) ON DELETE CASCADE,
    winner         text,
    reason         text,
    judged_by      text,
    judged_at      timestamptz
);
CREATE INDEX IF NOT EXISTS match_tournament_idx ON tournament_match(tournament_id, batch);

CREATE TABLE IF NOT EXISTS ranking (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tournament_id     uuid NOT NULL REFERENCES tournament(id) ON DELETE CASCADE,
    idea_id           uuid NOT NULL REFERENCES idea(id) ON DELETE CASCADE,
    elo               numeric,
    wins              integer NOT NULL DEFAULT 0,
    losses            integer NOT NULL DEFAULT 0,
    ties              integer NOT NULL DEFAULT 0,
    rank              integer,
    calibration_band  text
);


-- ─── 第 6 批：新穎性與可行性 ────────────────────────────────
CREATE TABLE IF NOT EXISTS novelty_check (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    idea_id          uuid NOT NULL REFERENCES idea(id) ON DELETE CASCADE,
    run_id           uuid REFERENCES run(id) ON DELETE CASCADE,
    verdict          text,     -- scooped / incremental / adjacent / no_prior_art
    rounds           jsonb,    -- 每輪的查詢字串與命中數
    closest_papers   jsonb,
    coverage_limits  text,
    checked_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS feasibility (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    idea_id           uuid NOT NULL REFERENCES idea(id) ON DELETE CASCADE,
    dataset_id        uuid REFERENCES dataset(id) ON DELETE SET NULL,
    tier              text,     -- A / B / C / D
    missing           jsonb,
    route_to_tier_a   text,
    design            text,
    power_note        text,
    assessed_at       timestamptz NOT NULL DEFAULT now()
);


-- ─── 第 7 批：唱反調辯論 ────────────────────────────────────
CREATE TABLE IF NOT EXISTS debate_round (
    id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    idea_id                 uuid NOT NULL REFERENCES idea(id) ON DELETE CASCADE,
    round_no                integer NOT NULL,
    proposer_model          text,
    critic_model            text,   -- 必須與 proposer_model 不同
    idea_version_before     text,
    idea_version_after      text,
    novelty_recheck_id      uuid REFERENCES novelty_check(id) ON DELETE SET NULL,
    closest_paper_distance  numeric,  -- 新穎性軌跡：變遠才是真的改進
    drift_from_original     numeric,  -- 超標就強制停，優先於輪數上限
    n_objections_open       integer,
    terminated              boolean NOT NULL DEFAULT false,
    termination_reason      text,
    created_at              timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS debate_idea_idx ON debate_round(idea_id, round_no);

CREATE TABLE IF NOT EXISTS objection (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    debate_round_id   uuid NOT NULL REFERENCES debate_round(id) ON DELETE CASCADE,
    statement         text NOT NULL,
    severity          text,   -- major / minor
    axis              text,   -- contribution / novelty / soundness / feasibility
    cited_paper_id    uuid REFERENCES paper(id) ON DELETE SET NULL,
    citation_support  text,   -- strong / weak / irrelevant
    rebuttal          text,
    rebuttal_score    integer,   -- 1–5，3 分以下不讓步
    status            text       -- resolved_by_evidence / resolved_by_revision / unresolved
);


-- ─── 第 8 批：決策紀錄與營運 ────────────────────────────────
CREATE TABLE IF NOT EXISTS decision_log (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id  uuid NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    idea_id     uuid REFERENCES idea(id) ON DELETE SET NULL,
    action      text NOT NULL,   -- accepted / rejected / merged / parked
    rationale   text,
    actor       text,            -- ai / human
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS token_usage (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id         uuid REFERENCES run(id) ON DELETE CASCADE,
    model          text NOT NULL,
    input_tokens   bigint NOT NULL DEFAULT 0,
    output_tokens  bigint NOT NULL DEFAULT 0,
    cost_usd       numeric,
    recorded_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS eval_run (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    benchmark  text NOT NULL,
    sample     jsonb,
    coverage   jsonb,
    baseline   jsonb,
    ran_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS health_metric (
    id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id  uuid REFERENCES run(id) ON DELETE CASCADE,
    metric  text NOT NULL,   -- order_flip_rate / cross_model_match_agreement / ...
    value        numeric,
    recorded_at  timestamptz NOT NULL DEFAULT now()
);
