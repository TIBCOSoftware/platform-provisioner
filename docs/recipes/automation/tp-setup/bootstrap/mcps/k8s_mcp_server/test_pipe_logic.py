#!/usr/bin/env python3
"""Simple test to verify pipe command logic."""

import sys
import os

# Add the server directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tools import split_pipe_command, is_pipe_command
from cli_executor import inject_context_namespace

def test_pipe_logic():
    """Test the core pipe command logic."""
    test_commands = [
        "kubectl get pods | grep nginx",
        "kubectl get pods | grep Running | head -5",
        "kubectl get pods --all-namespaces | grep -v kube-system | wc -l",
        "kubectl get pods",  # Non-piped
        "",  # Empty
        "|",  # Just pipe
        "kubectl get pods |",  # Trailing pipe
        "| grep nginx",  # Leading pipe
    ]
    
    for original_command in test_commands:
        print(f"\n=== Testing: '{original_command}' ===")
        
        try:
            # Check if it's a pipe command
            is_piped = is_pipe_command(original_command)
            print(f"Is piped: {is_piped}")
            
            if is_piped:
                # Split the command
                commands = split_pipe_command(original_command)
                print(f"Split commands: {commands}")
                
                if not commands:
                    print("ERROR: No commands after split!")
                    continue
                
                # Process each command
                processed_commands = []
                for i, cmd in enumerate(commands):
                    if not cmd.strip():
                        print(f"WARNING: Empty command at position {i}")
                        continue
                    processed_cmd = inject_context_namespace(cmd.strip())
                    processed_commands.append(processed_cmd)
                    print(f"  {i}: '{cmd.strip()}' -> '{processed_cmd}'")
                
                if not processed_commands:
                    print("ERROR: No valid commands after processing!")
                    continue
                
                # Reconstruct
                full_piped_command = " | ".join(processed_commands)
                print(f"Reconstructed: '{full_piped_command}'")
            else:
                # Handle non-piped command
                if original_command.strip():
                    processed = inject_context_namespace(original_command)
                    print(f"Non-piped: '{original_command}' -> '{processed}'")
                else:
                    print("Empty command, skipping")
                    
        except Exception as e:
            print(f"ERROR: {e}")

if __name__ == "__main__":
    test_pipe_logic()
