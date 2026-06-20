from fastapi import FastAPI, HTTPException
from routers import bugs, test_cases, test_cycles
import jira_client as jira

app = FastAPI(
    title="QA AI Agent",
    description="AI-powered QA system: bug logging, test case generation, and test cycle management via Jira",
    version="1.0.0",
)

app.include_router(bugs.router)
app.include_router(test_cases.router)
app.include_router(test_cycles.router)


@app.get("/", tags=["Health"])
def health():
    return {"status": "ok", "message": "QA AI Agent is running"}


@app.get("/connect", tags=["Connection"])
def connect():
    """Test Jira Cloud connection and verify project access."""
    try:
        info = jira.test_connection()
        return info
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Jira connection failed: {str(e)}")


@app.get("/fields", tags=["Connection"])
def list_custom_fields():
    """List all Jira fields including custom ones (helps identify Quality Plus field IDs)."""
    try:
        fields = jira.get_custom_fields()
        custom = [f for f in fields if f.get("custom", False)]
        return {"total_custom_fields": len(custom), "fields": custom}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch fields: {str(e)}")
