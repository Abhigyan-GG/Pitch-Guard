# PitchGuard Coaching Studio

PitchGuard helps coaches prepare a match plan and turn visible movement in match
footage into specific conversations and training exercises. It runs locally in your
browser; uploads and coaching notes stay on your computer.

## Start the app

Use Python 3.10 or 3.11. From this project folder on Windows:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scripts/fetch_football_model.py
python run_app.py
```

Open **http://127.0.0.1:8000**. Keep the terminal running. Press Ctrl+C to stop.
The first setup downloads Python packages and the football player model; subsequent
analysis runs do not need internet. The already-installed local model is ready to use.
If PowerShell activation is restricted, use `.venv\Scripts\python.exe` instead of
`python` for the commands after creating the virtual environment.

For a lighter general person model, use `python scripts/setup_model.py --download`
instead of fetching the football model. The football model is preferred for distant
players. To use your own compatible trained model, set `$env:PITCHGUARD_MODEL` to
its local path before starting. Model provenance is in [models/README.md](models/README.md).

No npm build, external account, API key or GPU is required. This is a local Python
application with a responsive browser frontend.

## 1. Prepare for an opposition formation

Open **Match preparation**:

1. Select the opposition's expected formation and your team's familiar formation.
2. Choose the objective: balance, keep the ball, protect a lead, or chase a goal.
3. Under **Tailor to your squad**, rate passing, running capacity, wide players,
   striker options and centre-back depth from 1 to 5.
4. Select **Build our match plan**. Compare the recommended system and alternatives,
   the pitch diagram, the opposition's strengths and vulnerabilities, and your talking points.
5. Expand **Why this recommendation?** for the scoring breakdown and coaching references.
   Select **Use as our video reference** to bring that system into analysis.

Supported shapes: 4-3-3, 4-4-2, 4-2-3-1, 3-5-2, 3-4-3, 5-3-2, 4-1-4-1 and a 4-4-2 diamond.
Recommendations are explainable suitability scores, not win probabilities. The best
choice depends on the actual opponent, available players and coaching plan. Treat an
entered opposition formation as a prediction to check once the match begins.

## 2. Upload and analyse match footage

Open **Video analysis**. To learn the flow first, select **Try the six-second demo**
and then **Analyse this clip**; demonstration calibration is supplied automatically.
The demo flags a displaced defender and supplies review notes and an exercise.

For your own match:

1. Choose or drag in an MP4, MOV, AVI, MKV, M4V or WebM file. The two clips supplied
   in this workspace also appear in the local clip menu. Their originals are preserved.
2. Choose **Match camera** for learned player detection. For a near-vertical drone
   or overhead view where that detector misses people, choose **Overhead view**.
   This uses kit-colour regions and needs visual checking for split or merged players.
   **Synthetic markers** is only for generated red/blue circles.
3. Pick a clean pixel in each team's shirt with **Pick on image**, or set the kit
   colours directly. Distinct shirts matter; similar shirts or shirts matching grass
   can remain unassigned. Track IDs are temporary identities, not shirt numbers.
4. Select your reference formation and attacking direction. Use **Unknown / mixed**
   possession unless you know which team has the ball. Optional JSON periods allow
   in/out-of-possession context to change over time. There is no automatic ball possession claim.
5. Mark four landmarks at the analysis start frame. For a full view, click actual
   pitch corners: top-left, top-right, bottom-right, bottom-left. For a near-vertical
   overhead view, choose centre-circle extremes: top, right, bottom, left. That mode
   assumes a regulation 9.15 m radius and is unsuitable for an arbitrary angled ellipse.
   Keyboard users can enter four numeric pixel pairs under **Precise landmark coordinates**.
6. Save these landmarks. Move the frame-time slider to a zoom or camera cut, mark the
   four landmarks again, and save another keyframe. The list shows each saved time.
   The camera compensator handles modest motion while reference features remain visible;
   it abstains when registration is lost. It does not discover a whole pitch after a cut.
7. Choose an interval or use the whole clip. Start with 2 samples/second for a faster
   CPU review, then use 5 or 10 for more temporal detail. Click **Analyse this clip**.
   You can cancel; work is kept in the session library with its actual status.

Uploads are limited to 2 GB by default and recordings to three hours. Set
`PITCHGUARD_MAX_UPLOAD_MB` before starting to change the upload limit. An analysis
has at most 60,000 samples; reduce sample rate or split a longer recording. Keep
each half separate when attacking direction changes.

### Review what happened

The review shows a match frame with boxes/track IDs, a pitch map, a width/depth chart,
calibration coverage and timestamped observations. Use the scrubber, step controls,
or **View this moment** to inspect the evidence. The browser frame viewer supports
AVI clips even when the browser cannot play that codec directly.

The geometric rules look for sustained role drift, gaps between units, defensive
channels, excessive depth, distant support and abrupt shape disruption. They are
candidate flow/spacing issues, not automatic proof of a tactical mistake or turnover.
A cropped view supports only local observations; whole-team formation measurements
require enough confidently assigned visible players. Missing teammates are never
invented. With too few reliable observations, the app explicitly withholds findings.

For each observation:

- Read the coaching explanation, individual player cue and suggested exercise.
- Review the preceding seconds for an intentional run, an opponent action or a tracking error.
- Select **Add a coaching review**, then confirm, dismiss or mark it uncertain.
- Save your contextual note and reviewer name. Notes persist across server restarts.
- Export the reviewed JSON, player-observation CSV, annotated AVI or run manifest.

### Add missed moments and reviewed periods

Under **Your own observations**, add a moment even when the system did not flag it.
Choose the event type, enter start/end seconds, decide whether it is an issue,
intended movement or uncertain, and add the training cue. Mark the complete periods
you reviewed, including periods with no issues. These negative periods are needed
to measure false alarms and missed events.

Enter your reviewer name and role. You can save a draft at any time. Confirm the
review only after resolving uncertain events in the reviewed periods. **Export human
labels** produces a separate file containing only your explicitly entered issues;
automatic candidates and their verdicts are not silently copied into label truth.
Analyst/player reviews remain labelled as such. Simultaneous edits in another tab
are rejected with a revision conflict instead of overwriting a saved review.

The label export supports event-only evaluation; it does not invent player positions.
Set its clip identifier to the corresponding dataset manifest ID when preparing an
evaluation. Final independent validation still needs separate labels, match splits
and acceptance targets. Reviews made while predictions are visible retain that context.

Reopen reviews in **Session library**. Delete a session to remove its outputs and
notes. Delete associated sessions before deleting a video record. Removing a local
example record preserves the original clip. Uploaded copies and results live in
`.runtime/`; review exports can also be saved elsewhere by your browser.

## How coaches and players can use it

| User | Practical use | Example next action |
| --- | --- | --- |
| Coach, before a match | Compare counter-systems and their personnel demands | Rehearse switches against a narrow midfield |
| Coach, after a match | Find and discuss a specific gap or disconnected unit | Confirm the cause, then plan a compactness exercise |
| Player | See their movement in relation to teammates and a reference role | Scan before stepping out and agree who covers |
| Analyst | Keep timestamped evidence, uncertainty and coach decisions together | Export reviewed events and compare later sessions |

A productive review is **observe ? discuss intent ? choose one cue ? practise ?
compare the next clip**. A formation deviation may be an excellent attacking run;
use the coach's judgement before turning it into corrective feedback.

## What has been tested

Verification on 18 November 2026: **47 Python tests passed**; desktop/mobile browser
checks passed with no uncaught JavaScript errors, including native video upload and
keyboard calibration. Full records are in `results/app_verification.json`.

The original Phase 1 baseline remains available:

```powershell
python src/pitchguard.py --demo
python src/pitchguard.py --video data/synthetic_input.avi --output results/replay
```

For automated checks:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
# With the app running:
python scripts/smoke_ui.py
```

