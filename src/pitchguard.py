"""PitchGuard: fixed-camera, calibrated colour-marker tactical baseline.
Synthetic markers are proxies, not evidence of real human detection accuracy.
"""
import argparse, csv, json, platform, time
from pathlib import Path
import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment

ROOT = Path(__file__).resolve().parents[1]
ANCHORS = np.float32([[8,34],[27,12],[27,27],[27,42],[27,57],[48,14],[48,34],[48,54],[72,14],[72,34],[72,54]])
CORNERS = np.float32([[110,70],[850,105],[925,550],[35,550]])
WORLD = np.float32([[0,0],[105,0],[105,68],[0,68]])
COLORS = {'red':(45,45,230),'blue':(230,95,30)}

def project(points, H):
    return cv2.perspectiveTransform(np.float32(points).reshape(1,-1,2),H)[0]

def calibration(corners):
    corners=np.float32(corners)
    if (corners.shape != (4,2) or not np.isfinite(corners).all()
            or not cv2.isContourConvex(corners) or cv2.contourArea(corners, oriented=True) < 100):
        raise ValueError('Four ordered, non-collinear pitch corners required: TL TR BR BL')
    H=cv2.getPerspectiveTransform(corners,WORLD)
    return H

def open_writer(path, fps, size):
    writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'MJPG'),fps,size)
    if not writer.isOpened():
        writer.release()
        raise OSError(f'Cannot open video output: {path}')
    return writer


def load_calibration(config):
    settings=json.loads(Path(config).read_text())
    if settings.get('pitch_m') != [105,68]:
        raise ValueError('Calibration must describe a 105 by 68 metre pitch')
    size=settings.get('image_size')
    if (not isinstance(size,list) or len(size)!=2
            or any(type(v) is not int or v<=0 for v in size)):
        raise ValueError('Calibration requires image_size: [width, height]')
    return calibration(settings['corners']),tuple(size)


def pitch_canvas():
    img=np.full((408,630,3),(46,115,40),np.uint8)
    for x in range(0,630,60): img[:,x:x+30]=(48,125,42)
    cv2.rectangle(img,(1,1),(628,406),(235,235,235),2)
    cv2.line(img,(315,0),(315,407),(235,235,235),2)
    cv2.circle(img,(315,204),55,(235,235,235),2)
    for x,sgn in [(0,1),(629,-1)]:
        cv2.rectangle(img,(min(x,x+sgn*99),83),(max(x,x+sgn*99),325),(235,235,235),2)
    return img

def synthetic_frame(t=0, case='clean', broken=False):
    red=ANCHORS.copy(); red[:,1]+=np.sin(t*.15)*.8
    if broken: red[1,0]+=18
    blue=ANCHORS.copy();blue[:,0]=105-blue[:,0];blue[:,1]=68-blue[:,1]+2
    top=pitch_canvas()
    for team,pts in [('red',red),('blue',blue)]:
        for i,(x,y) in enumerate(pts):
            if case=='occluded' and team=='red' and i in (1,2,3): continue
            color=COLORS[team]
            if case=='same_kit' and team=='blue': color=COLORS['red']
            cv2.circle(top,tuple(np.int32([x*6,y*6])),7,color,-1)
    M=cv2.getPerspectiveTransform(np.float32([[0,0],[629,0],[629,407],[0,407]]),CORNERS)
    frame=cv2.warpPerspective(top,M,(960,600),borderValue=(28,31,35))
    if case=='dim': frame=(frame*.40).astype(np.uint8)
    if case=='blur': frame=cv2.GaussianBlur(frame,(15,15),4)
    truth={'red':red.tolist(),'blue':blue.tolist(),'broken':broken}
    return frame,truth

def detect(frame,H):
    hsv=cv2.cvtColor(frame,cv2.COLOR_BGR2HSV)
    grass=cv2.inRange(hsv,(30,35,20),(95,255,255))
    white=cv2.inRange(hsv,(0,0,140),(179,65,255))
    edges=cv2.Canny(white,50,150)
    lines=cv2.HoughLinesP(edges,1,np.pi/180,35,minLineLength=45,maxLineGap=15)
    masks={'red':cv2.bitwise_or(cv2.inRange(hsv,(0,110,65),(12,255,255)),cv2.inRange(hsv,(170,110,65),(179,255,255))),
           'blue':cv2.inRange(hsv,(95,110,65),(130,255,255))}
    positions={}; centers={}
    for team,mask in masks.items():
        mask=cv2.morphologyEx(mask,cv2.MORPH_OPEN,np.ones((3,3),np.uint8))
        masks[team]=mask
        cnts,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        pix=[]
        for c in cnts:
            area=cv2.contourArea(c)
            if not 35 <= area <= 900: continue
            m=cv2.moments(c)
            if m['m00']: pix.append([m['m10']/m['m00'],m['m01']/m['m00']])
        if pix:
            pix=np.float32(pix); xy=project(pix,H)
            good=(xy[:,0]>=0)&(xy[:,0]<=105)&(xy[:,1]>=0)&(xy[:,1]<=68)
            positions[team]=xy[good];centers[team]=pix[good]
        else: positions[team]=np.empty((0,2));centers[team]=np.empty((0,2))
    return positions,centers,{'grass':grass,'white':white,'red':masks['red'],'blue':masks['blue'],'lines':lines}

