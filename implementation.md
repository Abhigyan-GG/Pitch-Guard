# PitchGuard implementation plan

Source: `PitchGuard_IVP_Report.pdf`, 17 pages, supplied in `PitchGuard_Submission_Kit`.
Phase 1 verified: 12 November 2026. Coaching-app implementation updated: 18 November 2026.

The report describes a constrained synthetic marker baseline (Sections 1-6) and
future real-footage and tactical work (Section 7.3). This roadmap divides that work
into three dependent phases. Phase 1 is complete. Phase 2 and 3 software is now implemented with a local coaching frontend. Their original held-out accuracy and coach-validation exit gates remain open; unlabelled footage and engineering tests cannot establish those outcomes.

The report is a requirements and evidence source. Its institutional submission,
publication and team-assignment instructions are document content; they do not
expand this implementation task into publication, account actions or submission.

| Phase | Outcome | Status | Dependency |
| --- | --- | --- | --- |
| 1 | Reproducible fixed-camera synthetic baseline | Complete | Local Python environment |
| 2 | Real-player localisation, registration and identity tracking | Implemented; independent validation pending | Human location labels and frozen acceptance targets |
| 3 | Tactical events, formation advice and analyst review | Implemented; coach validation pending | Reviewed event/negative intervals and agreed accuracy targets |

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

### Implemented software

| Requirement | Implementation | Evidence / status |
| --- | --- | --- |
| Real-player detector | Football-specific YOLOv8s, with COCO YOLOv8n fallback and custom-model path | Learned inference executed on supplied clips; model provenance/checksums retained |
| Detection records | Box, footpoint, model confidence, team, team confidence, pitch location, track ID, observed flag | Timeline JSON and tracks CSV |
| Team labels and ambiguity | User-picked kit colours, torso LAB comparison, explicit unknowns | Kit-assignment tests; similar kit input rejected |
| Overhead footage | Separate kit-region detector; centre proxy explicitly distinguished from human footpoint | User-supplied aerial clip engineering run |
| Temporal identity | Team-aware gated Hungarian association with velocity prediction and short reacquisition window | Track persistence, team separation and expiry tests |
| Camera motion | Reference optical flow, forward/backward checks, robust homography and held-out feature residual | Camera-transform, cut rejection and fixed-view tests |
| Re-registration | User-saved calibration keyframes after cuts/zooms; full-pitch or overhead circle landmarks | Frontend calibration flow and validated config |
| Incomplete observations | Whole-team measurements require sufficient observed players; local-only events have explicit scope | Partial-view tests; no invented occluded tracks |
| Video analysis | Full interval, user-set sample rate, bounded queue, progress, cancellation and durable results | End-to-end API and browser checks |
| Evaluation and training tools | Independent human-label evaluator, split leakage checks, frame extraction and guarded supervised training | Evaluation unit tests; CLI and annotation specification |

`src/vision.py`, `src/pipeline.py`, `src/schemas.py`, `src/evaluation.py` and
`scripts/` contain these components. `models/football-model.json` pins the downloaded
football model revision and SHA-256. Per-run manifests record model classes, source
checksums, actual thresholds and end-to-end runtime. No training was claimed on the
supplied unlabelled videos.

### Real-video evidence boundary

The user supplied a 36.71-second 1920x1080 overhead screen recording and an
8.8-second 768x432 Getty clip. Both were decoded and processed. The cropped overhead
view can support only local support-distance observations. Distant players and team
classification remain difficult in the Getty clip; the app abstains from unsupported
whole-team conclusions. Engineering outputs are under `results/real_*` and local
application jobs. These are smoke tests, not labelled accuracy benchmarks.

The supplied clips are recorded in `datasets/manifest.json`. They do not yet have
independent position/team/identity labels or verified match split provenance.
`docs/VALIDATION.md` explains the label schema, training and held-out evaluation.

### Original phase exit gates still open

- Human-verified location/team/identity labels on independent match splits.
- Independent pitch landmarks, not the calibration fit points, for calibration error.
- Frozen reviewer-approved thresholds and held-out location/team/tracking/coverage results.
- Separate failure-case labels for pan/zoom, cuts, occlusion, similar kits and calibration loss.

Do not describe Phase 2 as accuracy-validated until those gates have measured evidence.

## Phase 3 - Tactical events, formation advice and coaching review