For a fresh browser-testing installation, run `python -m playwright install chromium`.
The UI smoke checks formation advice, demo analysis, event reviews, playback,
saved sessions, help and mobile overflow. It writes screenshots to `artifacts/`.

Both user-supplied real clips have been exercised as engineering smoke tests.
The overhead recording is cropped and supports local spacing checks. The distant,
watermarked Getty clip remains difficult to classify by team; improved football
weights detect more players, but whole-team tactical coverage is still limited.
Neither clip has supplied coach-reviewed truth, so no real-match accuracy or training
success is claimed. See [implementation.md](implementation.md) for phase status and
[validation guidance](docs/VALIDATION.md) for the remaining evidence gates.

## Training and independent evaluation

User permission to use footage is recorded separately from labels. Unlabelled videos
are useful for workflow testing; they cannot establish detection or tactical accuracy.
The app uses third-party pretrained weights, and has not silently trained on your clips.

[docs/VALIDATION.md](docs/VALIDATION.md) explains extracting frames, adding human
labels, splitting by match, fine-tuning, measuring detection/tracking/calibration and
event metrics, reviewer agreement, and freezing acceptance thresholds before testing.
API documentation is available at http://127.0.0.1:8000/docs while the app runs.

## Project map

- `web/`: responsive coaching frontend and interactive pitch/timeline views.
- `src/server.py`: local API, bounded uploads, queue, durable results and coach reviews.
- `src/vision.py`: learned/overhead detection, kit assignment, tracking and camera registration.
- `src/coaching.py`: formation geometry, sustained event rules and training cues.
- `src/formations.py`: formation profiles and transparent recommendation scores.
- `src/pipeline.py`: video processing and reproducible exports.
- `src/evaluation.py`: separate-label location, identity, calibration and event evaluation.
- `src/annotations.py`: human review labels, reviewed periods and separate truth exports.
- `src/pitchguard.py`: original reproducible synthetic baseline.
- `scripts/`: setup, browser checks, frame extraction and supervised training tools.

Phase 1 originated from the source supplied beside `PitchGuard_IVP_Report.pdf`, credited
to Abhigyan, Rohit and Vabhravi. The new coaching app extends that baseline. Original
report metrics are synthetic evidence. Static passing lanes do not predict pass
success, the defensive guide does not decide offside, and no official adjudication,
player fitness assessment or ball-aware tactical validation is provided.
