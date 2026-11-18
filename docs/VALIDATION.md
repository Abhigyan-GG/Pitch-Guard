# Labels, training and validation

The application is implemented; external accuracy gates require independent human
labels. Synthetic regression tests, unlabelled video smoke runs and model-author
metrics are different evidence categories and must stay separate.

## Data inventory and splits

`datasets/manifest.json` records the two user-supplied sources. They are currently
an unlabelled validation inventory, not a training/test benchmark. One match must
never occur in more than one split, including alternate clips, resolutions or cuts.
For real training add separate matches for train, validation and test. Two clips
alone do not provide three independent match splits.

Record a real match identity, clip interval, source location, permission/access note,
annotation version, and actual split. `validate_splits` rejects match leakage.
Do not treat a public model's original training data as known-independent of a
stock clip unless that overlap has been checked.

## 1. Extract frames for human labels

```powershell
python scripts/prepare_frames.py --video "path/to/match.mp4" --match-id match-a --split train --every-seconds 2
```

Repeat with different matches for validation and test. Frames are written to
`datasets/label-workspace/images/<split>`. The registry prevents reassigning the
same match ID to another split. Existing extracted images are not overwritten.

Annotate person/player boxes with a human annotation tool. Write YOLO text files
under `labels/<split>/<same-image-stem>.txt`. Each line uses:

```text
0 centre_x_fraction centre_y_fraction width_fraction height_fraction
```

Class 0 is person. Include players, keep consistent referee/goalkeeper conventions,
and document those conventions. Use a genuinely reviewed empty file for a negative
image. Do not invent boxes, auto-approve predictions, or create empty files for
unreviewed frames. `human_labels_verified` in the manifest must only become true
when the labels were actually checked.

## 2. Fine-tune after labels exist

```powershell
python scripts/train_detector.py --dataset datasets/label-workspace --manifest datasets/manifest.json --epochs 30 --device cpu
```

The script requires labelled images and separate match splits for all three sets.
It trains a COCO-initialised YOLOv8n using train and validation images; test images
are never passed as training or validation inputs. Output is in
`artifacts/training/player-detector` by default. Training can take substantial time
on a CPU. Set an installed compatible GPU device if one is available.

The script refuses to overwrite an existing `data.yaml`; preserve experiments
before running again. After training, set `PITCHGUARD_MODEL` to the new `best.pt`
before restarting the app. A compatible model must name a person/player/goalkeeper
class. Use validation clips to tune kit assignment, detection confidence, spatial
thresholds and persistence. Freeze those settings before running the test clips.
The script does not report a held-out score merely because training finished.

## 3. Label pitch positions and calibration

Analyse the clip and export `result.json`. Independently label selected sampled
frames. The sample frame indices are in the result timeline and tracks CSV.
For each player record team, an identity maintained across frames, and manually
verified pitch coordinates. Keep hidden players in denominators only under a
clearly documented visibility convention. Position error is measured over matched
pairs and always reported alongside recall and coverage.

Add **extra** manually verified landmarks, distinct from the points used to fit
calibration. Image positions are pixels; world positions are metres. Calibration
error is computed by projecting these world landmarks through the inverse recorded
homography and measuring image residual. Missing independent landmarks yield no
calibration score, rather than a made-up residual.

Label structure:

```json
{
  "clip_id": "test-clip-a",
  "annotation_version": "human-v1",
  "frames": [
    {
      "frame": 0,
      "players": [
        {"identity": "own-01", "team": "own", "xy": [30.0, 24.0]},
        {"identity": "opp-01", "team": "opponent", "xy": [50.0, 40.0]}
      ],
      "landmarks": [
        {"world_xy": [52.5, 34], "image_xy": [480, 300]}
      ]
    }
  ],
  "events_reviewed": false,
  "reviewed_intervals": [],
  "events": []
}
```

These coordinates are **format examples**, not labels for either supplied video.
Include every player under the chosen visibility convention, not only successful
predictions. Event reviews saved in the app are useful annotations, but an automatic
candidate list alone cannot reveal missed events. Review negative intervals too.

## Human label collection in the app

