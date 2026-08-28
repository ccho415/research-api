# Observational Pack

Claims established by comparing groups that were **not** assigned by the researcher.

**Fields:** epidemiology, public health, environmental health, clinical outcomes and
pharmacoepidemiology, nutrition, occupational health, sociology, demography, field ecology.

**`lit-search` domains:** `publichealth`, `biomed`, `clinical`, `env`, `ecology`, `social`

## Question frame

**PECO / PICO** — Population, Exposure (or Intervention), Comparator, Outcome — plus two
things beginners omit and reviewers always ask for:

- **Time structure**: does exposure precede outcome, with what induction period?
- **Adjustment set**: which confounders must be controlled, justified by a causal diagram
  rather than by stepwise selection

State it as: *"Among [population], is [exposure] associated with [outcome] compared with
[comparator], over [period], adjusting for [set]?"*

## Unit of contribution

One well-identified association in a defined population. Also counts: an effect
modification nobody has tested, a mediation pathway, a replication in a population where
the effect might differ, a natural experiment, and a well-powered null that overturns an
assumed effect.

## Generation axes

| Axis | Ask |
|---|---|
| Population | Which group is understudied — age, region, comorbidity, occupation, minority? |
| Exposure | What variation is unseparated — dose, timing, duration, chronic vs acute, mixtures? |
| Outcome | What downstream effect is unmeasured — functional, long-term, patient-relevant? |
| Mechanism | What mediates the known association? |
| Effect modification | For whom is the effect different, and why would it be? |
| Confounding | Which prior finding is unconvincing because a confounder was unavailable? |
| Design | What natural experiment, instrument or policy change enables cleaner identification? |
| Contradiction | Where do cohorts disagree, and what population or measurement difference explains it? |
| Translation | What blocks the finding from changing practice or policy? |
| Temporal | What changed — new exposure, new measurement, new data linkage? |

## Data and artifacts

Cohorts, registries, claims and EHR data, surveys, surveillance systems, biobanks,
census and administrative records, environmental monitoring, linked record systems.

## Tier B — obtainable without new collection

Almost always joinable on **place × time** or **person × time**:

- Air quality, water quality, noise, weather and climate reanalysis
- Census composition, deprivation and area socioeconomic indices
- Land use, greenspace, walkability, facility and provider density
- Policy implementation dates, legislative changes
- Disease surveillance, vaccination and screening coverage
- National statistics: mortality, natality, migration, employment

**Aggregating area-level values onto individuals introduces exposure misclassification —
state the expected direction of bias.** Non-differential misclassification usually biases
toward the null, which makes a positive finding conservative but a null finding
uninterpretable.

## Validity threats

1. **Confounding** — named and measured, not "adjusted for covariates". Unmeasured
   confounding is the default objection; answer it with a negative control, an E-value,
   or a design that does not need the assumption
2. **Reverse causation** — especially where the outcome affects the exposure behaviour
3. **Selection bias** — loss to follow-up, healthy-worker effect, collider stratification
4. **Measurement error** — self-report, proxy exposure, outcome ascertainment differing
   by exposure status
5. **Immortal time bias** and other time-alignment errors in cohort construction
6. **Multiple comparisons** across many exposures or outcomes
7. **Power for interactions** — effect modification needs several times the sample of a
   main effect; this kills more plausible ideas than anything else here
8. **Generalisability** — from this cohort to the population that matters

## Impact anchors

Disease burden (GBD, WHO, national registries), prevalence and exposed population size,
attributable fraction, healthcare cost, guideline and policy thresholds, screening or
treatment eligibility counts, exposure limit values.

## Novelty conventions

A new population or setting alone is **replication**, not novelty — worth doing, but say
so. Genuine novelty: an untested modifier or mediator, a better-identified design for a
contested association, an exposure or outcome nobody has been able to measure until now,
or reconciling two literatures that disagree.

## What good looks like

- Confounders are named and their measurement described, not summarised as "covariates"
- The adjustment set follows from a causal diagram whose assumptions are stated
- The direction of each anticipated bias is given, not just its existence
- Time zero is defined, and eligibility, assignment and follow-up start together
- A negative control or E-value is part of the design rather than a response to review
- Power is computed for the effect the study is actually about, interactions included
- The data linkage is genuinely difficult to assemble and the authors have it
- A null result is interpreted only where measurement error would not have produced it

## What this pack cannot see

- **Whether the hypothesised mechanism is biologically or socially plausible.** A
  perfectly identified estimate of a nonsensical relationship still passes every check
  here.
- **Exposure measurement quality** - load `measurement`, or the `environmental-health`
  field module for environmental exposures.
- **Data governance and access timelines**, which are institution-specific.
- **Field-specific literature.** Load the `epidemiology`, `clinical` or
  `environmental-health` field modules for the checklists and named biases reviewers in
  those communities actually raise.
