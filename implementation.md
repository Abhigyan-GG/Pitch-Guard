# PitchGuard implementation plan

Source: `PitchGuard_IVP_Report.pdf`, 17 pages, supplied in `PitchGuard_Submission_Kit`.
Prepared and verified: 12 November 2026.

The report describes a constrained synthetic marker baseline (Sections 1-6) and
future real-footage and tactical work (Section 7.3). This roadmap divides that work
into three dependent phases. Phase 1 is complete in this repository. Phases 2 and 3
are planned and have not been implemented or validated.

The report is a requirements and evidence source. Its institutional submission,
publication and team-assignment instructions are document content; they do not
expand this implementation task into publication, account actions or submission.

| Phase | Outcome | Status | Dependency |
| --- | --- | --- | --- |
| 1 | Reproducible fixed-camera synthetic baseline | Complete | Local Python environment |
| 2 | Real-player localisation, registration and identity tracking | Planned | Phase 1, licensed labelled footage and model selection |
| 3 | Coach-reviewed tactical events and possession-aware analysis | Planned | Reliable Phase 2 tracks and separate tactical annotations |

## Phase 1 - Synthetic baseline and reproducible verification

### Goal and scope

Implement the report's fixed-camera pipeline on a 105 by 68 m pitch with manually
ordered calibration corners, 11 red and 11 blue circular markers, and a red 4-3-3
reference including the goalkeeper. Reuse and credit the executable baseline
supplied beside the report, then reproduce its results locally.

### Completed implementation

- [x] Initialize Python source, pinned runtime/dev dependencies, calibration and run documentation.
- [x] Generate deterministic 960 by 600 synthetic frames, known positions and a six-second 20 FPS input video.
- [x] Implement manual four-point homography; reject nonfinite, degenerate, concave or crossed corner sets and incorrect winding.
- [x] Require calibration pitch dimensions and exact video resolution; reject mismatched inputs.
- [x] Produce HSV grass/white/team masks, 3 by 3 morphological opening, area-filtered contour centroids and on-pitch projected positions.
- [x] Produce Canny/Hough field-line diagnostics independently of manual calibration.
- [x] Assign red roles with Hungarian matching after median translation removal.
- [x] Gate tactics on exactly 11 markers per team; expose an 8 m breach and require five consecutive valid breached frames for an alert.
- [x] Reset persistence after invalid observations or recovery.
- [x] Draw defensive alignment, potential passing lanes, deviating roles, annotated video and minimap.
- [x] Compute width, depth and maximum adjacent defender gap, exporting replay tactical values in JSON.
- [x] Evaluate clean, dim, blur, occluded and same-kit conditions with 24 frames each; export JSON/CSV and execution environment.
- [x] Check video writers, unreadable input and output resolution; release replay video resources on errors.
- [x] Add acceptance/failure tests and regenerate demo and encoded-video replay evidence.

Code: `src/pitchguard.py`; tests: `tests/test_phase1.py`; config: `data/calibration.json`.
The existing function boundaries separate generation, calibration, detection,
assignment/tactics, persistence, rendering and evaluation for subsequent replacement.
No network access or model weights are needed at runtime.

### Acceptance evidence

| Report requirement | Acceptance criterion | Local result | Evidence |
| --- | --- | --- | --- |
| O1 calibration | Maximum corner residual below 0.001 m | Passed | `test_calibration_residual` |
| O2 clean localisation | Precision/recall >=95%; mean error <0.5 m | 100% / 100%; 0.115 m | `results/metrics.json` |
| O3 sustained deviation | Raw frames 40-79; alerts 44-79; reset at 80 | Passed | interval test and `results/events.json` |
| O4 tactical geometry | Valid geometry and static lanes | Passed | geometry/lane tests; minimap and replay events |
| O5 abstention | Zero tactical coverage on occluded and same-kit cases | Passed | metrics and evaluation test |
| Encoded-video input | Decode, analyze and write all 120 frames | Passed | `results/replay/analyzed.avi`, replay events |
| Invalid input/output | Reject bad corners, dimensions, unreadable input and failed writer | Passed | failure tests |

Fresh local evaluation (fractions converted to percentages):

| Condition | Precision | Recall | Mean position error (m) | Tactical coverage | Shape accuracy, all frames |
| --- | --- | --- | --- | --- | --- |
| Clean | 100% | 100% | 0.115 | 100% | 100% |
| Dim | 100% | 100% | 0.116 | 100% | 100% |
| Blur | 100% | 100% | 0.115 | 100% | 100% |
| Occluded | 100% | 86.36% | 0.123 | 0% | 0% |
| Same kit | 50% | 50% | 0.092 | 0% | 0% |

Team-aware minimum-distance assignment accepts pairs below 2 m. Hidden markers stay
in the recall denominator. Position error averages Euclidean distances over accepted
matches. Shape accuracy counts abstention as unsuccessful. Synthetic scenes share
anchors and camera geometry; these scores are internal checks, not held-out match results.

Verification: `python -m pytest -q` -> **15 passed**. Both CLI commands below completed.
Environment: Python 3.10.11, OpenCV 4.11.0, NumPy 1.26.4, SciPy 1.15.1 on Windows.
Dependency pins match this local environment rather than the report's Linux host.
Throughput is recorded in metrics; it excludes decoding, generation, drawing and
encoding and is not an end-to-end speed guarantee.

