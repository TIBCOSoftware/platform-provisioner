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

"""Health check script for TIBCO Platform MCP Server."""

import requests
import json
import sys
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("tp-mcp-health")

def check_server_health(host="localhost", port=8090):
    """Check if the TIBCO Platform MCP Server is running and healthy."""
    
    url = f"http://{host}:{port}/mcp"
    
    try:
        logger.info("Checking server health at %s", url)
        
        # Try to connect to the MCP endpoint
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            logger.info("✓ Server is running and accessible")
            logger.info("  Status Code: %d", response.status_code)
            logger.info("  Content Type: %s", response.headers.get('content-type', 'N/A'))
            return True
        else:
            logger.warning("Server responded with status code: %d", response.status_code)
            return False
            
    except requests.exceptions.ConnectionError:
        logger.error("❌ Cannot connect to server - server may not be running")
        return False
    except requests.exceptions.Timeout:
        logger.error("❌ Connection timeout - server may be overloaded")
        return False
    except Exception as e:
        logger.error("❌ Unexpected error: %s", str(e))
        return False

def main():
    """Main health check function."""
    
    logger.info("TIBCO Platform MCP Server Health Check")
    logger.info("=" * 50)
    
    # Check default configuration
    if check_server_health():
        logger.info("🎉 Health check passed!")
        logger.info("Server is ready to accept MCP connections")
        sys.exit(0)
    else:
        logger.error("💥 Health check failed!")
        logger.error("Please check if the server is running:")
        logger.error("  python -m tp_automation_mcp_server")
        sys.exit(1)

if __name__ == "__main__":
    main()
