from __future__ import annotations
from pydantic import BaseModel
from enum import Enum


class BugPriority(str, Enum):
    HIGHEST = "Highest"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    LOWEST = "Lowest"


class BugCategory(str, Enum):
    FUNCTIONAL = "Functional"
    UI_UX = "UI/UX"
    PERFORMANCE = "Performance"
    SECURITY = "Security"
    DATA = "Data"
    INTEGRATION = "Integration"
    USABILITY = "Usability"
    ACCESSIBILITY = "Accessibility"
    OTHER = "Other"


class LogBugResponse(BaseModel):
    jira_key: str
    jira_url: str
    summary: str
    severity: str
    priority: str
    category: str
    assignee: str | None
    story_key: str | None
    attachment_uploaded: bool
