"""Human-authored review labels stored separately from machine predictions."""
from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from .schemas import StrictModel


EventKind = Literal['role_drift','unit_gap','defensive_gap','stretched_shape','support_isolation','shape_disruption']


class ReviewedPeriod(StrictModel):
    start_s: float = Field(ge=0)
    end_s: float = Field(gt=0)

    @model_validator(mode='after')
    def ordered(self):
        if self.end_s<=self.start_s:raise ValueError('Period end must follow its start')
        return self


class ManualEvent(ReviewedPeriod):
    id: str = Field(min_length=1,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
    kind: EventKind
    judgement: Literal['issue','intended','uncertain'] = 'issue'
    notes: str = Field(default='',max_length=3000)


class AnnotationRequest(StrictModel):
    expected_revision: int = Field(default=0,ge=0)
    clip_id: str = Field(min_length=1,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
    reviewer: str = Field(default='',max_length=120)
    reviewer_role: Literal['coach','analyst','player'] = 'coach'
    reviewed_periods: list[ReviewedPeriod] = Field(default_factory=list,max_length=1000)
    manual_events: list[ManualEvent] = Field(default_factory=list,max_length=2000)
    attested: bool = False

    @model_validator(mode='after')
    def consistent(self):
        periods=sorted(self.reviewed_periods,key=lambda p:p.start_s)
        if any(a.end_s>b.start_s for a,b in zip(periods,periods[1:])):
            raise ValueError('Reviewed periods must not overlap')
        ids=[e.id for e in self.manual_events]
        if len(set(ids))!=len(ids):raise ValueError('Manual event IDs must be unique')
        if self.attested:
            if not self.reviewer.strip() or not periods:
                raise ValueError('Add your reviewer name and reviewed periods before confirming the review')
            def covered(e):return any(p.start_s<=e.start_s and e.end_s<=p.end_s for p in periods)
            if any(e.judgement=='issue' and not covered(e) for e in self.manual_events):
                raise ValueError('Every confirmed issue must lie within a reviewed period')
            if any(e.judgement=='uncertain' and any(e.start_s<p.end_s and e.end_s>p.start_s for p in periods) for e in self.manual_events):
                raise ValueError('Resolve uncertain events or exclude their periods before confirming the review')
        return self


def new_annotations(job_id,clip_id):
    return {'revision':0,'clip_id':clip_id,'reviewer':'','reviewer_role':'coach',
            'reviewed_periods':[],'manual_events':[],'attested':False,
            'job_id':job_id,'annotation_context':'Human review with access to machine predictions'}


def validate_bounds(request, start_s, end_s):
    for item in [*request.reviewed_periods,*request.manual_events]:
        if item.start_s<start_s or item.end_s>end_s:
            raise ValueError('Human labels must lie within the analysed interval')


def export_labels(annotations,input_sha256):
    """Include only explicitly human-entered issues, never automatic candidates."""
    return {'schema_version':1,'clip_id':annotations['clip_id'],'job_id':annotations['job_id'],
            'input_sha256':input_sha256,'annotation_version':f"human-review-{annotations['revision']}",
            'reviewer':annotations['reviewer'],'reviewer_role':annotations['reviewer_role'],
            'annotation_context':annotations['annotation_context'],
            'events_reviewed':bool(annotations['attested'] and annotations['reviewer_role']=='coach'),
            'reviewed_intervals':[[p['start_s'],p['end_s']] for p in annotations['reviewed_periods']],
            'events':[{k:e[k] for k in ['kind','start_s','end_s','notes']} for e in annotations['manual_events'] if e['judgement']=='issue'],
            'review_decisions':annotations['manual_events'],'frames':[],
            'scope':'Event labels only; no player positions or independent calibration labels supplied.'}