def tactics(positions):
    red=positions['red'];blue=positions['blue']
    # Fail closed when the full expected team is unavailable.
    result={'valid':len(red)==11 and len(blue)==11,'breach':False,'deviations':[], 'lanes':[]}
    if not result['valid']: return result
    # Remove collective translation before comparing shape to the reference.
    shift=np.median(red,axis=0)-np.median(ANCHORS,axis=0)
    cost=np.linalg.norm((red-shift)[:,None,:]-ANCHORS[None,:,:],axis=2)
    rows,cols=linear_sum_assignment(cost)
    ordered=np.empty_like(red);ordered[cols]=red[rows]
    deviations=np.linalg.norm(ordered-shift-ANCHORS,axis=1)
    result.update(deviations=deviations.tolist(),breach=bool(np.any(deviations>8)),ordered=ordered.tolist(),
                  defensive_line=float(np.median(ordered[1:5,0])),width=float(np.ptp(red[:,1])),depth=float(np.ptp(red[:,0])))
    defenders=ordered[1:5][np.argsort(ordered[1:5,1])]
    result['max_defensive_gap']=float(np.max(np.diff(defenders[:,1])))
    for i in range(11):
        for j in range(i+1,11):
            a,b=red[i],red[j];v=b-a;length=np.linalg.norm(v)
            if length<5 or length>35:continue
            u=np.clip(((blue-a)@v)/(length*length),0,1)
            clearance=np.min(np.linalg.norm(blue-(a+u[:,None]*v),axis=1))
            if clearance>2:result['lanes'].append([i,j,float(clearance)])
    return result

class Persistence:
    def __init__(self):self.count=0
    def update(self,state):
        self.count=self.count+1 if state['valid'] and state['breach'] else 0
        return self.count>=5

def visualize(frame,positions,centers,state,alert=False):
    overlay=frame.copy(); mini=pitch_canvas()
    for team,pts in positions.items():
        for i,p in enumerate(pts):
            cv2.circle(mini,tuple(np.int32(p*6)),7,COLORS[team],-1)
            c=tuple(np.int32(centers[team][i]));cv2.circle(overlay,c,13,COLORS[team],2)
    if state['valid']:
        x=int(state['defensive_line']*6);cv2.line(mini,(x,0),(x,407),(0,255,255),2)
        for i,j,_ in state['lanes']:
            cv2.line(mini,tuple(np.int32(positions['red'][i]*6)),tuple(np.int32(positions['red'][j]*6)),(180,210,160),1)
        for i,p in enumerate(state['ordered']):
            if state['deviations'][i]>8:cv2.circle(mini,tuple(np.int32(np.array(p)*6)),13,(0,255,255),3)
    text=('FORMATION ALERT' if alert else 'Shape within threshold') if state['valid'] else 'INSUFFICIENT / AMBIGUOUS DETECTIONS'
    cv2.putText(overlay,text,(30,35),cv2.FONT_HERSHEY_SIMPLEX,.75,(0,255,255),2)
    cv2.putText(overlay,'SYNTHETIC MARKER DEMO',(30,585),cv2.FONT_HERSHEY_SIMPLEX,.6,(255,255,255),1)
    return overlay,mini

