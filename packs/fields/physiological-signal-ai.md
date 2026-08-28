# Physiological Signal AI Module

ECG, EEG, PPG and other waveform data with models fitted to it.

Sits on **`computational`** when the claim is model performance, **`measurement`** when
the claim is that the signal measures a physiological quantity, **`clinical`** when the
claim is that a decision should change.

Nearly all work here needs at least two of those. Answer Q2 in the routing step honestly.

## The failure that dominates this field

**Subject-level splitting.**

Segments from the same person appearing in both training and test sets means the model
can score well by recognising *the person* rather than the pathology. Every reported
number from such a split is meaningless, and the numbers are usually excellent, which is
why the error survives peer review.

Three forms, all of which must be checked separately:

1. **Segment-level random split** — windows from one recording scattered across train and
   test. The default behaviour of `train_test_split` on a segmented dataset.
2. **Window overlap across the split boundary** — overlapping windows are standard for
   augmentation; if the split is applied after windowing, adjacent windows sharing
   samples land on both sides.
3. **Normalisation fitted before splitting** — computing mean and variance, or any filter
   coefficient, on the full dataset. Described in the literature as subtle but
   devastating, because it leaks the test distribution without leaking any test sample.

The question to ask any proposal here: **is the split by subject, and was every
preprocessing step fitted inside the training fold?** If the answer is not explicit,
that is the first objection.

---

## ECG

**AAMI EC57** is the standard, and reviewers know it.

- 15 heartbeat classes collapse into **5 superclasses**: N, SVEB, VEB, F, Q
- Required reporting is **per-class Sensitivity, PPV and FPR** — not overall accuracy.
  Overall accuracy on a dataset that is 90% normal beats is 90% for a model that predicts
  "normal" every time, and papers reporting only accuracy get rejected for this.

**Inter-patient versus intra-patient — the field's most cited pitfall.**

The de Chazal inter-patient paradigm splits by patient. MIT-BIH's DS1/DS2 division is
exactly that split and exists for this reason. Intra-patient evaluation routinely
approaches 100% accuracy and means nothing; the literature states plainly that it
**should be highly discouraged**. A paper reporting near-perfect arrhythmia
classification without specifying the paradigm is almost certainly intra-patient.

**PTB-XL** — 21,837 records from 18,885 patients, with **official recommended folds**.
Using a custom random split on a dataset that ships with a recommended split invites the
question of why, and the answer is rarely good.

Other expectations: lead configuration stated (12-lead, single-lead, reduced); sampling
rate and filtering described; class imbalance handled and the handling described; and for
any clinical claim, external validation on a different recording system, because ECG
models learn device characteristics.

---

## EEG

**Artifact removal is the central question, and most papers skip it.**

Roughly **72% of studies do not perform explicit removal of ocular, muscular and cardiac
artifacts**. High-capacity models will use non-brain signal to reduce loss, because it is
there and it is predictive. Eye blinks correlate with drowsiness; jaw tension correlates
with stress; ECG contamination correlates with everything cardiac.

So the first question to any EEG-AI proposal is: **how do you know the model is not
classifying eye movement?** Acceptable answers name a method — ICA with component
rejection criteria, ASR, regression-based EOG removal — and say how the removal was
validated. "Bandpass filtered 1–40 Hz" is not artifact removal.

**Double dipping** — selecting channels, time windows or features using the full dataset,
then cross-validating on the same data. The selection has already seen the test fold.

**Scoring conventions differ and give different numbers.** For seizure detection,
event-based scoring (did you find the seizure) and epoch-based scoring (was each window
labelled correctly) produce substantially different performance for the same model. Both
are defensible; not saying which was used is not.

**This field has no equivalent of EC57.** There is no settled reporting standard for
EEG-AI; proposals for Model Cards exist but nothing is established. A module that
pretended otherwise would be inventing authority. State the absence, and expect the
proposal to define its own reporting protocol explicitly.

Other expectations: montage and reference scheme stated; subject-level splits (see
above); session effects treated as a confounder — same subject, different day, different
electrode impedance; and for clinical claims, inter-rater agreement on the labels, since
EEG labels are expert opinion and expert opinion disagrees.

