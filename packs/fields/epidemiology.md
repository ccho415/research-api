# Epidemiology Module

Sits on **`observational`** for cohort, case-control and cross-sectional work; on
**`experimental`** for randomised trials; on **`econometric`** when the identification
comes from a policy change or natural experiment.

Load alongside `clinical` when the population is patients, and alongside
`environmental-health` when the exposure is environmental.

## Checklists a reviewer will hold up

| Study type | Checklist | Version checked |
|---|---|---|
| Observational study reporting | **STROBE** | current |
| Risk of bias, exposure studies | **ROBINS-E** | 2024 |
| Risk of bias, non-randomised interventions | **ROBINS-I V2** | 2025-11 |
| Target trial emulation | **TARGET** — 21 items | 2025-09, JAMA |
| Certainty of evidence | **GRADE** | current |
| Prediction models | **TRIPOD+AI** | 2024 |
| Systematic review | **PRISMA** | 2020 |

Naming the checklist in a proposal is not decoration. A reviewer who sees TARGET cited
knows the time-zero question has been thought about; a reviewer who does not see it
assumes it has not.

## Named biases

These have names because reviewers use the names. A critique that says "there may be
selection issues" is weaker than one that says "this is immortal time bias".

- **Immortal time bias** — follow-up during which the outcome could not have occurred is
  attributed to the exposed group. Endemic in pharmacoepidemiology using prescription
  records.
- **Time-zero misalignment** — eligibility, treatment assignment and follow-up start must
  coincide. When they do not, the study is comparing people at different points in their
  disease course.
- **Healthy worker survivor effect** — remaining employed is a consequence of health,
  so occupational cohorts systematically understate harm.
- **Healthy user effect** — people who adhere to a treatment differ in every other health
  behaviour too.
- **Collider stratification bias** — adjusting for a variable caused by both exposure and
  outcome induces association where none exists. Adjusting for more covariates is not
  safer.
- **Competing risks** — death from another cause removes people from risk. Cause-specific
  hazards and cumulative incidence answer different questions; using the wrong one
  overstates risk.
- **Depletion of susceptibles** — in prevalent-user designs, the people most likely to be
  harmed have already left the cohort.
- **Detection bias** — exposure changes how hard anyone looks for the outcome.

## Causal inference expectations

- **Confounders are selected from a causal diagram**, not by stepwise regression or by
  what changed the estimate by 10%. Say the DAG exists and what it implies.
- **Target trial emulation** is now the default framing for a causal question asked of
  observational data. State the hypothetical trial: eligibility, treatment strategies,
  assignment, outcome, follow-up, causal contrast, analysis plan.
- **Negative controls** — an outcome the exposure cannot plausibly cause, or an exposure
  that cannot plausibly cause the outcome. Cheap and persuasive.
- **E-value** — how strong unmeasured confounding would have to be to explain the result
  away. Expected whenever unmeasured confounding is the obvious objection, which is
  always.
- **Triangulation** — agreement across designs with different, non-overlapping biases.

## Power and sample size

**An interaction needs roughly four times the sample of a main effect of the same size.**

This single fact kills more otherwise good ideas than anything else in the field. Any
direction whose core claim is effect modification — "the association differs in people
with X" — must be checked against it before it goes any further. A cohort adequately
powered for the main effect is usually not powered for the modifier that makes the
question interesting.

Related: subgroup analyses that were not pre-specified are hypothesis-generating, and
saying so in advance costs nothing and buys credibility.

## Tier B data

Joinable on **place × time** or **person × time** without new collection: air and water
quality monitoring, weather and climate reanalysis, census and deprivation indices, land
use and greenspace, policy implementation dates, disease surveillance, vaccination and
screening coverage, national vital statistics, drug approval and withdrawal dates.

## Impact anchors

Global Burden of Disease estimates, WHO and national registry burden, prevalence and size
of the exposed population, population attributable fraction, healthcare cost, guideline
thresholds, screening or treatment eligibility counts.

## Novelty conventions

A new population or setting alone is **replication** — worth doing, and it should be
called replication. Genuine novelty: an untested modifier or mediator with a mechanistic
reason to expect it; a better-identified design for a contested association; an exposure
or outcome that could not be measured until now; reconciling two literatures that
disagree; a well-powered null that overturns an assumed effect.

## What good looks like

Credit these when they are present — they are what separates a competent proposal from a
routine one, and they are easy to overlook when scanning for defects:

- The target trial is stated explicitly, including time zero
- The adjustment set comes from a diagram and the diagram's assumptions are stated
- A negative control or an E-value is planned, not just mentioned
- The direction of each anticipated bias is named, not just its existence
- Power is computed for the effect the paper is actually about
- The data linkage is genuinely hard to assemble and the authors have it
- A pre-specified analysis plan distinguishes confirmatory from exploratory

## What this module cannot see

- **Whether the clinical or biological mechanism is plausible.** It can tell you the
  design is sound and the estimate well identified while the hypothesis is nonsense.
- **Whether the exposure measurement is any good.** Load `environmental-health` or
  `measurement` for that.
- **Local data governance.** Whether a linkage is permitted, how long approval takes, and
  what the custodian will actually release are institution-specific and unknowable here.
- **Field-specific mechanistic literature.** A reviewer who knows the biology will raise
  objections no design checklist reaches.
