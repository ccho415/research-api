---
name: domain-profile
description: Resolve which research paradigm a topic belongs to and load the matching frame - how questions are posed, what counts as a contribution, what makes work wrong, what good work looks like, and what impact means in that field. Layers a field module on top for the checklists reviewers actually hold up. Loaded first by the research ideation skills so they reason in the field's own terms instead of defaulting to one discipline's template. Use at the start of any ideation, gap-finding, feasibility or critique task, or when work spans several fields.
license: MIT
metadata:
  version: "2.0.0"
---

# Domain Profile

Research fields do not just study different things — they **pose questions differently,
fail differently, and count contributions differently**. A framework that assumes one
paradigm produces confident nonsense in every other field: asking a mathematician about
confounders, or an epidemiologist about ablation studies.

This skill resolves the frame and loads it. **Every other skill in the ideation workflow
reads its frame from here** rather than hardcoding one.

The frame has two layers, and they answer different questions:

| Layer | Answers | Example |
|---|---|---|
| **Paradigm pack** | *What has to be true for the claim to hold?* | Groups were comparable; the baseline was fair; the proof is tight |
| **Field module** | *Which checklist will a reviewer actually hold up?* | ROBINS-E; CONSORT 2025; inter-patient splits; TRIPOD+AI |

Packs are the reasoning. Modules are the specifics reviewers name out loud. A pack alone
produces critique that is correct and generic — the kind that says "watch for data
leakage" to an EEG study whose real problem is that nobody removed eye-blink artifacts.

## Step 1 — Answer the three routing questions

Answer all three **before** opening any pack. They exist because the failure this skill
was rebuilt to fix was a routing failure, not a knowledge failure.

**Q1. What does the main claim rest on to be established?**
→ This is the **primary pack**. Match on how the claim is established, not on subject
matter. A physicist running a lab experiment uses `experimental`; a physicist proving a
bound uses `formal`.

**Q2. Is there a second thing that must also hold for the work to stand?**
→ **If the answer is anything other than a clear no, you MUST load a second pack.**
This is not a judgement call and not an optimisation.

A study of monkey electrophysiology that fits a computational model of the recorded
activity rests on two things: that the recordings mean what they are claimed to mean
(`experimental`), *and* that the model is evaluated honestly (`computational`). Routing
it to `experimental` alone produced critique that missed most of what expert reviewers
actually raised, because what they raised was about the model.

Ask it concretely: *if the second component were done badly, would the paper still
stand?* If no, that component's pack is mandatory.

**Q3. Which communities will the reviewers come from?**
→ This routes the **field modules** in Step 2, and it catches packs Q1 and Q2 missed. A
paper that will be read by both a cardiology journal and an ML venue has to satisfy both
audiences regardless of which pack you think is primary.

**If unsure about Q1, ask the user one question**: *how would a reviewer in your field
decide this work is wrong?* The answer routes immediately, and it is a better question
than asking what field they are in.

### Paradigm packs

| Pack | Establishes claims by | Typical fields |
|---|---|---|
| [`observational.md`](references/observational.md) | Comparing groups that were not assigned | Epidemiology, public health, environmental health, clinical outcomes, nutrition, sociology, ecology (field) |
| [`experimental.md`](references/experimental.md) | Manipulating a variable and measuring the effect | RCTs, lab biology, chemistry, experimental psychology, agriculture, materials testing |
| [`computational.md`](references/computational.md) | Beating or characterising a measurable baseline | ML, AI, NLP, CV, systems, bioinformatics, computational social science |
| [`formal.md`](references/formal.md) | Proof from stated assumptions | Mathematics, theoretical CS, theoretical physics, formal economics, logic |
| [`engineering.md`](references/engineering.md) | Building a thing that meets a specification | Systems, robotics, materials synthesis, chemical engineering, device design, software engineering |
| [`econometric.md`](references/econometric.md) | An identification strategy exploiting real-world variation | Economics, political science, policy evaluation, quantitative finance, health economics |
| [`interpretive.md`](references/interpretive.md) | Argued reading of sources or accounts | History, literature, philosophy, anthropology, qualitative social science, media studies |
| [`measurement.md`](references/measurement.md) | Showing an instrument measures what it claims | Psychometrics, assay and biomarker development, sensor validation, survey methodology, benchmark design |

## Step 2 — Layer on the field modules

Modules sit **on top of** packs; they do not replace them. The same module can sit on
different packs — epidemiology on `observational` for a cohort study, on `experimental`
for a trial — because a module carries the field's checklists and named biases, not its
notion of proof.

| Module | Load when the work involves | Sits most often on |
|---|---|---|
| [`epidemiology.md`](references/fields/epidemiology.md) | Population-level exposure–outcome inference, causal inference from non-randomised data | `observational`, `econometric` |
| [`clinical.md`](references/fields/clinical.md) | Patients, treatments, diagnosis, prognosis, real-world clinical data | `experimental`, `observational`, `measurement` |
| [`environmental-health.md`](references/fields/environmental-health.md) | Environmental exposures — air, water, noise, chemicals, heat | `observational`, `measurement` |
| [`physiological-signal-ai.md`](references/fields/physiological-signal-ai.md) | ECG, EEG, PPG or other waveform data with models fitted to it | `computational`, `measurement` |
| [`medical-imaging-ai.md`](references/fields/medical-imaging-ai.md) | Radiology, pathology or other medical images with models fitted to them | `computational`, `measurement` |

