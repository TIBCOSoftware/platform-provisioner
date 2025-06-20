#!/usr/bin/env python3

#  Copyright (c) 2025. Cloud Software Group, Inc. All Rights Reserved. Confidential & Proprietary

import os
import sys
import subprocess
import json
import urllib.request
import urllib.parse
import urllib.error
import logging
from http.client import IncompleteRead
from typing import Dict, Any, Optional

from .config import DEFAULT_VALUES, CASE_TO_MODULE
from .server_lifecycle import ensure_server_ready

logger = logging.getLogger('tibco-platform-provisioner-executor')

async def run_automation_task(case: str, params: Optional[Dict[str, Any]] = None) -> str:
    """Run an automation task by making an API call to the bootstrap server.

    Args:
        case: The automation case to run (e.g., page_env, case.k8s_create_dp)
        params: Optional parameters to pass to the automation task

    Returns:
        The output of the automation task as a string

    Raises:
        RuntimeError: If server is not ready or initialization failed
        urllib.error.URLError: If API connection fails
        Exception: For other automation errors
    """
    # Check if server is ready
    try:
        if not ensure_server_ready():
            return "Error: Server not ready for automation tasks"
    except RuntimeError as e:
        return f"Error: {str(e)}"

    # Start with default values
    request_params = DEFAULT_VALUES.copy()

    # Set the case
    request_params["case"] = case

    # Simplified special case handling, since provision tools now call the correct case directly
    delete_case_mapping = {
        "delete_bwce_app": "bwce",
        "delete_flogo_app": "flogo",
    }

    # Only keep delete-related special handling
    if case in delete_case_mapping:
        request_params["CAPABILITY"] = delete_case_mapping[case]
        request_params["case"] = "case.k8s_delete_app"

    # Add additional parameters
    if params:
        request_params.update(params)

    # Format parameters for URL
    query_params = urllib.parse.urlencode(request_params)

    # Local flask server URL (using port 3120 as seen in server.py)
    flask_url = f"https://automation.localhost.dataplanes.pro/run-gui-script?{query_params}"

    logger.info("Running automation task: %s", case)
    logger.info("API URL: %s", flask_url)

    # Retry mechanism for IncompleteRead errors
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            # Create request with timeout
            req = urllib.request.Request(flask_url)

            # Use urllib to make the HTTP request with timeout
            with urllib.request.urlopen(req, timeout=1800) as response:  # 30 minutes timeout
                # Check HTTP status
                if response.getcode() != 200:
                    error_msg = f"HTTP {response.getcode()}: Server returned error status"
                    logger.error(error_msg)
                    return error_msg

                # Read response data with chunked reading for better reliability
                response_data = b""
                chunk_size = 8192  # 8KB chunks
                
                try:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        response_data += chunk
                    
                    output = response_data.decode('utf-8', errors='replace')  # Handle encoding issues gracefully
                    
                except IncompleteRead as e:
                    # Handle partial data from IncompleteRead
                    logger.warning("IncompleteRead encountered, using partial data: %s", str(e))
                    partial_data = e.partial
                    if response_data:
                        response_data += partial_data
                    else:
                        response_data = partial_data
                    output = response_data.decode('utf-8', errors='replace')
                    
                except UnicodeDecodeError as e:
                    logger.error("Unicode decode error: %s", str(e))
                    # Try with different encoding as fallback
                    try:
                        output = response_data.decode('latin1', errors='replace')
                    except UnicodeDecodeError:
                        output = str(response_data)

                # Log the complete output
                logger.info("Automation task completed. Output length: %d characters", len(output))
                if len(output) > 1000:
                    logger.info("Output preview: %s...%s", output[:500], output[-500:])
                else:
                    logger.info("Complete output: %s", output)

                return output
                
        except IncompleteRead as e:
            retry_count += 1
            error_msg = f"IncompleteRead error on attempt {retry_count}/{max_retries}: {str(e)}"
            logger.warning(error_msg)
            
            if retry_count >= max_retries:
                # Last attempt failed, try to use partial data if available
                if hasattr(e, 'partial') and e.partial:
                    try:
                        output = e.partial.decode('utf-8', errors='replace')
                        logger.info("Using partial data from final attempt: %d characters", len(output))
                        return output
                    except UnicodeDecodeError:
                        return f"Error: {error_msg} - Could not decode partial data"
                return f"Error: {error_msg} after {max_retries} attempts"
            else:
                logger.info("Retrying request in 2 seconds...")
                import time
                time.sleep(2)  # Wait before retry
                continue
                
        except urllib.error.HTTPError as e:
            error_msg = f"HTTP Error {e.code}: {e.reason}"
            logger.error(error_msg)
            return error_msg
        except urllib.error.URLError as e:
            error_msg = f"Error connecting to automation server: {str(e)}"
            logger.error(error_msg)
            return error_msg
        except UnicodeDecodeError as e:
            error_msg = f"Error decoding server response: {str(e)}"
            logger.error(error_msg)
            return error_msg
        except Exception as e:
            # Catch any other exceptions not specifically handled above
            error_msg = f"Automation task failed: {str(e)}"
            logger.error(error_msg)
            return error_msg
    
    # Should not reach here, but just in case
    return "Error: Unexpected error in retry loop"

