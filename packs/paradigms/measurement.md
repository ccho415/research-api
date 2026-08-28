# Measurement Pack

Claims established by showing an **instrument measures what it claims to measure**. The
object of study is the measuring tool, not the phenomenon.

**Fields:** psychometrics and scale development, assay and biomarker development, sensor
and device validation, survey methodology, diagnostic test evaluation, benchmark and
metric design, wearable and digital-phenotype validation.

**`lit-search` domains:** `psych`, `biomed`, `clinical`, `stats`, `eng`, `edu`

## Question frame

**Construct / Instrument / Reference standard / Population / Conditions of use.**

State it as: *"Does [instrument] measure [construct] validly and reliably in [population],
against [reference standard], under [conditions], and within what limits?"*

**Naming the reference standard is the hard part.** Where no gold standard exists — which
is most interesting cases — say so and state what you are using instead and what that
substitution costs. Validating against an imperfect reference bounds the apparent accuracy
you can ever observe.

## Unit of contribution

Evidence for one aspect of validity or reliability in one population, a new instrument
that measures something previously unmeasurable, a demonstration that a widely-used
instrument is invalid for a population it is applied to, or a shortened or cheaper form
retaining acceptable properties.

## Generation axes

| Axis | Ask |
|---|---|
| Construct validity | Does the widely-used instrument actually measure the named construct? |
| Population invariance | Does it behave the same across age, culture, language, sex, disease severity? |
| Reference standard | What is validated only against another unvalidated instrument? |
| Responsiveness | Does it detect change, not just differences between people? |
| Feasibility | Can it be made shorter, cheaper, faster, or self-administered? |
| New modality | What can a new sensor, assay or data source measure that was inaccessible? |
| Error structure | What is the measurement error, and does it depend on the true value? |
| Threshold | Where is the cut-off, who set it, and on what population? |
| Misuse | What instrument is routinely used outside its validated conditions? |
| Metric design | Does the field's standard metric reward the wrong thing? |

**"Widely used but never properly validated in this population" is the single most
productive axis** in this pack, and such instruments are everywhere.

## Data and artifacts

Validation samples, paired measurements against a reference, test-retest data, item
response data, calibration standards, reference materials, inter-rater datasets,
instrument specifications, annotation guidelines.

## Tier B — obtainable without new collection

- Existing cohort or trial data containing both the instrument and a reference measure —
  the cheapest route to a validation study
- Public item-response and psychometric datasets; open survey archives
- Reference materials and calibration standards (NIST, WHO international standards)
- Published inter-laboratory comparison and ring-trial data
- Open benchmark annotations with multiple annotators, for reliability analysis
- Instrument manuals and prior validation studies, for meta-analytic reliability

## Validity threats

1. **Circular validation** — validated against another instrument that was itself never
   validated
2. **Spectrum bias** — validated on clear cases, applied to ambiguous ones, so accuracy
   collapses in practice
3. **Imperfect reference standard** treated as a gold standard, bounding observable accuracy
4. **Measurement invariance untested** across the groups being compared. Without it, group
   differences may be instrument artefacts, not real differences
5. **Reliability confused with validity** — a consistently wrong instrument is highly reliable
6. **Overfitted cut-off** derived and evaluated on the same sample
7. **Range restriction** inflating or deflating correlations
8. **Ceiling and floor effects**
9. **Reactivity** — measuring changes what is measured
10. **Construct drift** — the instrument still runs while the construct has moved on

## Impact anchors

How widely the instrument is used and in how many studies, decisions it drives (diagnosis,
eligibility, funding allocation, hiring, model selection), cost and burden per
administration, whether misclassification has documented harms, and how much downstream
literature would be affected if it is invalid.

**Invalidating a widely-used instrument has unusually high impact** — it propagates to
every study that used it.

## Novelty conventions

Yet another scale for a well-measured construct is weak and the literature is saturated
with them. Strong novelty: showing an established instrument fails in a population where
it is routinely used, measuring something previously unmeasurable, quantifying an error
structure everyone has assumed away, or demonstrating that a field's standard metric
rewards the wrong behaviour. **Check reporting standards for the pack's own conventions
(COSMIN, STARD, GRRAS) and follow them** — reviewers in these fields apply them strictly.

## What good looks like

- The reference standard is named, with its own error characteristics
- Validation spans the ambiguous cases the instrument is actually for
- Measurement invariance is tested across every group that will be compared
- Reliability and validity are reported separately and not conflated
- Cut-offs are derived and evaluated on different samples
- Agreement is analysed as agreement (Bland-Altman, ICC), not as correlation
- The construct definition precedes the instrument rather than following from it
- Failure conditions are stated: where the instrument should not be used

## What this pack cannot see

- **Whether the construct is worth measuring**, or even coherent. Construct definition is
  a theoretical question this pack takes as settled.
- **Domain-specific reference standards.** Load `clinical` for diagnostic accuracy
  conventions, `physiological-signal-ai` for waveform devices, `environmental-health` for
  exposure assessment.
- **Administration burden in practice** - what respondents, clinicians or operators will
  actually tolerate.
- **Whether existing instruments already do this.** The scale literature is vast, poorly
  indexed, and full of near-duplicates under different names.
