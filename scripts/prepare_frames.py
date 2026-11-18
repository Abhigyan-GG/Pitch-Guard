"""Extract source frames for human detection labels; never pseudo-label a test set."""
import argparse
import json
from pathlib import Path

import cv2

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--video',required=True);p.add_argument('--match-id',required=True)
    p.add_argument('--split',required=True,choices=['train','validation','test'])
    p.add_argument('--output',default='datasets/label-workspace');p.add_argument('--every-seconds',type=float,default=2)
    args=p.parse_args()
    if args.every_seconds<=0:raise SystemExit('Sampling interval must be positive')
    if not args.match_id or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in args.match_id):
        raise SystemExit('Use an alphanumeric match ID')
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    registry=out/'matches.json';matches=json.loads(registry.read_text()) if registry.exists() else {}
    if args.match_id in matches and matches[args.match_id]!=args.split:raise SystemExit('Match already assigned to another split')
    images=out/'images'/args.split;images.mkdir(parents=True,exist_ok=True)
    cap=cv2.VideoCapture(str(Path(args.video)));fps=cap.get(cv2.CAP_PROP_FPS)
    if not cap.isOpened() or fps<=0:raise SystemExit('Unreadable video')
    matches[args.match_id]=args.split;registry.write_text(json.dumps(matches,indent=2))
    step=max(1,round(fps*args.every_seconds));count=int(cap.get(cv2.CAP_PROP_FRAME_COUNT));written=[]
    try:
        for frame in range(0,count,step):
            cap.set(cv2.CAP_PROP_POS_FRAMES,frame);ok,image=cap.read()
            if not ok:break
            name=f'{args.match_id}-{frame:07d}.jpg';target=images/name
            if target.exists():raise SystemExit(f'Refusing to replace {target}')
            if not cv2.imwrite(str(target),image):raise OSError('Cannot save annotation frame')
            written.append({'image':str(target),'source_frame':frame,'time_s':frame/fps})
    finally:cap.release()
    (out/f'{args.match_id}-frames.json').write_text(json.dumps(written,indent=2))
    print(f'Extracted {len(written)} frames. Add human YOLO labels under labels/{args.split}; no labels have been invented.')
