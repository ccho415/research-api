# Experimental Pack

Claims established by **manipulating a variable** and measuring what changes.

**Fields:** randomised trials, laboratory biology and biochemistry, bench chemistry,
experimental and cognitive psychology, animal studies, agriculture and field trials,
materials testing, human factors.

**`lit-search` domains:** `biomed`, `clinical`, `psych`, `chem`, `materials`, `ecology`

## Question frame

**Manipulation / Units / Control / Outcome / Conditions.**

State it as: *"In [units/model system], does [manipulation] change [outcome] relative to
[control], under [conditions], by [expected magnitude]?"*

The **expected magnitude** clause is not optional — it determines the sample size, and an
experiment powered for an implausibly large effect is a waste of animals, participants or
reagents before it starts.

## Unit of contribution

One causal effect demonstrated under controlled conditions. Also counts: a mechanism
established by manipulating an intermediate step, a boundary condition where a known
effect disappears, a failed replication of an influential result, and a method that makes
a previously impossible manipulation feasible.

## Generation axes

| Axis | Ask |
|---|---|
| Manipulation | What has only been observed correlationally and could now be manipulated directly? |
| Mechanism | Which step in the accepted pathway has never been intervened on? |
| Dose / gradient | Is the response linear, threshold, or non-monotonic? Almost never tested |
| Boundary | Under what conditions does the effect vanish or reverse? |
| Model system | What does the standard model organism, cell line or participant pool fail to represent? |
| Timing | Does when the manipulation happens change the result — critical periods, order effects? |
| Combination | What interaction between two manipulations is untested? |
| Replication | Which influential effect has a shaky evidence base? |
| Measurement | What new instrument or assay makes an old question newly answerable? |
| Ecological validity | Does the lab effect survive realistic conditions? |

## Data and artifacts

Trial data, lab measurements, instrument output, imaging, sequencing and omics, behavioural
task data, specimens and cell lines, protocols, pre-registrations.

## Tier B — obtainable without new collection

- Public repositories: GEO, SRA, ArrayExpress, PDB, ChEMBL, PubChem, OpenNeuro, PsychArchives
- Trial registries and results databases; individual participant data on request
- Published supplementary datasets and figure source data
- Reference cell lines, plasmid and strain repositories (Addgene, ATCC), reagent catalogues
- Shared core-facility instrument time
- Existing specimens with an ethics amendment — often faster than new collection

## Validity threats

1. **Insufficient power** — the dominant failure. Underpowered studies produce inflated
   effect sizes even when significant
2. **Pseudo-replication** — technical replicates counted as biological ones; the wrong
   experimental unit. Wells are not animals; cells are not cultures
3. **Batch and order effects** confounded with condition
4. **Lack of blinding** in outcome assessment, especially with subjective measures
5. **Missing or inadequate control** — no vehicle, no sham, no positive control
6. **Selective reporting** — undisclosed outcomes, flexible stopping, HARKing
7. **Model-system validity** — does the cell line, animal model or student sample support
   the claim being made?
8. **Reagent and construct validity** — antibody specificity, off-target effects,
   manipulation checks
9. **Ceiling and floor effects** in the outcome measure

## Impact anchors

Effect size against the clinically or practically meaningful difference, number of
affected patients or units, cost and feasibility of the intervention at scale, whether it
changes a guideline or a protocol, downstream reagents or methods enabled, 3Rs
considerations for animal work.

## Novelty conventions

A new compound, gene or condition tested with a standard assay is incremental unless the
result is surprising. Strong novelty: establishing causality where only association
existed, identifying a boundary condition that reframes a known effect, a well-powered
failure to replicate something influential, or a manipulation nobody could previously
perform. **Pre-registration substantially strengthens novelty claims in this pack** —
recommend it whenever the design is confirmatory.

## What good looks like

- The experimental unit is identified explicitly and matches the analysis unit
- Power is computed against a meaningful effect size, with the source of that size given
- Randomisation and blinding are described at the level of who knew what, and when
- Controls include the ones that could disconfirm, not only the ones that confirm
- Manipulation checks show the manipulation did what it claims
- Batch and order are randomised or explicitly modelled
- The design is pre-registered when confirmatory, and says so
- Negative and unexpected results are reported alongside the headline

## What this pack cannot see

- **Whether the model system supports the claim.** Whether this cell line, animal model
  or participant sample stands in for the target is a domain judgement no design
  checklist makes.
- **Reagent and instrument specifics** - antibody validation, off-target effects,
  calibration drift.
- **Laboratory feasibility.** Whether the group can actually run the protocol, and at
  what throughput, is local knowledge.
- **Ethical approval scope and timeline** for human or animal work.
- If the experiment feeds a fitted model, `computational` is mandatory rather than
  optional - see routing question Q2.
