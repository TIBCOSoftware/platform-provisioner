#!/usr/bin/env python3
"""Test the MCP server with fixed pipe handling."""

import asyncio
import sys
import os

# Add the server directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the functions we want to test
from tools import split_pipe_command, is_pipe_command

def test_split_pipe_fixes():
    """Test the fixes to split_pipe_command."""
    print("=== Testing split_pipe_command fixes ===")
    
    test_cases = [
        "",                           # Empty string
        "   ",                       # Whitespace only
        "kubectl get pods",          # Single command
        "kubectl get pods | grep nginx",  # Simple pipe
        "|",                         # Just pipe character
        "kubectl get pods |",        # Trailing pipe
        "| grep nginx",             # Leading pipe
    ]
    
    for test_case in test_cases:
        print(f"\nTesting: '{test_case}'")
        try:
            is_piped = is_pipe_command(test_case)
            print(f"  is_pipe_command: {is_piped}")
            
            if is_piped:
                commands = split_pipe_command(test_case)
                print(f"  split_pipe_command: {commands}")
                
                # Test the new logic
                if not commands:
                    print("  Result: Empty command list (expected for edge cases)")
                else:
                    processed_commands = []
                    for i, cmd in enumerate(commands):
                        if not cmd.strip():
                            print(f"    Command {i}: Empty, skipping")
                            continue
                        processed_commands.append(cmd.strip())
                        print(f"    Command {i}: '{cmd.strip()}'")
                    
                    if processed_commands:
                        full_command = " | ".join(processed_commands)
                        print(f"  Reconstructed: '{full_command}'")
                    else:
                        print("  Result: No valid commands after processing")
                    
        except Exception as e:
            print(f"  ERROR: {e}")

if __name__ == "__main__":
    test_split_pipe_fixes()
