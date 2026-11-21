"""Application entry point for the SEO audit API."""

from fastapi import FastAPI

from app.api import router


app = FastAPI(
    title="AI Marketing Intelligence Assistant",
    description="A rule-based website SEO audit API with optional AI recommendation wording.",
)
app.include_router(router)