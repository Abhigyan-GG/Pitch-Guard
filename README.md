# PitchGuard

Fixed-camera football pitch and formation analysis using synthetic red/blue markers.
The three-phase roadmap and acceptance evidence are in [implementation.md](implementation.md).

## Setup

Python 3.10 or newer. The pinned dependencies match the local Phase 1 verification environment.
No GPU, model weights, web service, or external dataset is required.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python src/pitchguard.py --demo
python src/pitchguard.py --video data/synthetic_input.avi --calibration data/calibration.json --output results/replay
python -m pytest -q
```

The demo regenerates a 120-frame, 20 FPS input clip, annotated video, minimap,
colour masks, line diagnostics, failure examples, event log, metrics CSV/JSON,
and environment record. Output files are in `results/`; generated input is in `data/`.
Open `results/demo.avi` or inspect `results/overlay.png` and `results/minimap.png`.

## Calibration and outputs

`data/calibration.json` contains ordered image corners (TL, TR, BR, BL),
`pitch_m: [105, 68]`, and `image_size: [960, 600]`. Replace the corners and image
size together for a compatible stationary camera. Resolution mismatch is rejected;
convexity and winding checks cannot establish the semantic correctness of corners.

The red reference is a fixed 4-3-3 including the goalkeeper. Hungarian assignment
removes median team translation; displacement above 8 m for five consecutive valid
frames raises an alert. Invalid counts or recovery reset persistence. Synthetic
alerts occupy frames 44-79, with raw displacement at 40-79.
Replay `events.json` includes per-frame role distances, width, depth, defensive gap,
line position and candidate passing lanes. Lane indices refer to that frame's red
point order, not persistent player identities.

Evaluation uses five conditions with 24 frames each and team-aware matching below
2 m. `mean_position_error_m` is mean Euclidean error of accepted matches. Coverage
requires 11 markers per team. Timing excludes generation, decode, rendering and encoding.
The report's `position_mae_m` key was renamed to describe its actual calculation.
Diagnostic team masks now show the opening operation used by detection.

## Scope and provenance

The starting algorithm was supplied alongside `PitchGuard_IVP_Report.pdf` in
`PitchGuard_Submission_Kit/PitchGuard_Source/PitchGuard/src/pitchguard.py`, credited
to the report team: Abhigyan, Rohit, and Vabhravi. This repository adapts that source,
adds input/output validation, tests, run documentation and freshly generated evidence.
It does not claim an independently authored algorithm or reuse the kit's measured outputs.

All demonstrated players are synthetic circles. Human-player detection, identity
tracking, moving-camera registration, ball detection and coach-reviewed tactical
accuracy remain future phases. White Hough segments are diagnostic. Defensive
and passing guides describe static geometry; they do not decide offside or pass success.
The full-team count check cannot catch every localization error.
