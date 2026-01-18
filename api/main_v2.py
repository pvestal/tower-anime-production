#!/usr/bin/env python3
"""
Tower Anime Production Service - Unified API (Modular Version)
Consolidates all anime production functionality into single service
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import logging

# Import modular components
from api.routers import auth, projects
from api.models.database import Base, engine

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Tower Anime Production API",
    description="Unified anime production service integrating professional workflows with personal creative tools",
    version="2.0.0"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://***REMOVED***:8328"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(projects.router)

# Health check endpoints
@app.get("/health")
async def simple_health_check():
    """Simple health check endpoint at root"""
    return {
        "status": "healthy",
        "service": "tower-anime-production",
        "version": "2.0.0",
        "architecture": "modular"
    }

@app.get("/api/anime/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "tower-anime-production",
        "version": "2.0.0"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8328)