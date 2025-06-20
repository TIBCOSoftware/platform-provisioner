#!/usr/bin/env python3
"""Health check script for TIBCO Platform Automation MCP Server.

This script can be used to verify that the MCP server is running correctly
and that all required components are available.
"""

import asyncio
import logging
import sys
import time
from typing import Dict, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("tibco-platform-mcp-health-check")


async def check_server_initialization() -> bool:
    """Check if server initialization completed successfully."""
    try:
        # Import here to avoid circular imports
        import mcp_server
        
        if not hasattr(mcp_server, '_is_initialized'):
            logger.warning("Server initialization state not available")
            return False
        
        if not mcp_server._is_initialized.is_set():
            logger.warning("Server initialization not completed")
            return False
        
        if not hasattr(mcp_server, '_server_status') or mcp_server._server_status is None:
            logger.warning("Server status not available")
            return False
        
        server_status = mcp_server._server_status
        if not server_status.get("server_ready", False):
            logger.error("Server not ready")
            return False
        
        logger.info("✓ Server initialization completed successfully")
        return True
        
    except ImportError as e:
        logger.error(f"✗ Cannot import server module: {e}")
        return False
    except Exception as e:
        logger.error(f"✗ Error checking server initialization: {e}")
        return False


async def check_automation_path() -> bool:
    """Check if automation path is accessible."""
    try:
        import os
        from mcp_server import PROJECT_ROOT, AUTOMATION_PATH
        
        if not os.path.exists(PROJECT_ROOT):
            logger.error(f"✗ Project root does not exist: {PROJECT_ROOT}")
            return False
        
        if not os.path.exists(AUTOMATION_PATH):
            logger.error(f"✗ Automation path does not exist: {AUTOMATION_PATH}")
            return False
        
        logger.info(f"✓ Project root accessible: {PROJECT_ROOT}")
        logger.info(f"✓ Automation path accessible: {AUTOMATION_PATH}")
        return True
        
    except Exception as e:
        logger.error(f"✗ Error checking automation path: {e}")
        return False


async def check_default_configuration() -> bool:
    """Check if default configuration is valid."""
    try:
        from mcp_server import DEFAULT_VALUES
        
        required_keys = [
            "TP_AUTO_ADMIN_URL",
            "CP_ADMIN_EMAIL", 
            "TP_AUTO_LOGIN_URL",
            "DP_HOST_PREFIX",
            "DP_USER_EMAIL",
            "TP_AUTO_K8S_DP_NAME"
        ]
        
        missing_keys = []
        for key in required_keys:
            if key not in DEFAULT_VALUES or not DEFAULT_VALUES[key]:
                missing_keys.append(key)
        
        if missing_keys:
            logger.error(f"✗ Missing required configuration keys: {missing_keys}")
            return False
        
        logger.info("✓ Default configuration is valid")
        return True
        
    except Exception as e:
        logger.error(f"✗ Error checking default configuration: {e}")
        return False


async def check_case_mappings() -> bool:
    """Check if case to module mappings are valid."""
    try:
        from mcp_server import CASE_TO_MODULE
        
        if not CASE_TO_MODULE:
            logger.error("✗ No case to module mappings found")
            return False
        
        essential_cases = [
            "page_env",
            "case.k8s_create_dp",
            "case.k8s_delete_dp"
        ]
        
        missing_cases = []
        for case in essential_cases:
            if case not in CASE_TO_MODULE:
                missing_cases.append(case)
        
        if missing_cases:
            logger.error(f"✗ Missing essential case mappings: {missing_cases}")
            return False
        
        logger.info(f"✓ Case mappings are valid ({len(CASE_TO_MODULE)} cases)")
        return True
        
    except Exception as e:
        logger.error(f"✗ Error checking case mappings: {e}")
        return False


async def run_health_check() -> bool:
    """Run comprehensive health check."""
    logger.info("Running TIBCO Platform Automation MCP Server health check...")
    
    checks = [
        ("Server Initialization", check_server_initialization()),
        ("Automation Path", check_automation_path()),
        ("Default Configuration", check_default_configuration()),
        ("Case Mappings", check_case_mappings())
    ]
    
    results = []
    for name, check_coro in checks:
        logger.info(f"Checking {name}...")
        try:
            result = await check_coro
            results.append((name, result))
        except Exception as e:
            logger.error(f"Error in {name} check: {e}")
            results.append((name, False))
    
    # Summary
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    logger.info(f"\nHealth Check Summary: {passed}/{total} checks passed")
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        logger.info(f"  {name}: {status}")
    
    if passed == total:
        logger.info("✓ All health checks passed - Server is ready")
        return True
    else:
        logger.error(f"✗ {total - passed} health check(s) failed")
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
