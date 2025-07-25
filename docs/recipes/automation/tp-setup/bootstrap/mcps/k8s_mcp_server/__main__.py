# Source: https://github.com/alexei-led/k8s-mcp-server
# License: MIT License
# Copyright (c) 2021 Alexei Ledenev
# Modified by Cloud Software Group, 2025

"""Main entry point for K8s MCP Server.

Running this module will start the K8s MCP Server.
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
logger = logging.getLogger("k8s-mcp-server")


def handle_interrupt(signum, frame):
    """Handle keyboard interrupt (Ctrl+C) gracefully."""
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    sys.exit(0)


async def wait_for_server_ready(max_wait_time: int = 30) -> bool:
    """Wait for server to be ready before accepting connections."""
    logger.info("Waiting for server initialization...")
    start_time = time.time()
    
    while time.time() - start_time < max_wait_time:
        try:
            # Import here to check if initialization is complete
            from .server import _is_initialized
            if _is_initialized.is_set():
                logger.info("Server initialization completed successfully")
                return True
        except Exception as e:
            logger.debug(f"Server not ready yet: {e}")
        
        await asyncio.sleep(0.5)
    
    logger.error(f"Server initialization timeout after {max_wait_time} seconds")
    return False


# Using FastMCP's built-in CLI handling
def main():
    """Run the K8s MCP Server."""
    # Set up signal handler for graceful shutdown
    signal.signal(signal.SIGINT, handle_interrupt)
    signal.signal(signal.SIGTERM, handle_interrupt)
    
    try:
        # Import here to avoid circular imports
        from .config import MCP_TRANSPORT, MCP_DEBUG, MCP_HOST, MCP_PORT
        from .server import mcp

        # Configure logging level
        if MCP_DEBUG:
            logging.getLogger().setLevel(logging.DEBUG)
            logger.setLevel(logging.DEBUG)
            logger.debug("Debug mode enabled")

        # Validate transport protocol and ensure proper typing
        if MCP_TRANSPORT not in ["stdio", "sse", "streamable-http"]:
            logger.error("Invalid transport protocol: %s. Using stdio instead.", MCP_TRANSPORT)
            transport = "stdio"
        else:
            transport = MCP_TRANSPORT

        # Add initialization delays based on transport type
        logger.info("Initializing K8s MCP Server...")
        
        # For streamable-http transport, add additional startup delay
        if transport == "streamable-http":
            logger.info("Using streamable-http transport, ensuring proper initialization...")
            logger.info(f"Server will listen on {MCP_HOST}:{MCP_PORT}")
            time.sleep(3)  # Increased delay for streamable-http
        else:
            time.sleep(1)

        # Start the server
        logger.info("Starting K8s MCP Server with %s transport", transport)
        logger.info("Server configuration: host=%s, port=%s, debug=%s", MCP_HOST, MCP_PORT, MCP_DEBUG)
        
        if transport == "streamable-http":
            logger.info("HTTP endpoint will be available at: http://%s:%s/mcp", MCP_HOST, MCP_PORT)
            # Enable more detailed logging for HTTP transport
            if MCP_DEBUG:
                import os
                os.environ["UVICORN_LOG_LEVEL"] = "debug"
        
        mcp.run(transport=transport)  # type: ignore
        
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Shutting down gracefully...")
        sys.exit(0)
    except Exception as e:
        logger.error("Failed to start K8s MCP Server: %s", str(e))
        logger.exception("Full traceback:")
        sys.exit(1)


if __name__ == "__main__":
    main()
