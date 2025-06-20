#!/usr/bin/env python3

#  Copyright (c) 2025. Cloud Software Group, Inc. All Rights Reserved. Confidential & Proprietary

"""Custom authentication middleware for K8s MCP Server."""

import logging
from typing import Optional

from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger('k8s-mcp-auth')


class BearerTokenMiddleware(BaseHTTPMiddleware):
    """Custom Bearer Token authentication middleware for K8s MCP Server."""
    
    def __init__(self, app: Starlette, expected_token: Optional[str] = None):
        super().__init__(app)
        self.expected_token = expected_token
        self.enabled = expected_token is not None and expected_token.strip() != ""
        
        if self.enabled:
            logger.info("Bearer Token authentication middleware enabled for K8s MCP Server")
        else:
            logger.info("Bearer Token authentication middleware disabled for K8s MCP Server")
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request and validate Bearer Token if required."""
        
        # Skip authentication for health checks and non-MCP endpoints
        if not self.enabled or request.url.path in ["/health", "/", "/docs"]:
            return await call_next(request)
        
        # For MCP endpoints, require authentication
        if request.url.path.startswith("/mcp"):
            auth_header = request.headers.get("authorization", "")
            
            if not auth_header:
                logger.warning("Missing Authorization header for K8s MCP request")
                return JSONResponse(
                    status_code=401,
                    content={"error": "Authorization header required", "code": "MISSING_AUTH"}
                )
            
            if not auth_header.lower().startswith("bearer "):
                logger.warning("Invalid Authorization header format for K8s MCP: %s", auth_header[:20])
                return JSONResponse(
                    status_code=401,
                    content={"error": "Bearer token required", "code": "INVALID_AUTH_FORMAT"}
                )
            
            token = auth_header[7:]  # Remove "Bearer " prefix
            
            if token != self.expected_token:
                logger.warning("Invalid Bearer token provided for K8s MCP")
                return JSONResponse(
                    status_code=403,
                    content={"error": "Invalid Bearer token", "code": "INVALID_TOKEN"}
                )
            
            logger.debug("Bearer token validated successfully for K8s MCP")
        
        return await call_next(request)
