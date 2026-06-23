from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Divami Jira
    jira_base_url: str = "https://divami.atlassian.net"
    jira_email: str
    jira_api_token: str
    jira_project_key: str = "IIRM"

    # Personal / second Jira instance (optional)
    jira2_base_url: Optional[str] = "https://prathiphalakandula.atlassian.net"
    jira2_email: Optional[str] = None
    jira2_api_token: Optional[str] = None

    # Groq API
    groq_api_key: str

    class Config:
        env_file = ".env"


settings = Settings()
