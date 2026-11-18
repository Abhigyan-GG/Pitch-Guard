"""Download the football-specific model with pinned upstream revision and checksum."""
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parents[1]
REPO="AurevinP/PULSE_AI_Models"
FILENAME="yolov8s_player_tracker.pt"
revision="5c7b65a062557736baa036af15ca469f8a5b2847"
expected="74b71f4ab2f5f8bfafff3679a2f5a06f994fc6fe6963df500a223d80e8047c70"
url=f"https://huggingface.co/{REPO}/resolve/{revision}/{FILENAME}"
target=ROOT/"models/football-yolov8s.pt"
target.parent.mkdir(exist_ok=True)
if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest()!=expected:
    temporary=target.with_suffix(".download")
    with urlopen(url,timeout=90) as response,temporary.open("wb") as output:
        while chunk:=response.read(1024*1024):output.write(chunk)
    if hashlib.sha256(temporary.read_bytes()).hexdigest()!=expected:
        temporary.unlink();raise SystemExit("Model checksum mismatch")
    temporary.replace(target)
record={"repository":REPO,"revision":revision,"filename":FILENAME,"sha256":expected,"url":url,
        "model_card":f"https://huggingface.co/{REPO}","upstream_base":"Ultralytics YOLOv8s"}
(ROOT/"models/football-model.json").write_text(json.dumps(record,indent=2)+"\n")
print(json.dumps(record,indent=2))