def evaluate(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    H=calibration(CORNERS);summaries=[]
    for case in ['clean','dim','blur','occluded','same_kit']:
        tp=fp=fn=0;errors=[];correct=valid=0;times=[]
        for t in range(24):
            frame,gt=synthetic_frame(t,case,t>=12)
            tic=time.perf_counter();p,c,d=detect(frame,H);s=tactics(p);times.append(time.perf_counter()-tic)
            valid+=int(s['valid']);correct+=int(s['valid'] and s['breach']==gt['broken'])
            for team in COLORS:
                truth=np.array(gt[team]);pred=p[team]
                if len(pred):
                    cost=np.linalg.norm(truth[:,None,:]-pred[None,:,:],axis=2);a,b=linear_sum_assignment(cost)
                    matched=cost[a,b]<2;n=int(matched.sum());errors.extend(cost[a[matched],b[matched]].tolist())
                else:n=0
                tp+=n;fp+=len(pred)-n;fn+=len(truth)-n
        summaries.append({'case':case,'frames':24,'precision':round(tp/max(tp+fp,1),4),'recall':round(tp/max(tp+fn,1),4),
           'mean_position_error_m':round(float(np.mean(errors)),3) if errors else None,'coverage':round(valid/24,4),
           'formation_accuracy_all_frames':round(correct/24,4),'analysis_fps':round(24/sum(times),1)})
    (out/'metrics.json').write_text(json.dumps(summaries,indent=2))
    with (out/'metrics.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=summaries[0]);w.writeheader();w.writerows(summaries)
    return summaries

def demo(out):
    out.mkdir(parents=True,exist_ok=True);(ROOT/'data').mkdir(exist_ok=True)
    H=calibration(CORNERS);persist=Persistence();events=[]
    writer=open_writer(out/'demo.avi',20,(960,600))
    source=open_writer(ROOT/'data'/'synthetic_input.avi',20,(960,600))
    try:
        for t in range(120):
            frame,gt=synthetic_frame(t,broken=40<=t<80);source.write(frame)
            p,c,d=detect(frame,H);s=tactics(p);alert=persist.update(s);ov,mini=visualize(frame,p,c,s,alert);writer.write(ov)
            events.append({'frame':t,'time_s':t/20,'ground_truth_breach':gt['broken'],'valid':s['valid'],'raw_breach':s['breach'],'alert':alert})
            if t==55:
                cv2.imwrite(str(out/'input.png'),frame);cv2.imwrite(str(out/'overlay.png'),ov);cv2.imwrite(str(out/'minimap.png'),mini)
                for k in ['grass','white','red','blue']:cv2.imwrite(str(out/f'{k}_mask.png'),d[k])
                line=frame.copy()
                if d['lines'] is not None:
                    for x1,y1,x2,y2 in d['lines'][:,0]:cv2.line(line,(x1,y1),(x2,y2),(0,255,255),2)
                cv2.imwrite(str(out/'line_segments.png'),line)
    finally:
        writer.release();source.release()
    (out/'events.json').write_text(json.dumps(events,indent=2))
    frame,_=synthetic_frame(55,'occluded',True);p,c,d=detect(frame,H);s=tactics(p)
    cv2.imwrite(str(out/'failure_input.png'),frame);cv2.imwrite(str(out/'failure_output.png'),visualize(frame,p,c,s)[0])
    (ROOT/'data'/'calibration.json').write_text(json.dumps({'corners':CORNERS.tolist(),'order':'top-left top-right bottom-right bottom-left','pitch_m':[105,68],'image_size':[960,600]},indent=2))
    metrics=evaluate(out)
    (out/'environment.json').write_text(json.dumps({'python':platform.python_version(),'opencv':cv2.__version__,'numpy':np.__version__,'platform':platform.platform(),'cpu':platform.processor(),'image_size':[960,600],'timing':'detection and tactics only; excludes generation, decode, render and encoding'},indent=2))
    print(json.dumps(metrics,indent=2))

def analyze(video,config,out):
    out=Path(out)
    H,expected_size=load_calibration(config)
    cap=cv2.VideoCapture(str(video))
    if not cap.isOpened():
        cap.release()
        raise ValueError(f'Cannot open video: {video}')
    fps=cap.get(cv2.CAP_PROP_FPS)
    if not np.isfinite(fps) or fps<=0:fps=20
    writer=None;events=[];persist=Persistence();t=0
    try:
        while True:
            ok,frame=cap.read()
            if not ok:break
            if (frame.shape[1],frame.shape[0])!=expected_size:
                raise ValueError('Video resolution differs from calibration image_size')
            p,c,d=detect(frame,H);s=tactics(p);alert=persist.update(s)
            ov,mini=visualize(frame,p,c,s,alert)
            if writer is None:
                out.mkdir(parents=True,exist_ok=True)
                writer=open_writer(out/'analyzed.avi',fps,expected_size)
            writer.write(ov)
            if not cv2.imwrite(str(out/'latest_minimap.png'),mini):
                raise OSError('Cannot write minimap')
            events.append({'frame':t,'time_s':t/fps,'valid':s['valid'],
                           'breach':s['breach'],'alert':alert,
                           'tactics':s});t+=1
    finally:
        cap.release()
        if writer is not None:writer.release()
    if not t:raise ValueError('No readable video frames')
    (out/'events.json').write_text(json.dumps(events,indent=2))
    print(f'Processed {t} frames into {out}')


if __name__=='__main__':
    ap=argparse.ArgumentParser();mode=ap.add_mutually_exclusive_group(required=True);mode.add_argument('--demo',action='store_true');mode.add_argument('--video');ap.add_argument('--calibration',default=str(ROOT/'data'/'calibration.json'));ap.add_argument('--output',default=str(ROOT/'results'));a=ap.parse_args()
    if a.demo:demo(Path(a.output))
    elif a.video:analyze(a.video,a.calibration,Path(a.output))
    else:ap.error('Use --demo or --video PATH')
