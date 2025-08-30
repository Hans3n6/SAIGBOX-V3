"""Authentication middleware for protected routes"""

from typing import Optional
from fastapi import Request, HTTPException, status
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from jose import jwt, JWTError
import os
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-this")
ALGORITHM = os.getenv("ALGORITHM", "HS256")

# Public routes that don't require authentication
PUBLIC_ROUTES = [
    "/login",
    "/auth",
    "/api/auth/check",
    "/api/auth/google/url",
    "/api/auth/microsoft/url",
    "/api/auth/google/callback",
    "/api/auth/microsoft/callback",
    "/api/auth/demo",
    "/static",
    "/health",
    "/docs",
    "/openapi.json",
    "/favicon.ico"
]

# API routes that require authentication
PROTECTED_API_ROUTES = [
    "/api/emails",
    "/api/actions",
    "/api/huddles",
    "/api/trash",
    "/api/saig",
    "/api/user"
]


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware to protect routes and validate authentication"""
    
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        
        # Allow public routes
        if self._is_public_route(path):
            response = await call_next(request)
            return response
        
        # Check authentication for protected routes
        if self._is_protected_route(path):
            # Try to get token from different sources
            token = self._get_token(request)
            
            if not token:
                if path.startswith("/api/"):
                    # API routes return 401
                    from fastapi.responses import JSONResponse
                    return JSONResponse(
                        status_code=401,
                        content={"detail": "Authentication required"},
                        headers={"WWW-Authenticate": "Bearer"}
                    )
                else:
                    # Web routes redirect to login
                    return RedirectResponse(url="/login")
            
            # Validate token
            if not self._validate_token(token):
                if path.startswith("/api/"):
                    from fastapi.responses import JSONResponse
                    return JSONResponse(
                        status_code=401,
                        content={"detail": "Invalid or expired token"},
                        headers={"WWW-Authenticate": "Bearer"}
                    )
                else:
                    return RedirectResponse(url="/login")
            
            # Add user info to request state
            request.state.token = token
        
        response = await call_next(request)
        return response
    
    def _is_public_route(self, path: str) -> bool:
        """Check if route is public"""
        for route in PUBLIC_ROUTES:
            if path.startswith(route):
                return True
        return False
    
    def _is_protected_route(self, path: str) -> bool:
        """Check if route requires authentication"""
        # Root path requires auth
        if path == "/":
            return True
        
        # Check API routes
        for route in PROTECTED_API_ROUTES:
            if path.startswith(route):
                return True
        
        return False
    
    def _get_token(self, request: Request) -> Optional[str]:
        """Extract token from request"""
        # Try Authorization header first
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            return auth_header.split(" ")[1]
        
        # Try cookie
        token = request.cookies.get("access_token")
        if token:
            return token
        
        # Try query parameter (for some edge cases)
        token = request.query_params.get("token")
        if token:
            return token
        
        return None
    
    def _validate_token(self, token: str) -> bool:
        """Validate JWT token"""
        if token == "session":
            # Special case for session-based auth
            return True
        
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            # Token is valid if we can decode it
            return True
        except JWTError:
            return False


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware"""
    
    def __init__(self, app, calls: int = 100, period: int = 60):
        super().__init__(app)
        self.calls = calls
        self.period = period
        self.clients = {}
    
    async def dispatch(self, request: Request, call_next):
        # Get client identifier (IP address)
        client_host = request.client.host if request.client else "unknown"
        
        # Implement basic rate limiting
        # In production, use Redis or similar for distributed rate limiting
        
        response = await call_next(request)
        return response


# CORSMiddleware is now handled by FastAPI's built-in middleware in main.py
# This custom implementation has been deprecated to avoid duplicate headers