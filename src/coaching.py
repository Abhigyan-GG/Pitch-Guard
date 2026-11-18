"""Context-aware geometric signals, sustained events and practical review prompts."""
from __future__ import annotations

import numpy as np
from scipy.optimize import linear_sum_assignment

from .formations import anchors


GUIDANCE = {
    "role_drift": {
        "title": "A player has left the reference shape",
        "coach": "Check whether this was an intended run. If cover was lost, agree who fills the vacated role before the next attack.",
        "player": "Scan behind you before stepping out; tell the nearest teammate who is covering your space.",
        "drill": "Pause a positional game after a forward run and ask the nearest three players to restore cover."},
    "unit_gap": {
        "title": "Space has opened between units",
        "coach": "Review whether midfield and defence advanced together. Move the supporting unit earlier rather than asking one player to cover the whole gap.",
        "player": "Check the distance to the unit behind you; recover toward a teammate instead of chasing alone.",
        "drill": "Play a compact three-zone game; award a point for progressing while the units remain connected."},
    "defensive_gap": {
        "title": "A wide channel has opened in the back line",
        "coach": "Check the ball-side defender's pressure and the cover angle. Have the adjacent defenders shift together before the opponent can run through.",
        "player": "Stay connected with the adjacent defender and check the runner in the channel.",
        "drill": "Use a back-four versus front-three exercise with coordinated shifting and recovery runs."},
    "stretched_shape": {
        "title": "The outfield team is stretched",
        "coach": "Review the team's depth at this moment. Agree a reference for advancing and recovering together, especially after a turnover.",
        "player": "Look for the next support player before moving forward; avoid leaving a long unsupported gap.",
        "drill": "Use a reduced-length transition game and reward connected support after regaining the ball."},
    "support_isolation": {
        "title": "A player has little nearby support",
        "coach": "Review whether this is an intended wide outlet. If not, bring a supporting teammate closer and give the receiver two options.",
        "player": "Create an angle before the ball arrives; ask for nearby support when passing options are distant.",
        "drill": "Play a 3v2 support game where the receiver must have two different passing angles."},
    "shape_disruption": {
        "title": "Team shape changed abruptly",
        "coach": "Review the preceding seconds for a turnover, an intentional run or a tracking error. If unplanned, agree a shared reset cue.",
        "player": "On the reset cue, recover toward your unit and communicate who delays the opponent.",
        "drill": "Use a transition game with a shared recovery cue; replay the moment and compare the response."},
}


