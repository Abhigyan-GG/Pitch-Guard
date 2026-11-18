"""Explicit, checksum-verified download of the standard COCO person model."""
import argparse
import hashlib
from pathlib import Path
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parents[1]
URL='https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt'
EXPECTED='f59b3d833e2ff32e194b5bb8e08d211dc7c5bdf144b90d2c8412c47ccfc83b36'

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--download',action='store_true');args=parser.parse_args()
    target=ROOT/'models/yolov8n.pt';target.parent.mkdir(exist_ok=True)
    if target.exists():
        digest=hashlib.sha256(target.read_bytes()).hexdigest()
        if digest!=EXPECTED:raise SystemExit('Existing model checksum differs. Preserve custom weights separately before installing the standard model.')
        print('YOLOv8n is ready:',digest)
    elif args.download:
        temp=target.with_suffix('.download')
        try:
            with urlopen(URL,timeout=60) as response,temp.open('wb') as output:
                while chunk:=response.read(1024*1024):output.write(chunk)
            if hashlib.sha256(temp.read_bytes()).hexdigest()!=EXPECTED:raise ValueError('Weight checksum verification failed')
            temp.replace(target);print('Installed YOLOv8n')
        finally:
            if temp.exists():temp.unlink()
    else:raise SystemExit('Use --download to fetch model weights, or place the verified model in models/yolov8n.pt')
