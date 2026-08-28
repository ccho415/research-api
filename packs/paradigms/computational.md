# Computational Pack

Claims established by **beating or characterising a measurable baseline** on a defined task.

**Fields:** machine learning, AI, NLP, computer vision, speech, information retrieval,
systems and databases (performance work), bioinformatics, computational social science.

**`lit-search` domains:** `ml`, `cs`, `stats`

## Question frame

**Task / Method / Baseline / Metric / Budget.**

State it as: *"On [task], does [method] improve [metric] over [baseline], under [compute
and data budget], and why?"*

The **budget** clause is what separates a contribution from a purchase. An improvement
obtained with 10× the compute of the baseline is not an improvement until it is matched.

Two respectable variants that are not "beat the baseline":

- **Analysis** — why does the existing method work or fail? No new method needed.
- **Negative / limitation** — a widely-assumed capability does not hold under a fair test.

## Unit of contribution

A method with a controlled comparison, an analysis that changes how people understand an
existing method, a benchmark or dataset that exposes something no existing one does, or a
reproduction that overturns a published result.

## Generation axes

| Axis | Ask |
|---|---|
| Task | What real task does no benchmark represent? Where is the benchmark saturated or gamed? |
| Method | What component is assumed necessary but never ablated? |
| Baseline | Which claimed gain disappears against a properly-tuned simple baseline? |
| Metric | What does the standard metric fail to capture — robustness, calibration, fairness, latency, cost? |
| Regime | What breaks at a different scale, in low resource, out of distribution, under shift? |
| Efficiency | Same result at a fraction of the compute, memory, data or labels? |
| Failure analysis | What error mode does everyone report but nobody characterises? |
| Transfer | What works in a neighbouring subfield and has never been tried here? |
| Reproduction | Which influential result has never been independently reproduced? |
| Theory-practice gap | Where does the theory predict something practice contradicts? |

**Efficiency, failure analysis and reproduction are systematically under-supplied**
relative to their value, because they read as less exciting than a new method.

## Data and artifacts

Benchmark datasets, model checkpoints, training corpora, code repositories, evaluation
harnesses, logs and traces, leaderboards, compute allocation.

## Tier B — obtainable without new collection

- Public benchmarks and datasets (HuggingFace, Kaggle, OpenML, UCI, Papers-with-Code)
- Pretrained checkpoints and open model weights
- Released evaluation harnesses and official baseline implementations
- Public leaderboards and their submission histories
- Logs, crash corpora, and public API traces
- Synthetic data generation, where the construct tolerates it

The real Tier B constraint in this field is usually **compute, not data**. State GPU-hours
or equivalent explicitly — an idea needing a 70B pretraining run is Tier C or D for most
researchers regardless of data availability.

## Validity threats

1. **Data leakage** — test contamination in pretraining corpora, temporal leakage,
   duplicate examples between splits. Assume it until checked
2. **Unfair baselines** — undertuned, older hyperparameters, less compute, no comparable
   search budget. The most common reason a reported gain is not real
3. **Single seed / no variance** — improvements inside seed noise
4. **Benchmark overfitting** — the community has collectively tuned on the test set
5. **Cherry-picked tasks** — gains on the subset where the method happens to work
6. **Metric gaming** — the metric improves while the underlying capability does not
7. **Non-reproducibility** — undisclosed tricks, missing code, unstated preprocessing
8. **Scale confound** — the effect is really a parameter-count or data-volume effect
9. **Construct validity** — the benchmark does not measure the capability it is named for

## Competitive positioning

The threat list above asks whether the result is real. Reviewers in this field spend at
least as much effort on a different question: **where does this sit relative to what
already exists, and did you compare against the right thing?** A methodologically clean
paper is routinely rejected for answering that badly, and a review that never raises it
reads as though it does not know the area.

This section exists because of a measured failure. Scored against expert reviews of AI
research plans, working only from the threat list produced sound but misplaced critique:
the experts were writing about comparator choice, novelty scope and evaluation breadth,
and almost none of that is reachable from validity threats alone.

### The comparator ladder

Four separate objections, not one. A paper can satisfy any of them and fail the rest.

| Rung | The question | What a missing answer looks like |
|---|---|---|
| **The trivial baseline** | Does it beat the simplest thing that could work? | Fingerprints with a random forest, nearest-neighbour retrieval, a fixed-time controller. Beating a deliberately weak learned model instead is a straw man |
| **The nearest competitor** | Does it beat the published method it most resembles? | A method built on a white-box surrogate compared only against methods that use none |
| **The ablated self** | Does the contributed component do the work? | Three components introduced together, one number reported |
| **Matched budget** | Does it win at equal compute, queries and tuning effort? | "Consistent hyperparameters across all models" is the opposite of fairness — each model needs its own search, and the search budget is the thing to equalise |

