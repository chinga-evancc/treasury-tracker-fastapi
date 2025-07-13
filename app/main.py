from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
import uvicorn
import os

from .database import engine, Base
from .routers import auth, investments
from .models import *  # Import all models to ensure they're registered

# Create database tables
Base.metadata.create_all(bind=engine)

# Create FastAPI app
app = FastAPI(
    title="Treasury Investment Tracker API",
    description="A comprehensive API for managing treasury note and bill investments",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual frontend domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/v1")
app.include_router(investments.router, prefix="/api/v1")

# Global exception handlers
@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
    return JSONResponse(
        status_code=500,
        content={"detail": "Database error occurred", "error_code": "database_error"}
    )

@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc), "error_code": "validation_error"}
    )

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "Treasury Investment Tracker API"}

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "Treasury Investment Tracker API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }

# API info endpoint
@app.get("/api/v1/info")
async def api_info():
    """API information endpoint."""
    return {
        "name": "Treasury Investment Tracker API",
        "version": "1.0.0",
        "description": "API for managing treasury investments in Malawi Kwacha",
        "features": [
            "User authentication and authorization",
            "Treasury note and bill management",
            "Automatic payment schedule generation",
            "Portfolio tracking and analytics",
            "Payment status management"
        ],
        "endpoints": {
            "authentication": "/api/v1/auth",
            "investments": "/api/v1/investments",
            "documentation": "/docs"
        }
    }

if __name__ == "__main__":
    # Run the application
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info"
    )

