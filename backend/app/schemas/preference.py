"""Explicit scope for newly saved preferences; omitted scopes retain legacy behaviour."""

from typing import Literal

from pydantic import BaseModel, model_validator

MemoryScope = Literal["global", "course", "knowledge_point"]


class ScopedMemoryInput(BaseModel):
    scope: MemoryScope | None = None
    course: str = ""
    knowledge_point: str | None = None

    @model_validator(mode="after")
    def normalize_scope(self):
        if self.scope == "global":
            self.course = ""
            self.knowledge_point = None
        elif self.scope in ("course", "knowledge_point"):
            if not self.course.strip():
                raise ValueError("a course is required for this scope")
            self.course = self.course.strip()
            if self.scope == "course":
                self.knowledge_point = None
            elif not self.knowledge_point or not self.knowledge_point.strip():
                raise ValueError("a knowledge point is required for this scope")
            else:
                self.knowledge_point = self.knowledge_point.strip()
        return self