**Load every module Q3 implicates.** A wearable-PPG study predicting a clinical outcome
in a cohort needs `physiological-signal-ai` *and* `clinical` *and* often `epidemiology` —
three checklists, three sets of named failures, and reviewers from three communities.

**If no module fits, say so explicitly and continue with the pack alone.** Most fields
have no module here. Saying "no field module covers computational linguistics, so the
critique below is at the paradigm level only" is honest and useful. Silently proceeding
as though the pack were complete is not.

## Step 3 — Handle cross-domain work explicitly

Genuinely interdisciplinary work is the common case in this workflow, not the exception,
and it is where a single-paradigm framework does the most damage.

**Keep the packs separate. Do not average them.**

- Name the **primary** pack — whose standards the main claim must satisfy — and the
  **secondary** pack(s) contributing methods, data or constructs.
- Work must clear the validity bar of **every** pack it draws on. A machine-learning
  method applied to clinical prediction is judged on leakage and baselines *and* on
  confounding and population validity. Failing either sinks it.
- **The friction between packs is where the good questions are.** When two fields would
  call the same finding sound and unsound, that disagreement is usually a real,
  publishable problem — surface it rather than smoothing it over.
- Say which pack each generated direction is being judged under. A direction that is
  novel in one field and routine in the other is a translation, not a discovery — still
  potentially worth doing, but describe it honestly.

## Step 4 — Carry the blind spots forward

Every pack and module ends with **what it cannot see**. Those sections are not filler and
they are not optional reading.

**The frame must name its own blind spots, and downstream output must repeat them.**

Some critiques require deep, specific domain knowledge that no general checklist reaches.
A neuroscience proposal drew fourteen expert objections about attractor dynamics and
toroidal topology; a general frame caught one. The right response is to say *this frame
does not reach the dynamical-systems content of this proposal — a domain expert must read
it* rather than to produce eight generic points and imply coverage.

Claiming coverage you do not have is worse than admitting the gap, because it stops the
user from seeking the expert who would have caught the real problem.

## Step 5 — Emit the frame

```json
{
  "primary_pack": "observational",
  "secondary_packs": ["computational"],
  "second_pack_reason": "the risk score is a fitted model; if it were evaluated badly the finding would not stand",
  "field_modules": ["epidemiology", "physiological-signal-ai"],
  "reviewer_communities": ["cardiology", "machine learning"],
  "lit_search_domains": ["publichealth", "clinical", "ml"],
  "question_frame": "the field's own template for stating a question",
  "unit_of_contribution": "what a single publishable result is here",
  "generation_axes": ["from the pack - replaces any generic axis list"],
  "reporting_checklists": ["from the modules - what reviewers will hold up"],
  "validity_threats": ["what makes work wrong in this field"],
  "positioning_demands": ["which comparators, ablations and scope a reviewer will require"],
  "named_biases": ["from the modules - the ones reviewers name out loud"],
  "strength_markers": ["what good work looks like here, for crediting strengths"],
  "tier_b_sources": ["what is obtainable without new collection"],
  "impact_anchors": ["what counts as external evidence of importance"],
  "novelty_conventions": "what counts as new here",
  "blind_spots": ["what this frame cannot assess, stated plainly"]
}
```

Downstream: `gap-scan` takes `generation_axes`, `plausibility-check` takes
`validity_threats` and `named_biases`, `data-feasibility` takes `tier_b_sources`,
`impact-appraisal` takes `impact_anchors`, `novelty-check` takes `novelty_conventions`
and `positioning_demands`, `lit-search` takes `lit_search_domains`. **Every
critique-producing skill takes `strength_markers`, `positioning_demands` and
`blind_spots`.**

**Every critique-producing skill also runs the self-correction pass** in
[`plausibility-check`](../plausibility-check/SKILL.md) Step 3 before delivering — five
named tests against unsupported claims, reasoning gaps, generic findings, one-sidedness
and inflated severity, each with a disposition, and a report of what changed. It is the
cheapest quality step available and it is the one this frame does not otherwise contain:
the packs shape what you look for, and nothing in them checks what you then wrote.

`positioning_demands` is the one most easily left out and the one measurement showed
mattered most. A frame that produces only validity threats yields critique that is sound
and misplaced: reviewers spend as much effort on where a contribution sits relative to
existing work as on whether its result is real. Only `computational.md` carries a full
treatment so far; for other packs, derive it from their novelty conventions and say that
is what you did.

## Rules

- **Never apply one pack's standards to another pack's work.** Asking a formal paper for
  a power calculation, or a qualitative study for a control group, is a category error
  that discredits everything else in the review.
- **Credit strengths, not only defects.** Each pack states what good work looks like in
  that field. A critique that lists eight weaknesses and no strengths is not rigorous, it
  is miscalibrated — and measurably so: adding defect checklists without strength markers
  made strength identification *worse* than using no frame at all.
- **The packs are starting frames, not authorities.** Subfields have their own
  conventions. If the user says their field works differently, they are right — record
  the correction and use it.
- **When no pack fits, say so** and build the frame by asking the user the four questions
  the packs answer: how questions are posed, what a contribution is, what makes work
  wrong, and what impact looks like.
- **Checklist versions move.** The modules record the current version and the date it was
  checked. For reporting guidelines check EQUATOR Network, for bias tools riskofbias.info,
  for physiological signals PhysioNet, for wearables IEEE and AAMI.
