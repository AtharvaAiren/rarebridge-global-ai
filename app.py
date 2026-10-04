"""Vercel entrypoint: the real API and compiled frontend share one origin."""

from rarebridge.api.app import app

# Vercel promotes this frontend to its CDN. API routes retain precedence.
# The build command creates frontend/dist before deployment.
app.frontend("/", directory="frontend/dist", fallback="index.html", check_dir=False)
