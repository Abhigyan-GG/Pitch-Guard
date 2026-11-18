"""Validated public inputs shared by the API and processing pipeline."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .formations import PROFILES
from .pitchguard import calibration
from .vision import KitClassifier


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class AdviceRequest(StrictModel):
    opponent: str = "4-4-2"
    current: str = "4-3-3"
    objective: Literal["balanced", "keep_ball", "protect_lead", "chase_goal"] = "balanced"
    squad: dict[str, float] = Field(default_factory=dict)

    @field_validator("opponent", "current")
    @classmethod
    def known_formation(cls, value):
        if value not in PROFILES:
            raise ValueError("Choose a supported formation")
        return value

    @field_validator("squad")
    @classmethod
    def valid_ratings(cls, value):
        allowed={"passing","stamina","wingers","strikers","centre_backs"}
        if set(value)-allowed or any(not 1<=v<=5 for v in value.values()):
            raise ValueError("Use named squad ratings from 1 to 5")
        return value


class CalibrationKeyframe(StrictModel):
    time_s: float = Field(ge=0)
    corners: list[list[float]]
    world_points: list[list[float]] | None = None

    @field_validator("corners")
    @classmethod
    def valid_corners(cls, value):
        calibration(value)
        return value


class PossessionSegment(StrictModel):
    start_s: float = Field(ge=0)
    end_s: float = Field(gt=0)
    possession: Literal["in","out","unknown"]

    @model_validator(mode="after")
    def ordered(self):
        if self.end_s<=self.start_s:raise ValueError("Possession segment end must follow start")
        return self


class Thresholds(StrictModel):
    deviation_m: float = Field(default=8, ge=3, le=30)
    unit_gap_m: float = Field(default=27, ge=10, le=50)
    defensive_gap_m: float = Field(default=23, ge=10, le=40)
    depth_m: float = Field(default=58, ge=30, le=95)
    isolation_m: float = Field(default=22, ge=10, le=45)
    persistence_s: float = Field(default=.8, ge=.2, le=5)


class AnalysisConfig(StrictModel):
    formation: str = "4-3-3"
    direction: Literal[-1, 1] = 1
    detector: Literal["players", "overhead", "markers"] = "players"
    own_colour: str = "#e63946"
    opponent_colour: str = "#2764e7"
    confidence: float = Field(default=.3, ge=.1, le=.9)
    sample_fps: float = Field(default=5, ge=1, le=10)
    start_s: float = Field(default=0, ge=0)
    end_s: float | None = Field(default=None, gt=0)
    corners: list[list[float]]
    world_points: list[list[float]] | None = None
    overhead_tolerance: float = Field(default=38, ge=15, le=75)
    compensate_camera: bool = True
    keyframes: list[CalibrationKeyframe] = Field(default_factory=list, max_length=100)
    possession: Literal["in", "out", "unknown"] = "unknown"
    possession_segments: list[PossessionSegment] = Field(default_factory=list, max_length=500)
    thresholds: Thresholds = Field(default_factory=Thresholds)

    @field_validator("formation")
    @classmethod
    def known_formation(cls,value):
        if value not in PROFILES:raise ValueError("Choose a supported formation")
        return value

    @field_validator("corners")
    @classmethod
    def valid_corners(cls,value):
        calibration(value)
        return value

    @model_validator(mode="after")
    def coherent(self):
        KitClassifier(self.own_colour,self.opponent_colour)
        if self.world_points is not None:
            calibration(self.world_points)
        for keyframe in self.keyframes:
            if keyframe.world_points is not None:calibration(keyframe.world_points)
        if self.end_s is not None and self.end_s<=self.start_s:
            raise ValueError("End time must follow start time")
        times=[k.time_s for k in self.keyframes]
        if times!=sorted(set(times)) or any(t<self.start_s or (self.end_s is not None and t>=self.end_s) for t in times):
            raise ValueError("Calibration keyframes must be ordered, unique and inside the analysis interval")
        segments=sorted(self.possession_segments,key=lambda s:s.start_s)
        if any(a.end_s>b.start_s for a,b in zip(segments,segments[1:])):
            raise ValueError("Possession segments must not overlap")
        return self


class StartRequest(StrictModel):
    upload_id: str
    config: AnalysisConfig


class ReviewRequest(StrictModel):
    status: Literal["confirmed", "dismissed", "uncertain", "unreviewed"]
    notes: str = Field(default="", max_length=3000)
    reviewer: str = Field(default="", max_length=120)