def run_bash_script(script_name: str, args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Run bash script and return the result (deprecated - kept for compatibility)"""
    from .config import AUTOMATION_PATH
    
    script_path = os.path.join(AUTOMATION_PATH, script_name)

    cmd = [script_path]
    if args:
        for k, v in args.items():
            cmd.extend([f"--{k}", str(v)])

    logger.info("Running command: %s", ' '.join(cmd))

    try:
        # Run script and capture output
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        logger.info("Command completed successfully: %s", result.stdout)

        # Try to parse output as JSON
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"success": True, "output": result.stdout, "message": "Command executed successfully"}

    except subprocess.CalledProcessError as e:
        logger.error("Command failed with error: %s", e.stderr)
        return {"success": False, "error": e.stderr, "message": "Command execution failed"}

async def execute_module(module_name: str, params: Optional[Dict[str, Any]] = None) -> str:
    """Execute a Python module directly as a fallback method.

    Args:
        module_name: Name of the module to run
        params: Optional dictionary of environment variables to set

    Returns:
        The output of the module execution as a string
    """
    # Check if server is ready
    try:
        if not ensure_server_ready():
            return "Error: Server not ready for module execution"
    except RuntimeError as e:
        return f"Error: {str(e)}"

    # Check if module exists
    if module_name not in CASE_TO_MODULE:
        return f"Error: Module {module_name} not found in the mapping"

    # Get the actual module path
    python_module = CASE_TO_MODULE[module_name]

    logger.info("Executing Python module: %s", python_module)

    try:
        # Set environment variables from DEFAULT_VALUES and params
        env = os.environ.copy()
        for key, value in DEFAULT_VALUES.items():
            env[key] = str(value)

        if params:
            for key, value in params.items():
                env[key] = str(value)

        # Run the Python module with timeout
        cmd = [sys.executable, "-u", "-m", python_module]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            env=env,
            timeout=1800  # 30 minutes timeout
        )
        logger.info("Module executed successfully")
        return result.stdout
    except subprocess.TimeoutExpired:
        error_msg = f"Module execution timeout after 30 minutes: {python_module}"
        logger.error(error_msg)
        return f"Error: {error_msg}"
    except subprocess.CalledProcessError as e:
        error_msg = f"Module execution failed with exit code {e.returncode}: {e.stderr}"
        logger.error(error_msg)
        return f"Error: {error_msg}"
    except FileNotFoundError as e:
        error_msg = f"Python executable or module not found: {str(e)}"
        logger.error(error_msg)
        return f"Error: {error_msg}"
