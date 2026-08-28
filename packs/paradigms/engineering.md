# Engineering Pack

Claims established by **building something that meets a specification** and showing it does.

**Fields:** computer systems, robotics, materials synthesis, chemical and process
engineering, device and circuit design, mechanical and civil engineering, software
engineering, synthetic biology (construct-building).

**`lit-search` domains:** `eng`, `materials`, `chem`, `cs`, `physics`

## Question frame

**Requirement / Design / Mechanism / Performance / Trade-off.**

State it as: *"Can [design] achieve [performance target] on [requirement], and what does
it cost in [the competing objective]?"*

**The trade-off clause is the contribution.** Anyone can improve one metric by sacrificing
another; the result matters only when the position on the trade-off curve is new. State
which curve, and where prior work sits on it.

## Unit of contribution

An artifact that reaches a performance point nobody has reached, a design principle that
generalises beyond the artifact, a characterisation of why existing designs fail, or a
fabrication or implementation route that makes something previously impractical routine.

## Generation axes

| Axis | Ask |
|---|---|
| Trade-off | Which two objectives is everyone assuming are irreconcilable? |
| Bottleneck | What component limits current performance, and why has nobody attacked it? |
| Scale | What works in the lab and fails at production scale, or vice versa? |
| Cost / manufacturability | Same performance with cheap, abundant or non-toxic materials? |
| Robustness | What degrades under real operating conditions — heat, vibration, load, adversarial input? |
| Lifetime | What fails first, and after how long? Usually under-reported |
| Integration | What breaks when two individually-working subsystems are combined? |
| Transfer | What design principle from another engineering domain applies here? |
| Characterisation | What failure mode is universally observed and never explained? |
| Standardisation | What is blocked by the absence of a common interface or benchmark? |

**Lifetime, manufacturability and integration are chronically under-reported** and are
often what actually decides whether a result matters.

## Data and artifacts

Prototypes and test articles, instrument characterisation data, simulation models,
CAD/HDL/source code, process recipes, benchmark suites, reliability and failure logs,
materials characterisation (XRD, SEM, spectroscopy).

## Tier B — obtainable without new collection

- Open materials and property databases: Materials Project, AFLOW, NOMAD, OQMD, ICSD
  (subscription), NIST reference data
- Simulation in place of fabrication: DFT, molecular dynamics, FEA, SPICE, discrete-event
  and network simulators
- Public hardware traces, failure and reliability datasets, benchmark suites
- Open-source reference implementations and hardware designs
- Shared fabrication and characterisation facilities, foundry multi-project wafer runs

**Fabrication access and instrument time are the usual binding constraint, not data.**
Tier accordingly: a design needing a cleanroom process the group cannot run is Tier C
even when everything else is in hand.

## Validity threats

1. **Unfair comparison** — the baseline is older, unoptimised, or measured on different
   hardware or conditions
2. **Cherry-picked operating point** — one favourable configuration, no curve
3. **Simulation-only claims** presented as validated performance
4. **Single sample / no yield data** — one working device says nothing about a process
5. **Missing lifetime and degradation data**
6. **Untested integration** — the component works standalone and breaks in the system
7. **Unreported cost, energy, or toxicity**
8. **Non-reproducible process** — undisclosed steps, unstated tolerances, equipment-specific
9. **Benchmark not representative** of real workloads or conditions

## Impact anchors

Distance to the deployment threshold that matters (efficiency, cost per unit, latency,
energy, lifetime), size of the addressable application, materials scarcity or supply-chain
implications, existing standards or regulations it would satisfy or require changing, and
what becomes possible that was not.

## Novelty conventions

An incremental performance number is weak. Strong novelty: a new point on the trade-off
curve, a design principle that transfers, an explanation for a long-observed failure mode,
or a route that makes an expensive capability cheap. **Reproducibility is part of the
contribution here** — a result nobody else can fabricate or build is close to worthless,
so recommend releasing recipes, designs and code as part of the plan.

## What good looks like

- Comparison is against the current best under matched conditions, and the conditions are
  stated
- A trade-off curve is shown rather than a single favourable operating point
- Yield and variability are reported, not one working unit
- Lifetime and degradation are measured over a horizon that matters
- Integration is demonstrated rather than asserted
- Cost, energy and material scarcity are reported even when unflattering
- The process is described in enough detail to be reproduced elsewhere
- Failure modes are characterised rather than avoided

## What this pack cannot see

- **Whether the physics or chemistry supports the claimed mechanism.** The device may work
  for a reason other than the one given.
- **Local fabrication capability** - what the group's facility can actually run.
- **Supply chain and regulatory reality** for materials and deployment.
- **Field conditions.** Bench performance under controlled conditions says little about
  performance where the thing will live.
