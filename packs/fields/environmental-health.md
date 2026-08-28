# Environmental Health Module

Sits on **`observational`** for population studies, **`measurement`** for exposure
assessment work, **`experimental`** for toxicology.

Load alongside `epidemiology` — this module carries the exposure-side technical content
that the general epidemiology frame does not.

## Checklists a reviewer will hold up

| What you are doing | Checklist | Version checked |
|---|---|---|
| Risk of bias in an exposure study | **ROBINS-E** — the core tool in this field | 2024 |
| Observational reporting | **STROBE** | current |
| Certainty of evidence | **GRADE**, adapted for environmental exposures | current |
| Air quality benchmarks | **WHO Global Air Quality Guidelines** | 2021 |
| Systematic review | **PRISMA 2020** | 2020 |

ROBINS-E is the one that matters here. It was built for exposure studies specifically,
and its exposure-measurement domain is where most environmental papers lose points.

## Exposure assessment — the technical core

This is what a general epidemiology frame misses, and it is where reviewers in this field
concentrate.

**How exposure gets estimated:**

- **Monitoring stations** — sparse, sited for regulatory compliance rather than for
  representing where people are, and often far from the study population
- **Land use regression (LUR)** — predicts concentration from land-use covariates.
  Performance is reported as cross-validated R², and cross-validation must be spatial or
  it is optimistic
- **Dispersion and chemical transport models** — physically grounded, resolution-limited
- **Satellite retrievals** — coverage where monitors are absent, at the cost of column
  versus surface concentration assumptions
- **Personal monitoring** — the closest to truth, and the least scalable
- **Biomarkers** — internal dose, but with half-lives that determine what window they
  represent. A biomarker with a six-hour half-life says nothing about chronic exposure.

**The misclassification direction is the point.**

Assigning an area-level concentration to an individual is exposure misclassification. If
it is non-differential with respect to the outcome, it biases the estimate **toward the
null**. The consequence a reviewer will state:

> **A positive finding under non-differential misclassification is conservative. A null
> finding is uninterpretable.**

Any direction whose contribution is a null result must address this or it is not a
finding. Any direction claiming precision must justify why misclassification is small.

Differential misclassification — where exposure error depends on outcome status, common
in retrospective self-report — can bias in either direction and has no such protection.

## Mixtures

Environmental exposures arrive together and correlate strongly. A single-pollutant model
in the presence of a correlated co-pollutant attributes the co-pollutant's effect to the
one you modelled.

- **BKMR** (Bayesian kernel machine regression) — non-linear, interactions, variable
  importance; computationally heavy
- **WQS** (weighted quantile sum) — a single mixture index with component weights;
  assumes all components act in the same direction unless the two-sided variant is used
- **Quantile g-computation** — relaxes the directional assumption, cheaper than BKMR
- **Elastic net / PCA** — dimension reduction, but the components are not interpretable
  as exposures

Naming the mixture method, and why that one, is expected in any proposal involving more
than one pollutant.

## Time windows

- **Distributed lag non-linear models (DLNM)** — the standard for exposure effects that
  are distributed over time, and for non-linear exposure–response
- **Critical windows** — susceptibility concentrated in a developmental period. A study
  averaging exposure over pregnancy when the effect is trimester-specific finds nothing.
- **Short-term versus chronic** — case-crossover for acute effects with the subject as
  their own control; cohorts for chronic. Mixing the two designs' interpretations is a
  common error.
- **Heat and temperature** — non-linear with a minimum-mortality temperature; adaptation
  and acclimatisation shift it by population.

## Tier B data

Regulatory monitoring networks, satellite products (MODIS AOD, TROPOMI), climate
reanalysis (ERA5), land cover and NDVI greenspace, road networks and traffic counts,
industrial emissions registries, water quality reporting, noise maps, census deprivation
indices, policy and regulation implementation dates.

Nearly all of it joins on **place × time**, which is what makes this field data-rich and
what makes exposure misclassification the central methodological problem.

## Impact anchors

Attributable burden (GBD environmental risk factors), WHO guideline values and the
population above them, size of the exposed population, regulatory limit values and
distance from them, economic cost of the burden, environmental justice differentials
across groups.

## Novelty conventions

Another city with the same pollutant and the same design is **replication**. Genuine
novelty: an exposure that could not be measured before, a mixture nobody has modelled
jointly, a critical window nobody has resolved, a susceptible subgroup with a mechanistic
reason, a policy change that provides identification, or a well-characterised null that
constrains a claimed effect.

## What good looks like

- The exposure assessment method is named, with its validation performance
- The direction of misclassification bias is stated, not just its presence
- A mixture method is used when there is a mixture, and the choice is justified
- The exposure window matches the hypothesised mechanism
- Spatial confounding is addressed rather than assumed away
- Personal or biomarker validation exists for a subset, even a small one
- The comparison population differs in exposure but not in everything else
- Environmental justice implications are examined rather than mentioned

## What this module cannot see

- **Whether the toxicological mechanism is plausible** at the concentrations studied.
  Population association at levels no mechanism supports is a real objection this module
  will not raise.
- **Local monitoring network quality.** Whether stations are well sited and well
  maintained for a given study area is unknowable here.
- **Regulatory and legal context** — what a limit value means in a given jurisdiction and
  whether exceeding it has consequences.
- **Atmospheric chemistry and transport detail.** A reviewer from that community will
  raise objections about secondary formation and speciation this module does not reach.
