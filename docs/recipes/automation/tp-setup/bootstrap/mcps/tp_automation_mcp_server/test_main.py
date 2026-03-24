#!/usr/bin/env python3

#
# Copyright 2025 Cloud Software Group, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

"""Test script for TIBCO Platform MCP Server main module."""

import sys
import os
import logging

# Add the current directory to Python path for local imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("tp-mcp-test")

def test_imports():
    """Test that all required modules can be imported."""
    try:
        logger.info("Testing module imports...")
        
        # Test config import
        from config import MCP_TRANSPORT, MCP_SERVER_HOST, MCP_SERVER_PORT
        logger.info("✓ Config imported successfully")
        logger.info("  Transport: %s", MCP_TRANSPORT)
        logger.info("  Host: %s", MCP_SERVER_HOST)
        logger.info("  Port: %s", MCP_SERVER_PORT)
        
        # Test server lifecycle import
        from server_lifecycle import is_server_initialized
        logger.info("✓ Server lifecycle imported successfully")
        
        # Test mcp_server import
        from mcp_server import mcp
        logger.info("✓ MCP server imported successfully")
        
        # Test main module import
        from __main__ import main
        logger.info("✓ Main module imported successfully")
        
        logger.info("All imports successful!")
        return True
        
    except ImportError as e:
        logger.error("Import failed: %s", str(e))
        return False
    except Exception as e:
        logger.error("Unexpected error during import: %s", str(e))
        return False

def test_server_status():
    """Test server status functionality."""
    try:
        from server_lifecycle import get_server_status
        status = get_server_status()
        logger.info("✓ Server status retrieved: %s", status)
        return True
    except Exception as e:
        logger.error("Server status test failed: %s", str(e))
        return False

if __name__ == "__main__":
    logger.info("Starting TIBCO Platform MCP Server tests...")
    
    success = True
    
    # Test imports
    if not test_imports():
        success = False
    
    # Test server status
    if not test_server_status():
        success = False
    
    if success:
        logger.info("All tests passed! 🎉")
        logger.info("You can now run the server with: python -m tp_automation_mcp_server")
        sys.exit(0)
    else:
        logger.error("Some tests failed! ❌")
        sys.exit(1)
