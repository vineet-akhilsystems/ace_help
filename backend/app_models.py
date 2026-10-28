from datetime import date as Date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Task(StrictModel):
    client: Literal['Augastam (New Product)'] = 'Augastam (New Product)'
    module: Literal['Augastam ai'] = 'Augastam ai'
    taskName: Literal['New Requirement'] = 'New Requirement'
    description: str = Field(min_length=1, max_length=500)
    start: str = Field(pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')
    end: str = Field(pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')
    ticket: str | None = Field(default=None, pattern=r'^ASPL-\d{5,8}$')
    matchReason: str | None = None
    evidence: str | None = Field(default=None, max_length=600)

    @model_validator(mode='after')
    def ticket_prefix(self):
        if self.ticket and not self.description.startswith(f'[{self.ticket}] '):
            raise ValueError('A selected ticket must prefix its task description.')
        return self


class DayPlan(StrictModel):
    date: Date
    workplace: Literal['Office', 'Home']
    totalHours: str = Field(pattern=r'^\d{2}:[0-5]\d$')
    tasks: list[Task] = Field(min_length=1, max_length=40)
    warnings: list[str] = Field(default_factory=list)
    activitySummary: str | None = None

    @model_validator(mode='after')
    def valid_day(self):
        from backend.app_rules import validate_day
        validate_day(self)
        return self


class PlanRequest(StrictModel):
    transcript: str = Field(default='', max_length=20000)
    date: Date


class RangeRequest(StrictModel):
    fromDate: Date
    toDate: Date
    notes: str = Field(default='', max_length=20000)
    perDay: dict[Date, str] = Field(default_factory=dict)

    @model_validator(mode='after')
    def check_range(self):
        if not 0 <= (self.toDate - self.fromDate).days <= 62:
            raise ValueError('Date range must be ordered and at most 63 calendar days.')
        return self


class Segment(StrictModel):
    source: str = Field(min_length=1, max_length=20000)
    description: str = Field(min_length=1, max_length=500)
    durationMinutes: int | None = Field(default=None, strict=True, ge=1, le=585)


class Segments(StrictModel):
    tasks: list[Segment] = Field(min_length=1, max_length=40)


class Ticket(StrictModel):
    ticket: str = Field(pattern=r'^ASPL-\d{5,8}$')
    description: str
    module: str = ''
    taskType: str = ''
    status: str = ''
