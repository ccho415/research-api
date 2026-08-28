# Clinical Medicine Module

Sits on **`experimental`** for trials, **`observational`** for real-world data,
**`measurement`** for diagnostic and prognostic model work.

Load alongside `epidemiology` whenever the inference is causal and the data are not
randomised.

## Checklists a reviewer will hold up

| What you are doing | Checklist | Version checked | What it catches first |
|---|---|---|---|
| Randomised trial, reporting | **CONSORT 2025** | 2025 | Non-inferiority margin, ITT vs per-protocol, surrogate endpoints |
| Randomised trial, protocol | **SPIRIT 2025** | 2025 | Pre-specification, outcome switching |
| Estimands and intercurrent events | **ICH E9(R1)** | current | What the effect estimate actually refers to |
| Real-world / non-randomised | **TARGET**, **ROBINS-I V2** | 2025-09, 2025-11 | Time zero, healthy user effect |
| Diagnostic accuracy | **STARD** | 2015 | Spectrum bias, verification bias |
| Diagnostic accuracy with AI | **STARD-AI** | 2025, Nature Medicine | Reader studies, deployment gap |
| Prediction model | **TRIPOD+AI** | 2024 | Calibration, external validation |
| Early clinical evaluation of AI | **DECIDE-AI** | current | Human factors, clinician–model interaction |
| Prospective AI trial | **CONSORT-AI** | current | Intended use, error analysis |
| Systematic review | **PRISMA 2020**, **RoB 2**, **GRADE** | current | Heterogeneity, publication bias |

## Named problems by study type

**Randomised trials**

- **Non-inferiority margin** chosen without justification, or chosen so wide that a worse
  treatment passes. The margin is the whole trial; a reviewer reads it first.
- **ITT vs per-protocol** — ITT preserves randomisation and estimates the effect of
  assignment; per-protocol estimates something else and is not randomised. Reporting only
  per-protocol is a red flag.
- **Surrogate endpoints** — a change in a biomarker is not a change in outcome unless the
  surrogate has been validated for that setting. Most have not.
- **Estimands** — ICH E9(R1) asks what happens to the estimate when patients stop
  treatment, switch, or die. "We analysed everyone who had data" is not an answer.
- **Composite endpoints** driven by the least important component.

**Real-world and observational clinical data**

- **Time zero** and immortal time — see `epidemiology`; this is the single most common
  fatal flaw in EHR and claims studies.
- **Healthy user effect** and adherence as a proxy for everything else.
- **Confounding by indication** — the reason a treatment was given predicts the outcome.
  This is the objection; a design that does not address it is not publishable.
- **EHR data are a record of care, not of health.** Missingness is informative: a test
  result is absent because nobody ordered it, and why nobody ordered it is prognostic.

**Diagnostic and prognostic models**

- **Spectrum bias** — accuracy measured in obviously-sick versus obviously-well patients
  does not transfer to the borderline patients the test is for.
- **Calibration versus discrimination** — AUC says the model ranks patients correctly; it
  says nothing about whether predicted risks are right. A model with excellent AUC and
  bad calibration is dangerous in the clinic. Report both, with a calibration plot.
- **External validation** in a population and time period the model was not developed in.
  Internal cross-validation is not external validation.
- **Verification bias** — the reference standard is applied only to people who tested
  positive.
- **Decision curve analysis** — whether using the model beats treating everyone or nobody
  at a clinically defensible threshold. Increasingly expected.

## Question frame

**PICO** — Population, Intervention, Comparator, Outcome — plus, for anything
non-randomised, the target trial's time zero, and for anything predictive, the intended
decision the prediction supports.

State it as: *"In [patients], does [intervention/model] compared with [comparator] change
[clinically meaningful outcome] over [horizon]?"*

A direction that cannot name the decision that would change is a measurement exercise,
not a clinical study. Say so.

## Unit of contribution

A change in what a clinician should do, or evidence that a common practice does not help.
Also counts: a validated prediction that alters triage, a harm signal, a well-powered
null against a widely used treatment, a de-implementation finding.

## Tier B data

Registries and disease-specific cohorts, national claims and insurance databases, EHR
warehouses, trial data-sharing platforms (Vivli, YODA, CSDR), open ICU datasets
(MIMIC-IV, eICU), biobanks with linked outcomes, drug approval and label change dates,
guideline publication dates.

## Impact anchors

Incidence and prevalence, mortality and readmission rates, cost per case, guideline
recommendation strength, number needed to treat, eligibility population size, time to
diagnosis in current practice.

## Novelty conventions

Applying an established method to a new disease is **translation** — publishable, but it
should be described as translation. Genuine novelty: a decision that changes, a harm
nobody had looked for, a mechanism-informed subgroup, a head-to-head comparison nobody
had done, or a negative result that removes a treatment from practice.

## What good looks like

- The clinical decision the work would change is named, in a sentence, up front
- Outcomes are patient-relevant rather than convenient
- The comparator is what patients actually receive now, not placebo when placebo is not
  the alternative
- Time zero is defined and defensible
- Calibration is reported alongside discrimination
- External validation is planned in a population that differs in a way that matters
- Harms are collected as deliberately as benefits
- The analysis plan is registered before data are seen

## What this module cannot see

- **Whether the disease biology supports the hypothesis.** A specialist will raise
  objections about mechanism, phenotype definition, and disease heterogeneity that no
  reporting checklist reaches.
- **Whether the clinical workflow can absorb the intervention.** Feasibility in a clinic
  is a human-factors question; `DECIDE-AI` names it but this module cannot assess it.
- **Local practice variation.** What counts as standard care differs by country, payer
  and institution, and that changes whether a comparator is honest.
- **Whether the data custodian will grant access**, and on what timeline.