The review room now includes **Your own observations**. It supports manually entered
missed events, intended/uncertain movement, and reviewed negative periods, plus a
reviewer identity/role and draft/completed state. The exported `human-labels.json`
is separate from predictions, bound to the source SHA-256, and records the context
that model predictions were available during review. It does not copy automatic
candidate verdicts into truth. Use separate blinded labels for a final independent
benchmark. No genuine labels have been claimed from automated UI fixtures.

Only an attested coach review sets `events_reviewed: true`. Resolve uncertainty or
exclude that time period before attesting. Analyst/player labels remain usable notes,
and preserve their source role. Empty event lists are valid for reviewed negatives;
recall is undefined when no positive truth events exist. The evaluator reports false
alarms per reviewed minute and never treats missing positives as perfect recall.

The CLI supports event-only exports without player-position labels. A draft/noncoach
review with no position labels cannot establish an accuracy report. Source checksums
must match the analysis when the label export includes one.

## 4. Coach-reviewed tactical events

Agree an annotation specification before evaluation:

- What counts as an unplanned role departure, a disconnected unit, a defensive
  channel, excessive depth, insufficient support or an abrupt shape disruption?
- When is the movement intended? How is possession established? How are corners,
  set pieces, substitutions, goalkeepers and incomplete views handled?
- What are the event start/end rules? How much disagreement can be tolerated?

Use two reviewers on a shared subset. Record each item with an `item_id` and a
`judgement` of issue/intended/uncertain. `reviewer_agreement` reports raw agreement
and disagreement IDs for reconciliation. It does not claim agreement without two
actual review lists.

In a completed label file set `events_reviewed: true`, record intervals that were
reviewed including negatives, and add actual events:

```json
{
  "events_reviewed": true,
  "reviewed_intervals": [[0, 20]],
  "events": [
    {"kind": "unit_gap", "start_s": 4.0, "end_s": 7.5}
  ]
}
```

Valid kinds: `role_drift`, `unit_gap`, `defensive_gap`, `stretched_shape`,
`support_isolation`, `shape_disruption`. The app records source player IDs,
onset, activation latency, duration, measured peak, rule threshold and context.
Partial-view events are explicitly scoped to visible teammates. A geometric
candidate is not an adjudicated coaching flaw.

## 5. Held-out evaluation and acceptance

```powershell
python -m src.evaluation --result path/to/result.json --labels path/to/human-labels.json --manifest datasets/manifest.json --clip-id test-clip-a --output results/held-out-evaluation.json
```

The selected clip must be declared a test clip. The evaluator measures:

- Team-aware matching below 2 m: precision, recall and mean matched Euclidean error.
- Team-shape coverage and changes in predicted ID for the same labelled player.
- Independent landmark reprojection error when extra landmarks exist.
- Event precision/recall, false alarms, missed events and mean onset latency.
  Event matching is one-to-one, by kind and temporal IoU of at least 0.3, measured
  inside the explicitly reviewed intervals. A prediction that crosses a reviewed
  boundary is included; it cannot disappear from the false-alarm count just because
  its full duration extends beyond the reviewed window.

This identity-switch count is not a full HOTA/IDF1 benchmark. Runtime is the
end-to-end processing time in the run manifest; it includes video decoding,
registration, detection, tactics and video writing.

A reviewer may supply a separate `--targets path/to/targets.json`. It must contain
`approved_by`, `frozen_before_test` and `metrics` with actual agreed thresholds,
for example keys `locations.precision` (min), `locations.recall` (min),
`locations.mean_position_error_m` (max), `events.precision` (min),
`events.recall` (min) and `events.mean_onset_latency_s` (max). The evaluator refuses
an unapproved/unfrozen target file. Missing metrics fail their acceptance checks.
Do not tune on test results and then present the same test as held out.

Before claiming Phase 2/3 validated completion, preserve the dataset/split versions,
label files, reviewer agreement, model and code checksums, frozen thresholds,
independent calibration and tracking results, sensitivity analysis and baseline
comparison on the same labelled clips. Run multiple validation configurations for
threshold sensitivity, then make one frozen test run. Ball-aware passing usefulness
requires separate ball labels and its own location/possession reliability study;
the current app deliberately keeps lanes as static geometric guides.
