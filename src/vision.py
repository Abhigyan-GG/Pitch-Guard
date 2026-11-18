"""Person detection, explicit kit assignment, short-term tracking and registration."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

import cv2

# Avoid oversubscribing CPU cores when decoding and running a model together.
cv2.setNumThreads(2)
import numpy as np
from scipy.optimize import linear_sum_assignment

from .pitchguard import calibration, project, detect


@dataclass
class Observation:
    box: list[float]
    footpoint: list[float]
    confidence: float
    team: str = "unknown"
    team_confidence: float = 0.0
    xy: list[float] | None = None
    track_id: int | None = None
    observed: bool = True

    def record(self):
        return asdict(self)


class PersonDetector:
    """COCO person class; never downloads weights during a video job."""

    def __init__(self, weights: Path, confidence=0.3, image_size=1280):
        if not weights.is_file():
            raise ValueError("Player model missing. Run python scripts/setup_model.py --download, then restart.")
        import torch
        torch.set_num_threads(4)
        from ultralytics import YOLO
        self.model = YOLO(str(weights))
        self.classes=[int(k) for k,v in self.model.names.items() if str(v).lower() in ('person','player','goalkeeper')]
        if not self.classes:raise ValueError('Model must contain person, player or goalkeeper classes')
        self.confidence = confidence
        self.image_size = image_size

    def __call__(self, frame) -> list[Observation]:
        results = self.model.predict(frame, classes=self.classes, conf=self.confidence,
                                     imgsz=self.image_size, device="cpu", verbose=False)[0]
        return [Observation(box=[float(v) for v in box], footpoint=[float((box[0]+box[2])/2), float(box[3])], confidence=float(conf))
                for box, conf in zip(results.boxes.xyxy.cpu().numpy(), results.boxes.conf.cpu().numpy())]


def hex_bgr(value: str) -> tuple[int, int, int]:
    if len(value) != 7 or value[0] != "#":
        raise ValueError("Use a six-digit kit colour, for example #e63946")
    try:
        r, g, b = (int(value[i:i+2], 16) for i in (1, 3, 5))
    except ValueError as exc:
        raise ValueError("Invalid kit colour") from exc
    return b, g, r


class KitClassifier:
    """Nearest LAB colour on torso pixels; abstain for weak/ambiguous agreement."""

    def __init__(self, own: str, opponent: str):
        bgr = np.uint8([[hex_bgr(own), hex_bgr(opponent)]])
        self.colours = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)[0].astype(float)
        if np.linalg.norm(self.colours[0]-self.colours[1]) < 28:
            raise ValueError("Kit colours are too similar. Choose distinct torso colours or use footage with distinguishable kits.")

    def assign(self, frame, observation: Observation):
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = observation.box
        bw, bh = x2-x1, y2-y1
        left, right = max(0, int(x1+.20*bw)), min(w, int(x2-.20*bw))
        top, bottom = max(0, int(y1+.18*bh)), min(h, int(y1+.52*bh))
        crop = frame[top:bottom, left:right]
        if crop.size < 12:
            return
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(float)
        # Remove likely grass and extreme shadows; neutral kits remain supported.
        grass = (hsv[:,:,0] >= 30) & (hsv[:,:,0] <= 95) & (hsv[:,:,1] > 65)
        keep = (~grass & (hsv[:,:,2] > 30)).reshape(-1)
        lab = lab[keep]
        if len(lab) < 2:
            return
        distances = np.linalg.norm(lab[:,None,:]-self.colours[None,:,:], axis=2)
        medians = np.median(distances, axis=0)
        best = int(np.argmin(medians)); other = 1-best
        vote = float(np.mean(np.argmin(distances, axis=1) == best))
        margin = float((medians[other]-medians[best])/max(medians[other], 1))
        if medians[best] > 90 or vote < .60 or margin < .18:
            return
        observation.team = ("own", "opponent")[best]
        observation.team_confidence = round(min(.5 if len(lab)<4 else 1., vote * margin), 3)


@dataclass
class Track:
    id: int
    team: str
    point: np.ndarray
    velocity: np.ndarray
    last_seen: float
    observations: int = 1


class Tracker:
    """Team-aware gated Hungarian association with constant-velocity prediction.

    Only measured observations are emitted. Missing tracks stay internal for a
    short reacquisition window and never become invented tactical observations.
    """
    def __init__(self, max_gap_s=1.2, max_speed_m_s=12.):
        self.tracks: dict[int, Track] = {}
        self.next_id = 1
        self.max_gap_s = max_gap_s
        self.max_speed = max_speed_m_s

    def reset(self):
        self.tracks.clear()

    def update(self, observations: list[Observation], time_s: float):
        self.tracks = {i: t for i, t in self.tracks.items() if time_s-t.last_seen <= self.max_gap_s}
        eligible = [o for o in observations if o.xy is not None and o.team != "unknown"]
        active = list(self.tracks.values())
        used = set()
        if active and eligible:
            cost = np.full((len(active), len(eligible)), 1e6)
            for i, track in enumerate(active):
                dt = max(time_s-track.last_seen, .001)
                prediction = track.point+track.velocity*min(dt, .5)
                for j, obs in enumerate(eligible):
                    if obs.team != track.team:
                        continue
                    distance = float(np.linalg.norm(np.array(obs.xy)-prediction))
                    if distance <= 1.5+self.max_speed*dt:
                        cost[i,j] = distance
            rows, cols = linear_sum_assignment(cost)
            for i,j in zip(rows,cols):
                if cost[i,j] >= 1e6:
                    continue
                t, o = active[i], eligible[j]
                dt = max(time_s-t.last_seen, .001)
                velocity = (np.array(o.xy)-t.point)/dt
                speed = np.linalg.norm(velocity)
                if speed > self.max_speed:
                    velocity *= self.max_speed/speed
                t.velocity = .5*t.velocity+.5*velocity
                t.point=np.array(o.xy);t.last_seen=time_s;t.observations+=1
                o.track_id=t.id;used.add(j)
        for j, o in enumerate(eligible):
            if j not in used:
                self.tracks[self.next_id] = Track(self.next_id, o.team, np.array(o.xy), np.zeros(2), time_s)
                o.track_id=self.next_id;self.next_id+=1
        return observations


class CameraRegistration:
    """Reference-frame optical flow with held-out validation and no drift chaining.

    Cuts/large changes invalidate projection. Users can supply new corner
    keyframes; automatic reacquisition works only while reference features survive.
    """
    def __init__(self, frame, corners, moving=True, world_points=None):
        self.reference = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        self.corners = np.float32(corners)
        self.initial_H = calibration(corners) if world_points is None else cv2.getPerspectiveTransform(np.float32(corners),np.float32(world_points))
        self.moving = moving
        mask = np.zeros(frame.shape[:2], np.uint8)
        # Landmarks may cover only the centre circle. Use the grass surface for
        # camera verification rather than limiting features to that small patch.
        hsv=cv2.cvtColor(frame,cv2.COLOR_BGR2HSV)
        mask=cv2.inRange(hsv,(25,30,25),(100,255,255))
        mask=cv2.dilate(mask,np.ones((11,11),np.uint8))
        self.points = cv2.goodFeaturesToTrack(self.reference, maxCorners=450, qualityLevel=.015, minDistance=9, mask=mask)
        self.orb=cv2.ORB_create(nfeatures=1800,scaleFactor=1.2,nlevels=8)
        self.keypoints,self.descriptors=self.orb.detectAndCompute(self.reference,mask)

    def _fit(self, src, dst, status, method):
        if len(src)<16:return None,status
        validation=np.arange(len(src))%4==0
        transform,inliers=cv2.findHomography(src[~validation],dst[~validation],cv2.RANSAC,2.5)
        if transform is None or inliers is None or not np.isfinite(transform).all():return None,status
        ratio=float(np.mean(inliers))
        error=float(np.median(np.linalg.norm(project(src[validation],transform)-dst[validation],axis=1)))
        mapped=project(self.corners,transform)
        area=abs(cv2.contourArea(mapped))/max(abs(cv2.contourArea(self.corners)),1)
        if ratio<.65 or error>3 or not .08<area<8 or not cv2.isContourConvex(mapped):return None,status
        movement=float(np.max(np.linalg.norm(mapped-self.corners,axis=1)))
        if not self.moving and movement>3:
            return None,{**status,'reason':'Camera moved in fixed-camera mode. Enable camera compensation or add a keyframe.'}
        try:H=self.initial_H @ np.linalg.inv(transform) if self.moving else self.initial_H
        except np.linalg.LinAlgError:return None,status
        if not np.isfinite(H).all():return None,status
        return H,{**status,'valid':True,'reason':'Reference features verified',
                  'inlier_ratio':round(ratio,3),'validation_error_px':round(error,3),
                  'movement_px':round(movement,2),'method':method}

    def update(self, frame):
        grey=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
        status={'valid':False,'reason':'Camera registration lost; add a calibration keyframe.',
                'inlier_ratio':0.,'validation_error_px':None}
        if self.points is not None and len(self.points)>=16:
            current,ok,_=cv2.calcOpticalFlowPyrLK(self.reference,grey,self.points,None,winSize=(31,31),maxLevel=4)
            if current is not None:
                back,reverse_ok,_=cv2.calcOpticalFlowPyrLK(grey,self.reference,current,None,winSize=(31,31),maxLevel=4)
                if back is not None:
                    keep=ok.reshape(-1).astype(bool)&reverse_ok.reshape(-1).astype(bool)
                    keep &= np.linalg.norm(back-self.points,axis=2).reshape(-1)<1.5
                    H,quality=self._fit(self.points[keep,0],current[keep,0],status,'optical_flow')
                    if H is not None or not self.moving and 'fixed-camera' in quality['reason']:return H,quality
        # Scale-invariant feature matching can reacquire the original view after
        # a zoom/brief interruption. Every match is still independently checked.
        if self.descriptors is not None:
            points,descriptors=self.orb.detectAndCompute(grey,None)
            if descriptors is not None:
                pairs=cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(self.descriptors,descriptors,k=2)
                good=[pair[0] for pair in pairs if len(pair)==2 and pair[0].distance<.7*pair[1].distance]
                if len(good)>=20:
                    src=np.float32([self.keypoints[m.queryIdx].pt for m in good])
                    dst=np.float32([points[m.trainIdx].pt for m in good])
                    return self._fit(src,dst,status,'feature_reacquisition')
        return None,status


def marker_observations(frame, H):
    """Explicit demo mode only: circle centres are ground-plane points."""
    positions,centres,_=detect(frame,H)
    observations=[]
    for source,team in (("red","own"),("blue","opponent")):
        for xy,pixel in zip(positions[source],centres[source]):
            u,v=(float(x) for x in pixel)
            observations.append(Observation([u-8,v-8,u+8,v+8],[u,v],1.,team,1.,xy.tolist()))
    return observations


def overhead_observations(frame, colours, H, tolerance=38):
    """Classical kit blobs for overhead footage; centres approximate the ground.

    This explicit mode is useful where a general side-view person model fails.
    Colour agreement is not a learned person confidence.
    """
    lab=cv2.cvtColor(frame,cv2.COLOR_BGR2LAB).astype(np.float32)
    distances=np.linalg.norm(lab[:,:,None,:]-colours[None,None,:,:],axis=3)
    result=[];height,width=frame.shape[:2]
    for idx,team in enumerate(("own","opponent")):
        mask=np.uint8((distances[:,:,idx]<tolerance)&((distances[:,:,1-idx]-distances[:,:,idx])>15))*255
        mask=cv2.morphologyEx(mask,cv2.MORPH_OPEN,np.ones((3,3),np.uint8))
        mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((5,5),np.uint8))
        contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        minimum=max(12,width*height*.000025);maximum=width*height*.005
        for contour in contours:
            area=cv2.contourArea(contour)
            if not minimum<=area<=maximum:continue
            x,y,w,h=cv2.boundingRect(contour)
            if not .25<=w/max(h,1)<=4:continue
            m=cv2.moments(contour)
            if not m['m00']:continue
            center=[m['m10']/m['m00'],m['m01']/m['m00']]
            xy=project([center],H)[0].tolist() if H is not None else None
            if xy is not None and not (0<=xy[0]<=105 and 0<=xy[1]<=68):continue
            result.append(Observation([x,y,x+w,y+h],center,.5,team,.5,xy))
    return result