---

## PPG and wearables

**Skin tone bias, and its direction.**

Pulse oximetry **systematically overestimates SpO₂ in people with darker skin**, which
means occult hypoxaemia goes undetected and clinical action is delayed. This is not a
hypothetical fairness concern; it is a documented, directional, clinically consequential
error.

Any PPG proposal that does not report performance **stratified by skin tone** should be
questioned on exactly that basis. Stating an aggregate accuracy across a mostly
light-skinned cohort is the failure mode.

**Cuffless blood pressure.** Accuracy in some subgroups has been reported as low as
**40%**, and models frequently turn out to be predicting the population mean rather than
the individual's pressure — which looks acceptable on aggregate error metrics and is
useless per person. The diagnostic: does the model's output vary with the individual's
actual pressure, or does it regress to the cohort mean? Test it explicitly.

**IEEE Std 1708** (2014, amended 1708a-2019) governs wearable cuffless blood pressure
device validation.

**Agreement, not correlation.** Comparing PPG-derived heart rate against ECG requires
**Bland–Altman** limits of agreement. A correlation coefficient can be near 1.0 with a
constant offset that makes the device clinically wrong. Reviewers in this field ask for
the Bland–Altman plot by name.

Other expectations: motion artifact handling described and tested under motion, not only
at rest; wear position and device stated; and reference standard specified, because
"compared against a consumer device" is not validation.

---

## Tier B data

PhysioNet is the centre of gravity: MIT-BIH Arrhythmia, PTB-XL, CinC Challenge datasets,
MIMIC waveform matched subset, CHB-MIT scalp EEG, TUH EEG Corpus, Sleep-EDF, BIDMC and
CapnoBase for PPG, UCI HAR for wearable activity.

Check the licence and, for anything clinical, whether the dataset's population resembles
the intended deployment population. Most public physiological datasets are small,
single-centre and demographically narrow.

## Impact anchors

Prevalence of the condition being detected, current diagnostic delay, cost or invasiveness
of the current reference test, number of wearable devices in use, screening eligibility
population, false-positive burden on downstream care.

## Novelty conventions

A new architecture on a standard benchmark is **weak novelty unless the change is
principled and ablated**. Reporting a higher number on MIT-BIH without an ablation
isolating what caused it is not a contribution.

Genuine novelty: a physiological quantity nobody could extract from this signal before; a
demonstration that a claimed capability does not hold under honest splits; cross-modal
inference with a mechanistic rationale; a bias characterisation that changes how a device
should be used; validation in a population where the signal properties genuinely differ.

**Testing whether a widely claimed capability survives correct evaluation is a real
contribution**, and it is the kind this field most needs.

## What good looks like

- The split is by subject, and the paper says so in the methods, not the appendix
- Every preprocessing step is fitted inside the training fold and the paper says so
- Per-class metrics for imbalanced problems, with the class distribution reported
- The official recommended split is used when the dataset ships with one
- Artifact handling is named and validated, for EEG especially
- Results are stratified by skin tone for PPG, by lead configuration for ECG, by montage
  for EEG
- Bland–Altman agreement where a device is compared against a reference
- An ablation isolates which component produced the gain
- External validation on a different device or recording site
- The absence of a field reporting standard is acknowledged rather than papered over

## What this module cannot see

- **Whether the physiological premise is sound.** That a signal *could* carry the
  information being extracted is a domain question. A model that predicts a condition
  from ECG with no plausible cardiac pathway may be exploiting a confounder — this module
  raises the possibility but cannot settle it.
- **Signal processing detail at expert level.** Filter design, phase distortion,
  resampling artifacts, and their interaction with downstream features need a signal
  processing reviewer.
- **Device-specific characteristics.** Sensor hardware, sampling jitter and proprietary
  onboard preprocessing differ by manufacturer and are frequently undocumented.
- **Regulatory pathway.** Whether a model is a regulated medical device, and what
  evidence a regulator would require, is jurisdiction-specific.
- **Whether labels are correct.** Most physiological labels are expert annotation with
  real disagreement rates; this module can ask for inter-rater agreement but cannot
  assess the labels themselves.
