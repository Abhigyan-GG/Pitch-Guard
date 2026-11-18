# Player detection models

The app prefers `football-yolov8s.pt` when installed; otherwise it uses COCO
`yolov8n.pt`. Set `PITCHGUARD_MODEL` before starting the server for your own local
Ultralytics-compatible weights. The model must expose person, player or goalkeeper
class names. Referee and ball classes are excluded from player observations.

## Football-specific model

Run `python scripts/fetch_football_model.py` once (internet needed).
Source: https://huggingface.co/AurevinP/PULSE_AI_Models
File: `yolov8s_player_tracker.pt`, revision
`5c7b65a062557736baa036af15ca469f8a5b2847`.
SHA-256: `74b71f4ab2f5f8bfafff3679a2f5a06f994fc6fe6963df500a223d80e8047c70`.
The model card credits a football fine-tune of Ultralytics YOLOv8s. Its declared
repository license does not remove the underlying framework's license obligations;
see the upstream model card and https://www.ultralytics.com/license.
Metadata is preserved in `football-model.json`. This is third-party pretraining,
not training on the two user-supplied clips. Its published metrics are not
PitchGuard's results.

## General model

Run `python scripts/setup_model.py --download`.
Ultralytics YOLOv8n, COCO-pretrained person class 0.
Upstream: https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt
SHA-256: `f59b3d833e2ff32e194b5bb8e08d211dc7c5bdf144b90d2c8412c47ccfc83b36`.
The local copy was reused from the existing local environment.

Every analysis records model filename, class map, package version and actual weight
checksum. Weights are large local setup artifacts. Do not use the weights as evidence
of validation on your footage.
