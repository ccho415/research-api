# Formal Pack

Claims established by **proof from stated assumptions**. Nothing is measured; nothing is
sampled. Applying empirical standards here is a category error.

**Fields:** mathematics, theoretical computer science, complexity theory, theoretical
physics, formal economics and game theory, logic, cryptography (provable security),
statistics (theory).

**`lit-search` domains:** `math`, `cs`, `physics`, `stats`, `econ`

## Question frame

**Assumptions / Object / Claim / Tightness.**

State it as: *"Under [assumptions], does [object] satisfy [property]? Is the bound
tight, and what happens when each assumption is dropped?"*

The **tightness** and **assumption-dropping** clauses are the contribution. A result that
holds under assumptions nobody can satisfy is a curiosity; a matching lower bound is
usually worth more than the upper bound it accompanies.

## Unit of contribution

A theorem, a matching bound, a counterexample, a separation, a new proof technique, a
simplification of a known proof, or a reduction connecting two problems.

## Generation axes

| Axis | Ask |
|---|---|
| Assumption weakening | Which hypothesis in a known theorem is stronger than necessary? |
| Tightness | Is there a gap between the best upper and lower bound? Close it either way |
| Generalisation | Does the result extend to a broader class, a different space, higher dimension? |
| Special case | Does a hard open problem become tractable under a natural restriction? |
| Counterexample | Which widely-believed conjecture might be false? |
| Technique transfer | What proof method from an adjacent area has never been applied here? |
| Constructivity | Does a non-constructive existence proof have an explicit or efficient version? |
| Reduction | Which two problems are secretly the same? |
| Robustness | Does the result survive noise, approximation, or an adversarial variant? |
| Computational content | What is the algorithmic consequence of this structural result? |

**Assumption weakening and tightness are where most publishable work lives** and are
easiest for an outsider to underrate.

## Data and artifacts

There is no dataset. The artifacts are: prior theorems and their exact statements,
counterexample libraries, proof assistants and formalisation libraries (Lean/mathlib,
Coq, Isabelle), symbolic computation systems, and computational search for small cases.

**`data-feasibility` is largely not applicable to this pack.** The binding constraints are
technique availability and the researcher's expertise. Tier the directions by *whether the
required proof technique is within reach* instead — and say that is what you are tiering.

## Tier B — obtainable without new collection

- Formalisation libraries and proof assistants for verifying small cases
- Computational search over small instances to test a conjecture before attempting a proof
- Published counterexample collections and problem lists (open-problem compilations,
  conjecture databases)

## Validity threats

1. **A gap in the proof** — the only real failure mode, and it is binary
2. **Assumptions doing hidden work** — the result is trivial or vacuous once you see
   what was assumed
3. **Already known** — often under different terminology in another field. This is the
   dominant *novelty* risk here and keyword search is bad at catching it
4. **Vacuous truth** — the hypothesis class is empty or trivial
5. **Non-tight bound presented as tight**
6. **Unstated dependence** on choice, on a large-cardinal axiom, on a conjecture
7. **Off-by-one and edge cases** — n=0, empty set, degenerate configurations
8. **Misstated quantifiers** — the classic source of a proof that proves something else

## Impact anchors

Which open problem it settles or approaches, what it implies downstream, how many results
depend on the assumption being weakened, algorithmic consequences, and whether it unifies
previously separate arguments. Citation counts are especially misleading here — deep
results can be cited rarely for decades.

## Novelty conventions

Novelty is binary and unforgiving: **the theorem is new or it is not**. But rediscovery
under other terminology is rampant across mathematics, TCS, physics and economics, so
`novelty-check` must search **by mathematical structure, not by topic words** — search the
object, the bound form, the technique name, and check MathSciNet/zbMATH-style sources and
the relevant open-problem lists. A new *proof* of a known theorem is a genuine
contribution if it is simpler, constructive, or generalises.

## What good looks like

- Assumptions are stated where they are used, not only in a preamble
- Tightness is established, or its absence acknowledged, rather than implied
- Edge and degenerate cases are handled explicitly
- The proof technique is explained well enough to be reused
- The result is connected to what depends on it downstream
- Counterexamples are given for the assumptions that cannot be dropped
- Prior work is located by structure, including under different terminology

## What this pack cannot see

- **Whether the formalisation captures the informal problem.** A theorem can be correct
  and about the wrong thing, and no proof check detects that.
- **Whether the result is already known** under other terminology in an adjacent field.
  This is the dominant risk here and keyword search is poor at it.
- **Practical relevance of a bound.** An asymptotic result with astronomical constants is
  true and useless, and only a practitioner will say so.
- **Verification at expert level.** A gap in a proof is found by a specialist reader, not
  by a checklist.