**Currency runs across all four.** Comparators are dated relative to the paper, not to
whenever the subfield's habits formed: victim models from 2015 in a 2024 attack paper,
task baselines from 2018 in a 2024 prediction paper. If the comparison set has not moved
in five years, that is the first thing a reviewer notices.

### Novelty scope

Reviewers deflate novelty claims hard, and the deflation is usually correct.

- Existing optimiser plus existing attribution method plus new application is an
  **application paper**. That is legitimate and it must be described that way.
- Where every component is pre-existing, the contribution is the *combination*, and the
  combination has to be shown to beat its parts. That is an experiment, not an argument.
- **"X has been largely untapped" is checkable**, and a reviewer who can name three papers
  doing X will name them. Check before writing it — especially when the paper's own
  baselines are examples of X.
- Claiming a formalism as the contribution obliges you to show the formalism earning its
  place: an ablation that removes it, not one that removes something adjacent to it.

### Evaluation breadth

- **One dataset, one target, one task** supports a claim about that dataset, target or
  task. A general claim needs a second, chosen to differ in the way that matters — a
  data-poor target, a different modality, a different deployment regime.
- **Benchmark hygiene is inherited.** Splits not controlled for homology or similarity,
  decoys separable by construction, test items present in pretraining corpora: adopting
  a benchmark adopts its defects, and "it is the standard benchmark" is not an answer.
- **A selection criterion generalises no further than the thing it was measured on.** If
  tokenisation, architecture and objective were chosen by score on benchmark B, the design
  is optimised for B. Say what else was checked.
- **The harder setting is where methods separate**, and reviewers ask for it: targeted
  rather than untargeted, unseen-entity rather than random splits, out-of-distribution
  rather than in-distribution, low-resource rather than well-resourced.

### Practicality

- **Hyperparameter burden is a real objection.** A method with six sensitive parameters and
  no tuning protocol cannot be used by anyone else, whatever it scores.
- **Required inputs must exist in the setting the paper motivates.** A white-box surrogate,
  lane-level sensor coverage, or a proprietary data feed each change who can run the
  method, and each needs pricing.
- **Cost belongs in the comparison**, not in the acknowledgements: compute, queries,
  licences, latency.

### Specification

- The mechanism the contribution rests on has to be specified precisely enough to
  reimplement. "We model inter-agent dependencies as a sequence problem" names a category,
  not a method.
- **Anything claimed as a contribution needs the specification of one** — a dataset, a
  generation pipeline, an evaluation suite. Naming it in the abstract and describing it in
  one sentence invites the reviewer to discount it entirely.
- Theoretical claims need their assumptions stated where they are used; a guarantee with
  unstated preconditions is not a guarantee. Load `formal.md` when the paper argues that
  its method provably works.

## Impact anchors

Adoption (downloads, citations of the artifact, downstream use), compute or cost saved at
deployment scale, users or systems affected, capability enabled that was previously
impossible, benchmark headroom remaining, safety or failure incidents addressed.

Beware: leaderboard position is not impact. Ask what someone would **do differently**.

## Novelty conventions

A new architecture variant is weak novelty unless the change is principled and ablated.
Strong novelty: a new problem formulation, a demonstration that an accepted result is
wrong, an efficiency result that changes what is affordable, or an analysis that explains
a phenomenon the field has only described. **Applying an existing method to a new dataset
is an application paper — legitimate, but do not claim it as method novelty.**

## What good looks like

- Splits are principled, and the paper says how leakage was ruled out rather than
  assuming it away
- Baselines are tuned with the same budget as the proposed method, and the budget is
  stated
- Multiple seeds with variance reported, and the claim survives the variance
- An ablation isolates which component produced the gain
- Evaluation includes a task the method was not designed for
- Compute is reported honestly, including failed runs
- Code and configs are released in a state someone else can run
- The limitation section names a condition under which the method fails
- The nearest published competitor is named and compared against, not just the trivial
  baseline and the authors' own earlier work
- Comparators are current, and where an old one is kept the reason is given
- The novelty claim is scoped to what is actually new, with the rest described as
  application or combination
- Required inputs are priced: what the method needs in order to run, and who can supply it

## What this pack cannot see

- **Whether the benchmark measures anything worth measuring.** Construct validity is a
  domain question; load `measurement` when the metric itself is the claim.
- **Whether the application domain's constraints are satisfied** - clinical safety,
  regulatory exposure, deployment cost. Load the relevant field module.
- **Data provenance and licensing** for datasets whose origins are undocumented.
- **Whether the labels are correct.** Benchmarks inherit their annotators' errors, and
  this pack takes labels as given.
- For medical waveform or image data, load `physiological-signal-ai` or
  `medical-imaging-ai`. The leakage patterns there are specific, and this pack will only
  tell you to check for leakage.
- **Which comparators are current in a given subfield.** The competitive positioning
  section says a reviewer will ask whether the comparison set has moved; it cannot tell
  you what has replaced what. That needs someone who reads the venue, and it goes stale
  faster than anything else in this pack.
