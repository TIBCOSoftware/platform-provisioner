#!/usr/bin/env python3
"""
Test script to validate the CLI executor piped command handling logic.
This script will test various scenarios to identify potential issues.
"""

import asyncio
import logging
import sys
import os

# Add the server directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tools import split_pipe_command, is_pipe_command
from cli_executor import inject_context_namespace, execute_command

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_pipe_command_parsing():
    """Test the pipe command parsing logic."""
    print("=== Testing Pipe Command Parsing ===")
    
    test_cases = [
        # Simple pipe
        "kubectl get pods | grep nginx",
        # Multiple pipes
        "kubectl get pods | grep Running | head -5",
        # Complex pipe with quotes
        'kubectl get pods -o jsonpath="{.items[*].metadata.name}" | tr " " "\\n" | sort',
        # Pipe with options
        "kubectl get pods --all-namespaces | grep -v kube-system",
    ]
    
    for test_case in test_cases:
        print(f"\nTesting: {test_case}")
        print(f"Is pipe: {is_pipe_command(test_case)}")
        if is_pipe_command(test_case):
            commands = split_pipe_command(test_case)
            print(f"Split commands: {commands}")
            
            # Test the reconstruction logic similar to CLI executor
            first_command = inject_context_namespace(commands[0])
            command_list = [first_command]
            if len(commands) > 1:
                command_list.extend(commands[1:])
            full_piped_command = " | ".join(command_list)
            print(f"Reconstructed: {full_piped_command}")

async def test_simple_commands():
    """Test execution of simple commands to see if they work."""
    print("\n=== Testing Simple Commands ===")
    
    simple_commands = [
        "kubectl version --client",
        "kubectl cluster-info --request-timeout=5s",
    ]
    
    for cmd in simple_commands:
        print(f"\nTesting execution: {cmd}")
        try:
            result = await execute_command(cmd, timeout=10)
            print(f"Success: {result.success}")
            print(f"Return code: {result.return_code}")
            if result.stdout:
                print(f"Stdout (first 200 chars): {result.stdout[:200]}")
        except Exception as e:
            print(f"Error: {e}")

async def test_pipe_commands():
    """Test execution of pipe commands to see if they work."""
    print("\n=== Testing Pipe Commands ===")
    
    pipe_commands = [
        "kubectl version --client | head -3",
        "kubectl cluster-info --request-timeout=5s | grep -i 'kubernetes'",
    ]
    
    for cmd in pipe_commands:
        print(f"\nTesting pipe execution: {cmd}")
        try:
            result = await execute_command(cmd, timeout=10)
            print(f"Success: {result.success}")
            print(f"Return code: {result.return_code}")
            if result.stdout:
                print(f"Stdout (first 200 chars): {result.stdout[:200]}")
        except Exception as e:
            print(f"Error: {e}")

async def main():
    """Run all tests."""
    print("Starting CLI Executor Testing")
    print("=" * 50)
    
    await test_pipe_command_parsing()
    await test_simple_commands()
    await test_pipe_commands()
    
    print("\n" + "=" * 50)
    print("Testing complete")

if __name__ == "__main__":
    asyncio.run(main())
