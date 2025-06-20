#!/usr/bin/env python3
"""Health check script for K8s MCP Server.

This script can be used to verify that the MCP server is running correctly
and that all required CLI tools are available.
"""

import asyncio
import logging
import sys
from typing import Dict, List

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("k8s-mcp-health-check")


async def check_cli_tool_availability() -> Dict[str, bool]:
    """Check if all required CLI tools are available."""
    from .cli_executor import check_cli_installed
    from .config import SUPPORTED_CLI_TOOLS
    
    results = {}
    for tool in SUPPORTED_CLI_TOOLS:
        try:
            is_available = await check_cli_installed(tool)
            results[tool] = is_available
            logger.info(f"{tool}: {'✓ Available' if is_available else '✗ Not found'}")
        except Exception as e:
            results[tool] = False
            logger.error(f"{tool}: ✗ Error checking availability: {e}")
    
    return results


async def check_server_initialization() -> bool:
    """Check if server initialization completed successfully."""
    try:
        from .server import _is_initialized, get_cli_status
        
        if not _is_initialized.is_set():
            logger.warning("Server initialization not completed")
            return False
        
        cli_status = get_cli_status()
        required_tools = ["kubectl"]  # kubectl is required
        
        for tool in required_tools:
            if not cli_status.get(tool, False):
                logger.error(f"Required tool {tool} is not available")
                return False
        
        logger.info("✓ Server initialization completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"✗ Error checking server initialization: {e}")
        return False


async def run_health_check() -> bool:
    """Run comprehensive health check."""
    logger.info("Running K8s MCP Server health check...")
    
    # Check CLI tools
    cli_results = await check_cli_tool_availability()
    
    # Check server initialization
    server_ok = await check_server_initialization()
    
    # Summary
    required_tools = ["kubectl"]
    all_required_available = all(cli_results.get(tool, False) for tool in required_tools)
    
    if all_required_available and server_ok:
        logger.info("✓ Health check passed - Server is ready")
        return True
    else:
        logger.error("✗ Health check failed")
        if not all_required_available:
            missing = [tool for tool in required_tools if not cli_results.get(tool, False)]
            logger.error(f"Missing required tools: {missing}")
        if not server_ok:
            logger.error("Server initialization issues detected")
        return False


async def main():
    """Main health check entry point."""
    try:
        success = await run_health_check()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"Health check failed with exception: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
