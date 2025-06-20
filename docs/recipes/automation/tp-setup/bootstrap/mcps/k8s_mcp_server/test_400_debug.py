#!/usr/bin/env python3
"""Test script to help debug 400 errors in K8s MCP Server."""

import json
import requests
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_mcp_server(host="localhost", port=8091):
    """Test the MCP server with various requests to trigger 400 errors."""
    
    base_url = f"http://{host}:{port}"
    
    # Test cases that might trigger 400 errors
    test_cases = [
        {
            "name": "Empty request",
            "url": f"{base_url}/mcp/",
            "method": "POST",
            "data": None,
            "headers": {"Content-Type": "application/json"}
        },
        {
            "name": "Invalid JSON",
            "url": f"{base_url}/mcp/",
            "method": "POST",
            "data": "invalid json",
            "headers": {"Content-Type": "application/json"}
        },
        {
            "name": "Empty JSON",
            "url": f"{base_url}/mcp/",
            "method": "POST",
            "data": json.dumps({}),
            "headers": {"Content-Type": "application/json"}
        },
        {
            "name": "Invalid MCP request",
            "url": f"{base_url}/mcp/",
            "method": "POST",
            "data": json.dumps({"invalid": "request"}),
            "headers": {"Content-Type": "application/json"}
        },
        {
            "name": "Missing jsonrpc version",
            "url": f"{base_url}/mcp/",
            "method": "POST",
            "data": json.dumps({"method": "tools/list", "id": 1}),
            "headers": {"Content-Type": "application/json"}
        },
        {
            "name": "Valid tools/list request",
            "url": f"{base_url}/mcp/",
            "method": "POST",
            "data": json.dumps({
                "jsonrpc": "2.0",
                "method": "tools/list",
                "id": 1
            }),
            "headers": {"Content-Type": "application/json"}
        },
        {
            "name": "Valid prompts/list request",
            "url": f"{base_url}/mcp/",
            "method": "POST",
            "data": json.dumps({
                "jsonrpc": "2.0",
                "method": "prompts/list",
                "id": 2
            }),
            "headers": {"Content-Type": "application/json"}
        }
    ]
    
    logger.info(f"Testing MCP server at {base_url}")
    
    for test_case in test_cases:
        logger.info(f"\n=== Testing: {test_case['name']} ===")
        
        try:
            response = requests.request(
                method=test_case['method'],
                url=test_case['url'],
                data=test_case['data'],
                headers=test_case['headers'],
                timeout=10
            )
            
            logger.info(f"Status Code: {response.status_code}")
            logger.info(f"Response Headers: {dict(response.headers)}")
            
            if response.status_code == 400:
                logger.error(f"🔴 400 ERROR DETECTED!")
                logger.error(f"Response Text: {response.text}")
            elif response.status_code == 200:
                logger.info(f"✅ Success")
                try:
                    response_json = response.json()
                    logger.debug(f"Response JSON: {json.dumps(response_json, indent=2)}")
                except:
                    logger.debug(f"Response Text: {response.text}")
            else:
                logger.warning(f"⚠️  Unexpected status: {response.status_code}")
                logger.warning(f"Response: {response.text}")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Request failed: {e}")
        except Exception as e:
            logger.error(f"❌ Unexpected error: {e}")

if __name__ == "__main__":
    import sys
    
    host = "localhost"
    port = 8091
    
    if len(sys.argv) > 1:
        host = sys.argv[1]
    if len(sys.argv) > 2:
        port = int(sys.argv[2])
    
    test_mcp_server(host, port)
