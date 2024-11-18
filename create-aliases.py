#!/usr/bin/env python3
"""
SimpleLogin Alias Creator

Dependencies:
- requests (>=2.31.0)
- python-dotenv (>=1.0.0)
- colorama (>=0.4.6)
"""

import sys
import os
import subprocess
import shutil
import atexit
from pathlib import Path

# Check for Unix-like environment
if os.name != 'posix':
    print("Error: This script requires a Unix-like environment (macOS, Linux, or WSL)")
    sys.exit(1)

def print_status(message: str, success: bool = True):
    """Print status message with color"""
    # Define here for use during venv setup
    if success:
        print(f"\033[92m{message}\033[0m")
    else:
        print(f"\033[91m{message}\033[0m")

def setup_venv():
    venv_path = Path("temp_venv")
    if venv_path.exists():
        shutil.rmtree(venv_path)
    
    print_status("Creating virtual environment...", True)
    subprocess.run([sys.executable, "-m", "venv", str(venv_path)], check=True)
    
    pip_path = venv_path / "bin" / "pip"
    python_path = venv_path / "bin" / "python"
    
    print_status("Installing dependencies...", True)
    subprocess.run([str(pip_path), "install", "-q", "requests", "python-dotenv", "colorama"], check=True)
    
    return python_path, venv_path

def cleanup_venv(venv_path):
    if venv_path.exists():
        print_status(f"Cleaning up virtual environment...", True)
        try:
            shutil.rmtree(venv_path)
        except Exception as e:
            print_status(f"Error cleaning up virtual environment: {str(e)}", False)

# Setup virtual environment and rerun script if needed
if not hasattr(sys, 'real_prefix') and not (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
    try:
        python_path, venv_path = setup_venv()
        atexit.register(cleanup_venv, venv_path)
        
        os.execv(str(python_path), [str(python_path), __file__] + sys.argv[1:])
    except Exception as e:
        print(f"Error setting up virtual environment: {str(e)}")
        sys.exit(1)

# Rest of the imports now that we're in the venv
from dotenv import load_dotenv
from domain_setup import SimpleLoginAliasManager, print_status

def get_alias_domains() -> list:
    """Get domains for alias creation from env var"""
    domains = []
    if os.getenv('ALIAS_DOMAINS'):
        domains = [d.strip() for d in os.getenv('ALIAS_DOMAINS').split(',')]
    return domains

def get_mailbox_prefixes() -> list:
    """Get mailbox prefixes from env var"""
    prefixes = []
    if os.getenv('MAILBOX_PREFIX'):
        prefixes = [p.strip() for p in os.getenv('MAILBOX_PREFIX').split(',')]
    return prefixes

def create_domain_aliases(domain: str, mailbox_prefixes: list, sl_manager: SimpleLoginAliasManager) -> bool:
    """Create aliases for all mailbox prefixes on the given domain"""
    success = True
    for prefix in mailbox_prefixes:
        print_status(f"Creating alias {prefix}@{domain}...", True)
        result = sl_manager.create_alias(domain, prefix)
        if result:
            print_status(f"Successfully created alias: {result['alias']}", True)
        else:
            print_status(f"Failed to create alias for {prefix}@{domain}", False)
            success = False
    return success

def main():
    load_dotenv()
    
    api_key = os.getenv('SIMPLE_LOGIN_API_KEY')
    if not api_key:
        print_status("Error: SimpleLogin API key is required", False)
        sys.exit(1)

    domains = get_alias_domains()
    if not domains:
        print_status("Error: No domains specified in DOMAIN_ALIAS env var", False)
        sys.exit(1)

    mailbox_prefixes = get_mailbox_prefixes()
    if not mailbox_prefixes:
        print_status("Error: No mailbox prefixes specified in MAILBOX_PREFIX env var", False)
        sys.exit(1)

    sl_manager = SimpleLoginAliasManager(api_key)
    
    for domain in domains:
        if not create_domain_aliases(domain, mailbox_prefixes, sl_manager):
            print_status(f"Failed to create all aliases for domain {domain}", False)

if __name__ == "__main__":
    main() 