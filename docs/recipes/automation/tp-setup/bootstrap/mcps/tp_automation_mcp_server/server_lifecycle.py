#!/usr/bin/env python3

#  Copyright (c) 2025. Cloud Software Group, Inc. All Rights Reserved. Confidential & Proprietary

import os
import sys
import threading
import logging
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional
from mcp.server.fastmcp import FastMCP

from .config import PROJECT_ROOT, AUTOMATION_PATH, DEFAULT_VALUES, CASE_TO_MODULE

logger = logging.getLogger('tibco-platform-provisioner-lifecycle')

# Global initialization state
_initialization_lock = threading.Lock()
_is_initialized = threading.Event()
_server_status: Optional[Dict[str, Any]] = None

def initialize_server_status() -> Dict[str, Any]:
    """Initialize server status and check system requirements."""
    logger.info("Initializing TIBCO Platform Automation server...")

    status = {
        "server_ready": True,
        "project_root": PROJECT_ROOT,
        "automation_path": AUTOMATION_PATH,
        "default_values": DEFAULT_VALUES.copy(),
        "available_cases": CASE_TO_MODULE.copy(),
        "initialization_time": 0,
        "errors": []
    }

    # Use simple time instead of asyncio loop time
    import time
    status["initialization_time"] = time.time()

    # Verify automation path exists
    if not os.path.exists(AUTOMATION_PATH):
        error_msg = f"Automation path does not exist: {AUTOMATION_PATH}"
        logger.warning(error_msg)
        status["server_ready"] = False
        status["errors"].append(error_msg)

    # Verify Python executable
    if not os.path.exists(sys.executable):
        error_msg = f"Python executable not found: {sys.executable}"
        logger.warning(error_msg)
        status["server_ready"] = False
        status["errors"].append(error_msg)

    return status

def _ensure_server_status():
    """Ensure server status is initialized."""
    global _server_status
    
    if _server_status is None:
        with _initialization_lock:
            if _server_status is None:
                _server_status = initialize_server_status()
                _is_initialized.set()
                logger.info("Server status initialized successfully")
    
    return _server_status

def ensure_server_ready() -> bool:
    """Ensure server is ready, initializing if necessary."""
    status = _ensure_server_status()
    return status is not None and status.get("server_ready", False)

def get_server_status() -> Optional[Dict[str, Any]]:
    """Get the current server status."""
    return _ensure_server_status()

def is_server_initialized() -> bool:
    """Check if server is initialized."""
    _ensure_server_status()  # Ensure initialization
    return _is_initialized.is_set()

@asynccontextmanager
async def lifespan(_app: FastMCP):
    """Minimal lifespan manager for FastMCP streamable-http compatibility."""
    logger.info("TIBCO Platform Automation MCP Server starting up...")
    yield
    logger.info("TIBCO Platform Automation MCP Server shutting down...")

# Pre-initialize server status to avoid streamable-http issues
logger.info("Pre-initializing TIBCO Platform Automation server...")
_ensure_server_status()
logger.info("TIBCO Platform Automation server pre-initialization completed")
