# Medical Imaging AI Module

Radiology, pathology, ophthalmology and other medical images with models fitted to them.

Sits on **`computational`** when the claim is model performance, **`measurement`** when
the claim is diagnostic accuracy, **`clinical`** when the claim is that care should
change.

Lighter than the physiological-signal module by design: the leakage and evaluation
concerns overlap heavily, so read
[`physiological-signal-ai.md`](physiological-signal-ai.md) for the splitting and
preprocessing detail and treat this module as the imaging-specific layer on top.

## Checklists a reviewer will hold up

The checklist depends on how far along the translation path the work sits, and picking
one too early in the ladder is itself a criticism.

| Stage | Checklist | Version checked |
|---|---|---|
| Model development and reporting | **CLAIM** | 2024 update |
| Prediction model, including AI | **TRIPOD+AI** | 2024 |
| Diagnostic accuracy with AI | **STARD-AI** | 2025, Nature Medicine |
| Early clinical evaluation, human factors | **DECIDE-AI** | current |
| Prospective randomised trial of an AI system | **CONSORT-AI** | current |

## Named problems

**Shortcut learning.** Models latch onto anything correlated with the label that is not
the pathology — a chest drain that only appears in pneumothorax images, a scanner
watermark, a laterality marker, the fact that sicker patients are imaged on a particular
machine. Measured across thirteen datasets, shortcut learning inflated apparent
performance by **up to 20%**.

The test is whether performance survives when the shortcut is removed or the population
is changed. Saliency maps are suggestive here, not conclusive, and reviewers increasingly
say so.

**Patient-level versus image-level splitting.** Multiple images per patient — different
slices, different views, follow-up studies — split randomly means the same patient
appears in train and test. Same failure as subject-level leakage in signals, same
consequence.

**Institution-level leakage.** Slides from one institution share staining batch, scanner
and preparation protocol. A model trained and tested across a random split of a
multi-institution dataset learns the institution. Worse, public benchmarks overlap:
TCGA-derived benchmark sets have been measured to share **92.3–100% of cases** with each
other, so "external validation on a second public dataset" may be validation on the same
patients.

Check dataset provenance before believing any external-validation claim.

**Domain shift by scanner and protocol.** Manufacturer, field strength, reconstruction
kernel, slice thickness, stain protocol, magnification. A model that works on one
scanner routinely fails on another, and a proposal that does not plan multi-scanner
validation is proposing something that will not deploy.

**Label provenance.** Radiology labels extracted from reports by NLP carry the report's
uncertainty and the extractor's errors. Labels from a single reader carry that reader's
bias. Expected: how labels were produced, by how many readers, and inter-reader agreement.

**Reader studies.** A claim that a model matches or exceeds clinicians requires a reader
study with a defined reading paradigm, and increasingly a comparison of clinician-with-model
against clinician-alone — because the deployment question is not whether the model beats
the doctor but whether the pair beats the doctor.

## Tier B data

TCGA and derived pathology sets (with the overlap caveat above), CheXpert, MIMIC-CXR,
NIH ChestX-ray14, UK Biobank imaging, ADNI, BraTS and other MICCAI challenge sets, CAMELYON,
ISIC, EyePACS and Messidor, the Cancer Imaging Archive.

Licences vary and several require registration and a data use agreement with a real
review timeline — this affects feasibility tiering, not just legality.

## Impact anchors

Imaging volume per year for the modality, radiologist reporting backlog and turnaround
time, diagnostic delay in current practice, inter-reader variability in current practice
(the bar the model must beat is often lower than assumed), screening programme size,
cost per study, and the false-positive burden a screening model would create downstream.

## Novelty conventions

A new architecture on a public benchmark is **weak novelty unless the change is
principled and ablated** — the same rule as the computational pack. Beating a benchmark
by a point without an ablation is not a contribution.

Genuine novelty: a task no imaging model has been shown to do; a demonstration that a
claimed capability collapses under institution-level splits; a shortcut characterisation
that explains a literature's inflated numbers; prospective evaluation where only
retrospective exists; a model whose failure modes are characterised well enough to be
deployed safely.

## What good looks like

- Splits are at patient level, and at institution level when multi-site
- Dataset provenance and overlap with other public sets are checked and stated
- Multi-scanner or multi-institution validation is planned, not deferred
- Label generation is described, with inter-reader agreement
- An ablation isolates the source of the gain
- Failure cases are analysed and reported, not only aggregate metrics
- Calibration is reported, not only discrimination
- The comparison is clinician-with-model versus clinician-alone where a clinical claim is
  made
- The checklist matched to the actual stage is followed, rather than the most impressive one

## What this module cannot see

- **Whether the imaging finding is biologically real.** A model can predict an outcome
  from an image via a confounder no checklist detects; a radiologist or pathologist has
  to say whether the signal is plausible.
- **Image acquisition physics.** Reconstruction, artifact formation and their interaction
  with model features need a physics or engineering reviewer.
- **Annotation quality** beyond asking for agreement statistics.
- **Regulatory pathway and post-market surveillance** requirements, which are
  jurisdiction-specific.
- **Whether a radiology or pathology workflow can absorb the tool** — a human-factors
  question `DECIDE-AI` names and this module cannot answer.
