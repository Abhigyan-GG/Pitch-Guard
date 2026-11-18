# Detector weights

The local model is Ultralytics YOLOv8n, COCO pretrained (person class 0).
`yolov8n.pt` is reused from the local environment, not trained on PitchGuard footage.
Upstream: https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt
Ultralytics licensing: https://www.ultralytics.com/license
Weights are ignored by Git. Run `python scripts/setup_model.py --download` in a new clone.
A run manifest records the actual weight checksum and package version.
