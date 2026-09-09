-- A stage that is running writes nothing until it finishes, so "still working"
-- and "never started" look identical on every screen. On 2026-09-09 a
-- tournament sat in Anthropic's batch queue for three hours and forty minutes
-- with zero requests completed, and the only evidence that distinguished stuck
-- from slow lived inside an n8n execution log that nobody would think to open.
--
-- These two columns are where a stage says what it is doing while it does it.
--
--   reported_at  when it last said anything
--   report       what it said - stage-specific, free shape on purpose
--
-- `report` is deliberately not a fixed schema. What counts as progress differs
-- per stage: a batch reports how many of its requests have completed, a search
-- reports how many queries are done, a debate reports which round it is on.
-- Forcing one shape would mean each stage reporting the least useful thing they
-- have in common.
--
-- The final report a stage leaves behind stays in the same column. For the
-- tournament that is its quality gates - which until now were computed, pushed
-- to LINE, and then lost. `order_flip_rate` in particular was measured on every
-- run and stored nowhere, so no screen could show it and no run could be
-- compared with the last one.

ALTER TABLE run ADD COLUMN IF NOT EXISTS reported_at timestamptz;
ALTER TABLE run ADD COLUMN IF NOT EXISTS report      jsonb;

-- Finding the row a stage should report into means "the active row for this
-- project and stage", which is the same lookup the pause switch and the
-- dispatcher already do.
CREATE INDEX IF NOT EXISTS run_project_stage_status_idx
    ON run(project_id, stage, status);