def analyse_shape(observations, formation, direction=1, possession="unknown", thresholds=None):
    limits = {"deviation_m": 8., "unit_gap_m": 27., "defensive_gap_m": 23.,
              "depth_m": 58., "isolation_m": 22., **(thresholds or {})}
    own = [o for o in observations if o.xy is not None and o.team == "own"]
    other = [o for o in observations if o.xy is not None and o.team == "opponent"]
    # Partial views can support local measurements, but need enough coverage for
    # a whole-team shape claim. More than 11 suggests team/detection ambiguity.
    valid = 8 <= len(own) <= 11 and 7 <= len(other) <= 11
    empty={"valid":False,"reason":"Need 8-11 own and 7-11 opponent observations for team-shape review.",
           "coverage":round(min(len(own),11)/11,3),"signals":[],"roles":[],"lanes":[],"metrics":{}}
    if not valid:
        # Do not infer a whole-team shape from a cropped view. A local isolation
        # measurement remains useful if several nearby own players are visible.
        if 3<=len(own)<=11:
            points=np.array([o.xy for o in own])
            d=np.linalg.norm(points[:,None,:]-points[None,:,:],axis=2)
            np.fill_diagonal(d,np.inf)
            signals=[]
            for o,nearest in zip(own,np.min(d,axis=1)):
                if nearest>limits['isolation_m']:
                    signals.append({'kind':'support_isolation','key':f'support_isolation:{o.track_id}',
                                    'track_ids':[o.track_id],'value':round(float(nearest),2),
                                    'threshold':limits['isolation_m'],'unit':'m','scope':'local_view'})
            return {**empty,'local_valid':True,'local_signals':signals,
                    'reason':'Partial view: only local support distances are assessed; teammates may be outside the image.'}
        return empty
    points=np.array([o.xy for o in own],float)
    reference=anchors(formation,direction).astype(float)
    # A different-coloured goalkeeper is often unassigned in real footage. With
    # ten or fewer players use outfield references and report partial coverage.
    offset=0 if len(own)==11 else 1
    reference=reference[offset:]
    # Possession is supplied by the analyst, never inferred from shape alone.
    if possession == "in":
        reference[:,0] = np.median(reference[:,0])+(reference[:,0]-np.median(reference[:,0]))*1.08+direction*5
        reference[:,1] = 34+(reference[:,1]-34)*1.08
    elif possession == "out":
        reference[:,0] = np.median(reference[:,0])+(reference[:,0]-np.median(reference[:,0]))*.90-direction*4
        reference[:,1] = 34+(reference[:,1]-34)*.90
    shift=np.median(points,axis=0)-np.median(reference,axis=0)
    cost=np.linalg.norm((points-shift)[:,None,:]-reference[None,:,:],axis=2)
    rows,cols=linear_sum_assignment(cost)
    roles=[];signals=[]
    for i,j in zip(rows,cols):
        deviation=float(cost[i,j]);role=int(j+offset);obs=own[i]
        target=(reference[j]+shift).tolist()
        roles.append({"track_id":obs.track_id,"role":role,"xy":obs.xy,
                      "target":target,"deviation_m":round(deviation,2)})
        if role and deviation>limits["deviation_m"]:
            signals.append({"kind":"role_drift","key":f"role_drift:{obs.track_id}","track_ids":[obs.track_id],
                            "value":round(deviation,2),"threshold":limits["deviation_m"],"unit":"m","role":role})
    outfield=[r for r in roles if r["role"]!=0]
    p=np.array([r["xy"] for r in outfield])
    width=float(np.ptp(p[:,1]));depth=float(np.ptp(p[:,0]))
    num_def=int(formation[0]);defenders=[r for r in outfield if r["role"]<=num_def]
    gap=0.
    if len(defenders)==num_def:
        defenders.sort(key=lambda r:r["xy"][1])
        gaps=np.diff([r["xy"][1] for r in defenders]);idx=int(np.argmax(gaps));gap=float(gaps[idx])
        if gap>limits["defensive_gap_m"]:
            pair=sorted([defenders[idx]["track_id"],defenders[idx+1]["track_id"]])
            signals.append({"kind":"defensive_gap","key":"defensive_gap:"+":".join(map(str,pair)),
                            "track_ids":pair,"value":round(gap,2),"threshold":limits["defensive_gap_m"],"unit":"m"})
    # Assign reference lines explicitly rather than clustering distorted actual X.
    grouped={}
    for r in outfield:
        line=float(anchors(formation,direction)[r["role"],0])
        grouped.setdefault(line,[]).append(r["xy"][0])
    # Only use units with at least two observations; a missing unit is not a gap.
    line_means=sorted(float(np.median(v)) for v in grouped.values() if len(v)>=2)
    unit_gap=float(max(np.diff(line_means),default=0))
    for kind,value,key in (("unit_gap",unit_gap,"unit_gap_m"),("stretched_shape",depth,"depth_m")):
        if value>limits[key]:
            signals.append({"kind":kind,"key":kind,"track_ids":[],"value":round(value,2),"threshold":limits[key],"unit":"m"})
    if len(p)>1:
        distances=np.linalg.norm(p[:,None,:]-p[None,:,:],axis=2)
        np.fill_diagonal(distances,np.inf)
        for idx,nearest in enumerate(np.min(distances,axis=1)):
            if nearest>limits["isolation_m"]:
                track_id=outfield[idx]["track_id"]
                signals.append({"kind":"support_isolation","key":f"support_isolation:{track_id}","track_ids":[track_id],
                                "value":round(float(nearest),2),"threshold":limits["isolation_m"],"unit":"m"})
    blue=np.array([o.xy for o in other]);lanes=[]
    for i,a in enumerate(outfield):
        for b in outfield[i+1:]:
            start=np.array(a["xy"]);v=np.array(b["xy"])-start;length=float(np.linalg.norm(v))
            if not 5<=length<=35:continue
            u=np.clip((blue-start)@v/(length*length),0,1)
            clearance=float(np.min(np.linalg.norm(blue-(start+u[:,None]*v),axis=1)))
            if clearance>2:
                lanes.append({"from":a["xy"],"to":b["xy"],"clearance_m":round(clearance,2)})
    return {"valid":True,"reason":"Geometric observations available; coach review required.",
            "coverage":round(len(own)/11,3),"signals":signals,"roles":roles,"lanes":lanes,
            "metrics":{"width_m":round(width,2),"depth_m":round(depth,2),"unit_gap_m":round(unit_gap,2),
                       "defensive_gap_m":round(gap,2),"mean_deviation_m":round(float(np.mean([r["deviation_m"] for r in outfield])),2)},
            "possession":possession,"partial_view":len(own)<11}


