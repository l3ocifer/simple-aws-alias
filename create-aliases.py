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
import requests
from dotenv import load_dotenv

class SimpleLoginAliasManager:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://app.simplelogin.io/api/"
        self.headers = {
            "Authentication": self.api_key,
            "Content-Type": "application/json"
        }

    def get_domain_id(self, domain: str) -> str:
        """Get domain ID from SimpleLogin"""
        try:
            response = requests.get(
                f"{self.base_url}custom_domains",
                headers=self.headers
            )
            
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, dict) and 'custom_domains' in data:
                    domains = data['custom_domains']
                else:
                    domains = data if isinstance(data, list) else []

                for d in domains:
                    if isinstance(d, dict):
                        domain_name = d.get('domain_name', '')
                        if domain_name.lower() == domain.lower():
                            return str(d.get('id'))
                return None
            return None
        except Exception as e:
            print_status(f"Error getting domain ID: {str(e)}", False)
            return None

    def get_mailboxes(self) -> list:
        """Get all mailboxes"""
        try:
            response = requests.get(
                f"{self.base_url}v2/mailboxes",
                headers=self.headers
            )
            if response.status_code == 200:
                return response.json().get('mailboxes', [])
            return []
        except Exception as e:
            print_status(f"Error getting mailboxes: {str(e)}", False)
            return []

    def get_aliases(self, page_id: int = 0) -> list:
        """Get existing aliases"""
        try:
            response = requests.get(
                f"{self.base_url}v2/aliases",
                params={"page_id": page_id},
                headers=self.headers
            )
            if response.status_code == 200:
                return response.json().get('aliases', [])
            return []
        except Exception as e:
            print_status(f"Error getting aliases: {str(e)}", False)
            return []

    def get_alias_options(self, domain: str = None) -> dict:
        """Get alias options including signed suffixes"""
        try:
            params = {}
            if domain:
                params['hostname'] = domain

            response = requests.get(
                f"{self.base_url}v5/alias/options",
                params=params,
                headers=self.headers
            )
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print_status(f"Error getting alias options: {str(e)}", False)
            return None

    def get_all_aliases(self) -> list:
        """Get all aliases with pagination"""
        all_aliases = []
        page_id = 0
        while True:
            aliases = self.get_aliases(page_id)
            if not aliases:
                break
            all_aliases.extend(aliases)
            page_id += 1
            if len(aliases) < 20:  # API returns max 20 per page
                break
        return all_aliases

    def get_or_create_mailbox(self, email: str) -> dict:
        """Get mailbox by email or create if doesn't exist"""
        try:
            # Check existing mailboxes
            mailboxes = self.get_mailboxes()
            for mailbox in mailboxes:
                if mailbox.get('email') == email:
                    return mailbox

            # Create new mailbox if not found
            response = requests.post(
                f"{self.base_url}v2/mailboxes",
                headers=self.headers,
                json={"email": email}
            )
            
            if response.status_code == 201:
                return response.json()
            else:
                print_status(f"Failed to create mailbox: {response.status_code}", False)
                print_status(f"Response: {response.text}", False)
                return None
        except Exception as e:
            print_status(f"Error managing mailbox: {str(e)}", False)
            return None

    def create_alias(self, domain: str, prefix: str) -> dict:
        """Create an alias for the given domain and prefix"""
        try:
            # Check if alias already exists using full list
            target_alias = f"{prefix}@{domain}"
            existing_aliases = self.get_all_aliases()
            for alias in existing_aliases:
                if alias.get('email') == target_alias:
                    print_status(f"Alias {target_alias} already exists", True)
                    return alias

            # Get alias options to get signed suffix
            options = self.get_alias_options(domain)
            if not options:
                print_status("Failed to get alias options", False)
                return None

            # Find the correct suffix for our domain
            suffix = None
            for s in options.get('suffixes', []):
                if s.get('is_custom') and s.get('suffix', '').endswith(f"@{domain}"):
                    suffix = s
                    break

            if not suffix:
                print_status(f"No valid suffix found for domain {domain}", False)
                return None

            # Get or create mailbox
            default_mailbox = None
            if os.getenv('DEFAULT_MAILBOX'):
                default_mailbox = self.get_or_create_mailbox(os.getenv('DEFAULT_MAILBOX'))
            
            if not default_mailbox:
                mailboxes = self.get_mailboxes()
                default_mailbox = next((m for m in mailboxes if m.get('default')), None)

            if not default_mailbox:
                print_status("No default mailbox found", False)
                return None

            response = requests.post(
                f"{self.base_url}v3/alias/custom/new",
                headers=self.headers,
                json={
                    "alias_prefix": prefix,
                    "signed_suffix": suffix['signed_suffix'],
                    "mailbox_ids": [default_mailbox['id']],
                    "note": f"Created via API for {domain}"
                }
            )
            
            if response.status_code == 201:
                return response.json()
            else:
                print_status(f"Failed to create alias: {response.status_code}", False)
                print_status(f"Response: {response.text}", False)
                return None
        except Exception as e:
            print_status(f"Error creating alias: {str(e)}", False)
            return None

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