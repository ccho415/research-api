# Econometric Pack

Claims established by an **identification strategy** that exploits real-world variation
the researcher did not create. Shares data with the observational pack but judges work on
the credibility of the identification argument, not on the adjustment set.

**Fields:** economics, political science, policy evaluation, health economics, quantitative
finance, education policy, criminology, quantitative sociology.

**`lit-search` domains:** `econ`, `social`, `edu`, `publichealth`

## Question frame

**Treatment / Outcome / Source of variation / Identifying assumption / Estimand.**

State it as: *"What is the causal effect of [treatment] on [outcome], identified from
[source of variation], under [assumption], for [which population]?"*

The **estimand** clause matters more here than anywhere else: ATE, ATT and LATE are
different quantities, and an instrument identifies an effect only for compliers. Naming
which one you get — and for whom — is half the contribution.

## Unit of contribution

One credibly identified causal effect. Also counts: a new source of exogenous variation,
showing an accepted identification strategy fails, a heterogeneity result that reconciles
conflicting estimates, and a structural estimate enabling counterfactual policy simulation.

## Generation axes

| Axis | Ask |
|---|---|
| New variation | What policy change, lottery, discontinuity, boundary or shock is unexploited? |
| Assumption failure | Which published result rests on a parallel-trends or exclusion assumption that is testably wrong? |
| Estimand | Whose effect was actually estimated, and does the policy question need a different one? |
| Heterogeneity | Which subgroup drives the average, and does the sign differ across groups? |
| Mechanism | Through what channel does the effect operate? Usually assumed, rarely tested |
| General equilibrium | Does the partial-equilibrium estimate survive scaling the policy up? |
| Long run | Do short-run effects persist, fade, or reverse? |
| External validity | Does the effect transfer to another country, period or institutional setting? |
| Measurement | What newly available administrative or digital data makes an old question answerable? |
| Replication | Which influential finding fails under a modern estimator? |

The **staggered difference-in-differences literature** is a live example of the assumption-
failure axis: a methodological correction invalidated a large body of published estimates.
Look for the equivalent in your subfield.

## Data and artifacts

Administrative registers, panel surveys, census microdata, firm and tax records, market and
transaction data, linked employer-employee data, policy timing databases, election and
legislative records.

## Tier B — obtainable without new collection

- Public microdata: IPUMS, LIS, national statistical office public-use files
- Panel surveys with open or light-application access: PSID, HRS, SHARE, Understanding
  Society, national household panels
- World Bank, OECD, IMF, Eurostat, national statistics portals
- Policy timing and legislative databases; court and regulatory records
- Replication packages from published papers — the fastest route to a heterogeneity or
  robustness contribution
- Scraped or digitised public records, where terms permit

**Restricted administrative data is the classic Tier C**: obtainable, but through an
application with a named holder, a review process, a secure enclave, and a timeline in
months. Say the months out loud — it is often the deciding factor for a thesis.

## Validity threats

1. **The identifying assumption is not credible** — parallel trends, exclusion restriction,
   continuity at the cutoff, conditional independence. This is the whole ballgame
2. **Weak instruments** — biased toward OLS, with unreliable inference
3. **Pre-trends** — not tested, or tested with too little power to detect a violation
4. **Staggered adoption with heterogeneous effects** — two-way fixed effects is biased;
   negative weights can flip the sign
5. **Spillovers to the control group** — violates SUTVA, biases the comparison
6. **Selection into treatment** on unobserved characteristics
7. **Inference** — clustering at the wrong level, few treated clusters, serial correlation
8. **Specification search** — many plausible specifications, one reported
9. **External validity** — a LATE for a narrow complier group presented as a policy effect

## Impact anchors

Population affected by the policy, fiscal cost or saving, welfare effect, elasticity
magnitude compared with the literature, whether it settles a live policy debate, and
whether an agency or legislature is currently deciding on it.

## Novelty conventions

A new outcome on a known natural experiment is incremental. Strong novelty: a genuinely
new source of variation, showing a canonical result does not survive a correct estimator,
credible heterogeneity that explains why the literature disagrees, or the first credible
identification of an effect everyone has only estimated by correlation.

## What good looks like

- The identifying assumption is stated as an assumption and defended on its own terms
- Pre-trends are tested with enough power that a null is informative
- The estimator suits the adoption structure, and modern alternatives to two-way fixed
  effects are considered where adoption is staggered
- Instrument strength is reported, not just instrument existence
- Inference is clustered at the level of treatment assignment
- Robustness is a specification curve, not three hand-picked alternatives
- The estimand is named - LATE, ATT, ATE - and its population described
- Spillovers are addressed rather than assumed away

## What this pack cannot see

- **Whether the policy question matters.** A beautifully identified effect of something
  nobody can change is still an identified effect.
- **Institutional detail** that decides whether the assumption is credible - how the
  policy was actually implemented, and who really complied.
- **Data access timelines** for administrative and register data, often the binding
  constraint.
- **Whether the mechanism behind a reduced-form effect is the claimed one.**
