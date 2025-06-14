#!/usr/bin/env python3

#  Copyright (c) 2025. Cloud Software Group, Inc. All Rights Reserved. Confidential & Proprietary

"""Main entry point for TIBCO Platform MCP Server.

Running this module will start the TIBCO Platform MCP Server.
"""

import asyncio
import logging
import signal
import sys
import time

# Configure logging before importing server
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger("tibco-platform-mcp-server")


def handle_interrupt(signum, _frame):
    """Handle keyboard interrupt (Ctrl+C) gracefully."""
    logger.info("Received signal %s, shutting down gracefully...", signum)
    sys.exit(0)


async def wait_for_server_ready(max_wait_time: int = 30) -> bool:
    """Wait for server to be ready before accepting connections."""
    logger.info("Waiting for server initialization...")
    start_time = time.time()
    
    while time.time() - start_time < max_wait_time:
        try:
            # Import here to check if initialization is complete
            from .server_lifecycle import is_server_initialized
            if is_server_initialized():
                logger.info("Server initialization completed successfully")
                return True
        except ImportError as e:
            logger.debug("Server not ready yet: %s", str(e))
        
        await asyncio.sleep(0.5)
    
    logger.error("Server initialization timeout after %s seconds", max_wait_time)
    return False


# Using FastMCP's built-in CLI handling
def main():
    """Run the TIBCO Platform MCP Server."""
    # Set up signal handler for graceful shutdown
    signal.signal(signal.SIGINT, handle_interrupt)
    signal.signal(signal.SIGTERM, handle_interrupt)
    
    try:
        # Import here to avoid circular imports
        from .config import MCP_TRANSPORT, MCP_SERVER_HOST, MCP_SERVER_PORT, MCP_HTTP_BEARER_TOKEN, MCP_DEBUG
        from .mcp_server import mcp

        # Configure logging level based on debug configuration
        if MCP_DEBUG:
            logging.getLogger().setLevel(logging.DEBUG)
            logger.setLevel(logging.DEBUG)
            logger.debug("Debug mode enabled")

        # Validate transport protocol and ensure proper typing
        if MCP_TRANSPORT not in ["stdio", "sse", "streamable-http"]:
            logger.error("Invalid transport protocol: %s. Using streamable-http instead.", MCP_TRANSPORT)
            transport = "streamable-http"
        else:
            transport = MCP_TRANSPORT

        # Add initialization delays based on transport type
        logger.info("Initializing TIBCO Platform MCP Server...")
        
        # For streamable-http transport, add additional startup delay
        if transport == "streamable-http":
            logger.info("Using streamable-http transport, ensuring proper initialization...")
            logger.info("Server will listen on %s:%s", MCP_SERVER_HOST, MCP_SERVER_PORT)
            time.sleep(3)  # Increased delay for streamable-http
        else:
            time.sleep(1)

        # Start the server
        logger.info("Starting TIBCO Platform MCP Server with %s transport", transport)
        logger.info("Server configuration: host=%s, port=%s, bearer_token=%s, debug=%s", 
                   MCP_SERVER_HOST, MCP_SERVER_PORT, "Set" if MCP_HTTP_BEARER_TOKEN else "Not Set", MCP_DEBUG)
        
        if transport == "streamable-http":
            logger.info("HTTP endpoint will be available at: http://%s:%s/mcp", MCP_SERVER_HOST, MCP_SERVER_PORT)
            # Enable more detailed logging for HTTP transport
            if MCP_DEBUG:
                import os
                os.environ["UVICORN_LOG_LEVEL"] = "debug"
        
        mcp.run(transport=transport)  # type: ignore
        
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Shutting down gracefully...")
        sys.exit(0)
    except ImportError as e:
        logger.error("Failed to import required modules: %s", str(e))
        logger.exception("Full traceback:")
        sys.exit(1)
    except Exception as e:
        logger.error("Failed to start TIBCO Platform MCP Server: %s", str(e))
        logger.exception("Full traceback:")
        sys.exit(1)


if __name__ == "__main__":
    main()
