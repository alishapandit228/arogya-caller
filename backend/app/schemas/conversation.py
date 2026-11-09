from datetime import date, time
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator


class CreateSession(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role_id: str = Field(min_length=1, max_length=50)


class Reply(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    message: str = Field(min_length=1, max_length=2000)


class ModelTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: Literal["consent", "refuse", "answer", "confirm", "correct", "cancel", "unclear"]
    fields: dict[str, StrictStr] = Field(default_factory=dict, max_length=4)
    question: str = Field(min_length=1, max_length=500)


class Collected(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    user_name: str | None = Field(default=None, min_length=1, max_length=100)
    reason_for_contact: str | None = Field(default=None, min_length=3, max_length=500)
    preferred_follow_up_time: str | None = Field(default=None, min_length=3, max_length=150)
    appointment_purpose: str | None = Field(default=None, min_length=3, max_length=500)
    preferred_date: date | None = None
    preferred_time: time | None = None

    @field_validator("preferred_date")
    @classmethod
    def future_date(cls, value):
        if value is not None and value < date.today():
            raise ValueError("Date must not be in the past")
        return value

    @field_validator("preferred_time")
    @classmethod
    def minute_precision(cls, value):
        if value and (value.tzinfo or value.second or value.microsecond):
            raise ValueError("Use local HH:MM time")
        return value

    @field_validator("user_name", "reason_for_contact", "preferred_follow_up_time", "appointment_purpose")
    @classmethod
    def meaningful(cls, value):
        if value and (value.lower() in {"unknown", "n/a", "none", "maybe", "sometime", "later", "unsure"} or any(ord(c) < 32 for c in value)):
            raise ValueError("Please supply a specific value")
        return value
