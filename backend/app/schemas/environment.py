"""Explicit scene observations; OSM place categories do not imply crowd or noise."""
from typing import Literal
from pydantic import BaseModel, Field, StrictBool, model_validator
from app.schemas.common import GeoPoint, LocalNaiveDT

class EnvironmentCondition(BaseModel):
    signal: Literal["crowded", "noisy"]
    state: Literal["present", "absent"]

class EnvironmentObservation(BaseModel):
    feature: Literal["water", "forest", "park", "market"]
    location: GeoPoint
    radius_m: float = Field(gt=0, le=500)
    valid_from: LocalNaiveDT
    valid_until: LocalNaiveDT
    crowded: StrictBool | None = None
    noisy: StrictBool | None = None
    source: Literal["guardian_report", "field_observation", "synthetic_scenario"]

    @model_validator(mode="after")
    def finite_window(self):
        if self.valid_until <= self.valid_from:
            raise ValueError("environment observation needs a positive validity interval")
        if self.crowded is None and self.noisy is None:
            raise ValueError("environment observation has no observed signal")
        return self
