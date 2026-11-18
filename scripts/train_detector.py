"""Fine-tune only after manual YOLO labels and split provenance are supplied."""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.evaluation import validate_splits

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dataset',required=True)
    p.add_argument('--manifest',required=True);p.add_argument('--epochs',type=int,default=30)
    p.add_argument('--device',default='cpu');p.add_argument('--output',default='artifacts/training')
    args=p.parse_args();dataset=Path(args.dataset).resolve()
    manifest=json.loads(Path(args.manifest).read_text());clips=validate_splits(manifest)
    if not all(any(c['split']==split for c in clips) for split in ['train','validation','test']):
        raise SystemExit('Declare separate train, validation and test matches before training')
    if not manifest.get('human_labels_verified'):raise SystemExit('Verify human labels before training')
    expected_splits={c['match_id']:c['split'] for c in clips}
    if not (dataset/'matches.json').is_file():raise SystemExit('Extract frames with prepare_frames.py to preserve match provenance')
    registry=json.loads((dataset/'matches.json').read_text())
    if any(expected_splits.get(match)!=split for match,split in registry.items()):
        raise SystemExit('Extracted-frame registry does not match declared match splits')
    for split in ['train','validation','test']:
        images=list((dataset/'images'/split).glob('*.jpg'))
        if not images:raise SystemExit(f'No {split} images')
        for image in images:
            source_match=image.stem.rsplit('-',1)[0]
            if registry.get(source_match)!=split:raise SystemExit(f'Unknown or misplaced source match for {image.name}')
            if not (dataset/'labels'/split/(image.stem+'.txt')).is_file():
                raise SystemExit(f'Missing human label for {image.name}; empty .txt is allowed for reviewed negatives')
    config=dataset/'data.yaml'
    if config.exists():raise SystemExit('data.yaml already exists. Preserve the previous experiment before retraining.')
    config.write_text(f'path: {json.dumps(str(dataset))}\ntrain: images/train\nval: images/validation\ntest: images/test\nnames:\n  0: person\n')
    os.environ.setdefault('YOLO_CONFIG_DIR',str(ROOT/'.runtime/ultralytics'))
    from ultralytics import YOLO
    model=YOLO(str(ROOT/'models/yolov8n.pt'))
    model.train(data=str(config),epochs=args.epochs,device=args.device,imgsz=960,batch=2,workers=0,
                project=str(Path(args.output).resolve()),name='player-detector',exist_ok=False)
    print('Training finished. Freeze detection/team/tactical thresholds on validation clips before evaluating held-out test footage.')
