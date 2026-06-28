from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator, model_validator


class ProjectBase(BaseModel):
    project_name: str | None = Field(None, description="Project display name")
    description: str | None = Field(None, description="Project description")
    start_date: date | None = Field(None, description="Project start date")
    end_date: date | None = Field(None, description="Project end date")
    status: str | None = Field(None, description="Project status")
    created_by: str | None = Field(None, description="Project creator")
    document_author: str | None = Field(
        None,
        description="Default author name shown in generated documents",
    )

    @field_validator(
        "project_name",
        "description",
        "status",
        "created_by",
        "document_author",
        mode="before",
    )
    @classmethod
    def strip_optional_text(cls, value):
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @model_validator(mode="after")
    def validate_date_range(self) -> "ProjectBase":
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must be greater than or equal to start_date")
        return self


class ProjectCreate(ProjectBase):
    project_id: str = Field(..., min_length=1, max_length=64)
    project_name: str = Field(..., min_length=1, max_length=255)

    @field_validator("project_id", mode="before")
    @classmethod
    def strip_project_id(cls, value):
        text = str(value or "").strip()
        if not text:
            raise ValueError("project_id is required")
        return text


class ProjectUpdate(ProjectBase):
    pass


class ProjectMetadata(BaseModel):
    project_id: str
    project_name: str
    description: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    status: str = "ACTIVE"
    created_by: str | None = None
    document_author: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
