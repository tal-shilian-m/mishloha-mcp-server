"""Authentication middleware for MCP server"""
import os
from typing import Optional
from fastapi import HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

def verify_auth_token(credentials: Optional[HTTPAuthorizationCredentials] = None) -> bool:
    """Verify the Bearer token against MCP_AUTH_TOKEN environment variable"""
    if not credentials:
        return False
    
    expected_token = os.getenv("MCP_AUTH_TOKEN")
    if not expected_token:
        raise HTTPException(status_code=500, detail="Server authentication not configured")
    
    return credentials.credentials == expected_token

async def auth_middleware(request: Request, call_next):
    """Middleware to check auth for all requests"""
    # Skip auth for health check endpoints
    if request.url.path in ["/health", "/", "/docs", "/openapi.json"]:
        response = await call_next(request)
        return response
    
    # Check Authorization header
    auth_header = request.headers.get("authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    
    token = auth_header.split(" ")[1]
    expected_token = os.getenv("MCP_AUTH_TOKEN")
    if not expected_token:
        raise HTTPException(status_code=500, detail="Server authentication not configured")
    
    if token != expected_token:
        raise HTTPException(status_code=401, detail="Invalid authentication token")
    
    response = await call_next(request)
    return response