### Implemented software

| Requirement | Implementation | Evidence / status |
| --- | --- | --- |
| Opponent prediction input | Eight selectable opponent formations | API/input tests and browser matchup flow |
| Formation pros/cons | Shape descriptions, strengths, vulnerabilities and exploitation ideas | Formation catalogue and coaching references |
| Best-fit recommendation | Objective, squad strengths, familiarity and transparent matchup scoring; ranked alternatives | Context-dependent scoring tests; frontend scoring breakdown |
| Formation reference | Eight own-team templates, attacking direction and goalkeeper exclusion from outfield summaries | Anchor/mirroring and geometry tests |
| Possession context | Analyst-supplied in/out/unknown state and optional time segments; width/depth references adapt | Config checks and context geometry test |
| Flow/shape signals | Sustained role drift, unit gap, defensive channel, excessive depth, visible support isolation and abrupt shape disruption | Geometry/persistence tests and synthetic event reproduction |
| Track-aware events | Per-rule/per-player keys, onset, detection time, interval, peak, threshold and source tracks | Event interval and missing-frame reset tests |
| Actionable feedback | Coach explanation, player cue and exercise per observation | Review cards and exports |
| Human interpretation | Confirm/dismiss/uncertain verdict, reviewer and persistent notes | API review/export and browser save/reopen checks |
| Missed events and reviewed negatives | Separate human-authored event labels, reviewed periods, reviewer role, attestation, source checksum and revision-safe saves | API and browser checks; no automatic copying of predictions into truth |
| Visual explanation | Synchronized match frames, boxes/IDs, minimap, reference-role offsets, static lanes, time scrubber, shape chart and event jumps | Desktop/mobile browser smoke checks |
| Reproducibility | Reviewed JSON, tracks CSV, annotated AVI, model/config/source manifest and session library | Export and file lifecycle tests |
| Evaluation | Reviewed-interval event precision/recall, misses, false alarms and onset latency; reviewer agreement helper | Evaluation tests with controlled labels |

The coaching UI is in `web/`; the local API is `src/server.py`. Start with
`python run_app.py` and open `http://127.0.0.1:8000`. `README.md` explains the entire
workflow and its use for coaches, players and analysts.

Recommendations use coaching heuristics, not a trained win-probability model.
Match flow is assessed through observed spacing and shape changes, not a claim of
automatic ball possession, intent recognition or official tactical judgement.
A local-view event explicitly states that support may exist off-screen.

### Original phase exit gates still open

- Coach-reviewed event and negative-interval labels with a documented annotation standard.
- Actual reviewer agreement and reconciliation; predictions cannot serve as their own truth.
- Reviewer-approved frozen acceptance thresholds; held-out event metrics, latency and coverage.
- Sensitivity analysis and comparison with the fixed-reference baseline on the same labelled clips.
- Separately validated ball localisation/possession before claiming ball-aware passing usefulness.

`docs/VALIDATION.md` describes these evidence gates and the tools that support them.
The implementation does not fabricate coaches, annotations, benchmark scores or
submission clearance. Static lanes remain geometric guides; offside adjudication
is outside this roadmap.

## Verification record

- Phase 1 synthetic precision/recall/error and failure-abstention checks remain in the suite.
- New checks cover formations, scoring context, observation records, tracking, camera motion,
  persistence, partial views, upload errors, complete jobs, review persistence and exports.
- Browser checks run the actual interface at desktop and 390px mobile widths, exercise
  playback and saved reviews, and detect uncaught JavaScript errors.
- The synthetic coaching demo detects the designed drift at 2.8 s after 0.8 s
  persistence, with an observed event interval beginning at 2.0 s. Phase 1's original
  five-frame-at-20-FPS check remains unchanged.
- Final verification: **47 Python tests passed**, JavaScript syntax passed, all Python modules
  compiled, and desktop/mobile browser checks passed with no uncaught JavaScript errors.
  Both supplied videos completed whole-interval HTTP processing and all four exports.
  The overhead run processed 74 samples and produced two local review observations;
  the Getty run processed 19 samples and produced no sustained events. **Neither
  supplied clip supported whole-team shape measurements** under the tested configuration.
  Full test/browser and supplied-video results are recorded in `results/app_verification.json`. Unlabelled real clips do not establish
  held-out accuracy or complete the remaining external validation gates.