class EventEngine:
    """Time-based persistence per player/rule; invalid data ends an event."""
    def __init__(self,persistence_s=.8,max_sample_gap_s=1.):
        self.persistence=persistence_s;self.max_gap=max_sample_gap_s
        self.pending={};self.events=[];self.previous=None;self.last_time=None

    def update(self,time_s,state):
        if self.last_time is not None and time_s-self.last_time>self.max_gap:
            self.pending.clear();self.previous=None
        self.last_time=time_s
        signals=list(state["signals"]) if state["valid"] else list(state.get("local_signals",[]))
        if state["valid"] and self.previous:
            dt=time_s-self.previous[0]
            change=abs(state["metrics"]["mean_deviation_m"]-self.previous[1])
            if .05<=dt<=self.max_gap and change/dt>12:
                signals.append({"kind":"shape_disruption","key":"shape_disruption","track_ids":[],
                                "value":round(change/dt,2),"threshold":12,"unit":"m/s"})
        self.previous=(time_s,state["metrics"]["mean_deviation_m"]) if state["valid"] else None
        keys={s["key"] for s in signals}
        self.pending={k:v for k,v in self.pending.items() if k in keys}
        for signal in signals:
            key=signal["key"]
            if key not in self.pending:
                self.pending[key]={"start":time_s,"signal":signal,"event":None}
            candidate=self.pending[key]
            # Abrupt changes are review markers and have no sustained-duration claim.
            duration=0 if signal["kind"]=="shape_disruption" else self.persistence
            if candidate["event"] is None and time_s-candidate["start"]>=duration-1e-6:
                event={"id":f"event-{len(self.events)+1}","kind":signal["kind"],
                       "start_s":round(candidate["start"],3),"detected_s":round(time_s,3),"end_s":round(time_s,3),
                       "track_ids":signal["track_ids"],"peak_value":signal["value"],
                       "threshold":signal["threshold"],"unit":signal["unit"],
                       "evidence":"Measured spacing relative to a selected reference; intent is not known.",
                       "review":{"status":"unreviewed","notes":""},**GUIDANCE[signal["kind"]]}
                event['scope']=signal.get('scope','team_shape')
                if event['scope']=='local_view':
                    event['title']='A player is far from visible teammates'
                    event['evidence']='Local view only. Other support players may be off-screen; whole-team isolation is not established.'
                self.events.append(event);candidate["event"]=event
            if candidate["event"] is not None:
                event=candidate["event"];event["end_s"]=round(time_s,3)
                event["peak_value"]=max(event["peak_value"],signal["value"])
        return [v["event"]["id"] for v in self.pending.values() if v["event"] is not None]
