"""
Instagram Comment-to-DM Automation Tool
Main FastAPI application entry point.
"""

import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from database import engine, Base
from routes import webhook, api, dashboard
from routes.auth_routes import router as auth_router
from routes.oauth import router as oauth_router

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-18s  %(levelname)-7s  %(message)s",
)

# Create FastAPI app
app = FastAPI(
    title="Instagram DM Automation",
    description="Automate Instagram comment replies and DMs based on keywords.",
    version="2.0.0",
)

# Add CORS for production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict to specific domains in production if needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include routers
app.include_router(auth_router)
app.include_router(oauth_router)
app.include_router(dashboard.router)
app.include_router(api.router)
app.include_router(webhook.router)


# Top-level health endpoint (in addition to /api/health)
@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok"}


@app.on_event("startup")
async def startup():
    Base.metadata.create_all(bind=engine)
    print("✅ Tables created in Supabase")
    logging.getLogger("main").info("Database tables ensured — app ready")

    logging.getLogger("main").info("Database tables ensured — app ready")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8888))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
