from pydantic import BaseModel, Field, model_validator


class DurationFields(BaseModel):
    preferred_minutes: int | None = Field(default=None, ge=1, le=240)
    max_minutes: int | None = Field(default=None, ge=1, le=240)

    @model_validator(mode="after")
    def consistent_duration(self):
        if self.preferred_minutes and self.max_minutes and self.preferred_minutes > self.max_minutes:
            raise ValueError("首选时长不能超过时长上限")
        return self
