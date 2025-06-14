#!/usr/bin/env python3

#  Copyright (c) 2025. Cloud Software Group, Inc. All Rights Reserved. Confidential & Proprietary

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
        logger.error("  python -m tp_mcp_server")
        sys.exit(1)

if __name__ == "__main__":
    main()