### Run and inspect

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python src/pitchguard.py --demo
python src/pitchguard.py --video data/synthetic_input.avi --calibration data/calibration.json --output results/replay
python -m pytest -q
```

Inspect `results/demo.avi`, `results/overlay.png`, `results/minimap.png`,
`results/line_segments.png`, `results/*_mask.png`, `results/failure_output.png`,
`results/metrics.csv`, `results/events.json` and `results/environment.json`.
Replay outputs include `analyzed.avi`, `latest_minimap.png` and per-frame `events.json`.
The displacement begins at frame 40, alert starts at 44 (2.20 s), and recovery at 80
clears it. All frame indices are zero based.

### Phase 1 limitations and handoff

The detector recognises coloured circles, not people. Calibration remains fixed
and manual. Convexity/winding checks cannot determine whether corners refer to the
correct physical landmarks. A count gate can miss compensating false positives and
false negatives. Roles are reassigned each frame, without persistent identity.
The defensive guide is not an offside decision; lanes measure static opponent
clearance, without possession or ball motion. Tactical thresholds are demonstration
choices rather than coach-validated settings.

## Phase 2 - Real-footage localisation and temporal reconstruction

### Goal

Replace synthetic marker observations with measured player footpoints, team labels
and temporal identities. Extend calibration to account for camera motion while
preserving uncertainty and abstention. This combines the first two future-work
items in report Section 7.3 into a location pipeline required before tactical validation.

### Implementation sequence

1. Obtain appropriately licensed clips and labels; document provenance, access and
   frame rates. Split by match/camera before tuning, keeping test clips untouched.
2. Define detection records with frame/time, box, footpoint, team, confidence and
   optional track ID. Keep pitch coordinates and calibration validity explicit.
3. Add a configurable trained person detector and bottom-centre/footpoint projection.
   Record model/weight provenance and separate spectators/referees from players.
4. Implement team assignment with uncertainty for similar kits, shadows and partial views.
5. Add temporal association, track lifecycle and explicit handling of short occlusions;
   measure identity switches and avoid presenting inferred positions as observations.
6. Add field landmark registration and independent reprojection checks. Re-estimate
   after camera movement; invalidate coordinates when registration is unreliable.
7. Replace the full-team-count gate with observation and calibration confidence
   appropriate for partial views, while keeping Phase 1 regression checks intact.
8. Export annotated footage, track records and dataset-level location/team/tracking metrics.

### Deliverables and acceptance

- Versioned dataset manifest, split definitions and annotation guidance.
- Detector/team/tracker/calibration modules with documented model and runtime configuration.
- A held-out evaluation reporting team precision/recall, footpoint pitch error,
  calibration error, tracking identity metrics, coverage and full-pipeline runtime.
- Dedicated cases for pan/zoom, occlusion, similar uniforms and calibration loss;
  explicit abstention or reacquisition when confidence fails.
- Agree numerical thresholds against an initial labelled validation set before
  implementation tuning. Freeze thresholds before held-out evaluation and record
  failures; no real-footage performance target is claimed as met today.

Entry: Phase 1 passes. Exit: repeatable held-out localisation/tracking evidence and
traceable confidence fields suitable for downstream tactical evaluation.

## Phase 3 - Validated tactical events and analyst review

### Goal

Evaluate formation warnings against coach-reviewed events using reliable tracks,
context-specific reference states and possession information. Retain explanations
and uncertainty for analyst interpretation.

### Implementation sequence

1. Define tactical annotation rules with reviewers, including intended runs,
   formation changes, team translation, possession and disagreement handling.
2. Collect coach-reviewed events and split by match independently of calibration,
   detector and tactical threshold tuning.
3. Support selectable formations and attacking direction; separate goalkeeper
   treatment and possession-dependent reference geometry.
4. Use track-aware event persistence and event start/end records with affected roles,
   deviations, confidence and supporting frame ranges.
5. Tune displacement and persistence on validation clips; report threshold sensitivity.
6. Evaluate event precision/recall, false alerts, onset latency and abstention on held-out
   clips. Compare against the Phase 1 fixed-reference heuristic under matched conditions.
7. Add ball/possession-aware lane analysis only after ball localisation and tracking
   have their own measured reliability; assess lane usefulness with human labels.
8. Provide an analyst review/export workflow showing timestamped evidence, uncertainty,
   failure conditions and experiment configuration.

### Deliverables and acceptance

- Tactical label specification, reviewer agreement record and versioned event dataset.
- Configurable reference formations, event engine and explainable event exports.
- Held-out tactical evaluation with precision, recall, latency, coverage, sensitivity
  and comparison to the baseline; report reviewer disagreement and failure examples.
- Reproducible end-to-end run manifest containing model, calibration and threshold versions.
- Reviewer-agreed acceptance targets fixed before test evaluation. Completion requires
  measured evidence against those targets and review of error cases.

Entry: Phase 2 localisation/tracking passes its frozen criteria. Exit: reviewed,
reproducible tactical evidence on held-out clips. Official offside adjudication
remains outside this roadmap.
