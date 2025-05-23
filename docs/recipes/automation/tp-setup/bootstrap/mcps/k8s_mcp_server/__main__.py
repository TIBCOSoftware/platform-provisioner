# Source: https://github.com/alexei-led/k8s-mcp-server
# License: MIT License
# Copyright (c) 2021 Alexei Ledenev
# Modified by Cloud Software Group, 2025

"""Main entry point for K8s MCP Server.

Running this module will start the K8s MCP Server.
"""

import logging
import signal
import sys

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


# Using FastMCP's built-in CLI handling
def main():
    """Run the K8s MCP Server."""
    # Set up signal handler for graceful shutdown
    signal.signal(signal.SIGINT, handle_interrupt)
    signal.signal(signal.SIGTERM, handle_interrupt)
    try:
        # Import here to avoid circular imports
        from .config import MCP_TRANSPORT
        from .server import mcp

        # Validate transport protocol
        if MCP_TRANSPORT not in ["stdio", "sse", "streamable-http"]:
            logger.error(f"Invalid transport protocol: {MCP_TRANSPORT}. Using stdio instead.")
            transport = "stdio"
        else:
            transport = MCP_TRANSPORT

        # Start the server
        logger.info(f"Starting K8s MCP Server with {transport} transport")
        mcp.run(transport=transport)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Shutting down gracefully...")
        sys.exit(0)


if __name__ == "__main__":
    main()
