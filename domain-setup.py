#!/usr/bin/env python3
"""
SimpleLogin Domain Setup with AWS Route53 Integration

Dependencies:
- boto3 (>=1.26.0)
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
import time

# Check for Unix-like environment
if os.name != 'posix':
    print("Error: This script requires a Unix-like environment (macOS, Linux, or WSL)")
    sys.exit(1)

def print_status(message: str, success: bool = True):
    """Print status message with color"""
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
    subprocess.run([str(pip_path), "install", "-q", "boto3", "requests", "python-dotenv", "colorama"], check=True)
    
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
import boto3
import requests
from dotenv import load_dotenv
from colorama import Fore, Style

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
            
            print_status(f"\nAPI Response Status: {response.status_code}", True)
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    print_status("\nAPI Response:", True)
                    print_status(str(data), True)
                    
                    if isinstance(data, dict) and 'custom_domains' in data:
                        domains = data['custom_domains']
                    else:
                        domains = data if isinstance(data, list) else []

                    for d in domains:
                        if isinstance(d, dict):
                            domain_name = d.get('domain_name', '')
                            print_status(f"Found domain: {domain_name}", True)
                            if domain_name.lower() == domain.lower():
                                return str(d.get('id'))
                    
                    print_status(f"\nDomain {domain} not found in available domains", False)
                except ValueError as e:
                    print_status(f"Error parsing API response: {str(e)}", False)
                    return None
            else:
                print_status(f"API request failed: {response.status_code}", False)
                print_status(f"Response: {response.text}", False)
            return None
        except Exception as e:
            print_status(f"Error getting domain ID: {str(e)}", False)
            return None

class AWSRoute53Manager:
    def __init__(self):
        self.route53 = boto3.client('route53')
        self.TTL = 6  # Set TTL to 6 seconds

    def get_zone_id(self, domain: str) -> str:
        """Get Route53 zone ID for a given domain"""
        try:
            if not domain:
                return None
            response = self.route53.list_hosted_zones_by_name(DNSName=domain)
            for zone in response['HostedZones']:
                if zone['Name'].rstrip('.') == domain:
                    return zone['Id'].split('/')[2]
            return None
        except Exception as e:
            print_status(f"Error getting zone ID: {str(e)}", False)
            return None

    def get_record(self, zone_id: str, domain: str, record_type: str, name: str = None) -> dict:
        """Get existing record if it exists"""
        try:
            paginator = self.route53.get_paginator('list_resource_record_sets')
            target_name = name if name else domain
            
            for page in paginator.paginate(HostedZoneId=zone_id):
                for record in page['ResourceRecordSets']:
                    if record['Type'] == record_type and record['Name'].rstrip('.') == target_name:
                        return record
            return None
        except Exception as e:
            print_status(f"Error getting record: {str(e)}", False)
            return None

    def create_mx_records(self, domain: str) -> bool:
        """Create MX records for SimpleLogin"""
        zone_id = self.get_zone_id(domain)
        if not zone_id:
            return False

        try:
            existing = self.get_record(zone_id, domain, 'MX')
            new_records = [
                {'Value': '10 mx1.simplelogin.co.'},
                {'Value': '20 mx2.simplelogin.co.'}
            ]
            
            if existing and existing.get('ResourceRecords') == new_records:
                print_status("MX records already exist with correct values", True)
                return True

            self.route53.change_resource_record_sets(
                HostedZoneId=zone_id,
                ChangeBatch={
                    'Changes': [{
                        'Action': 'UPSERT',
                        'ResourceRecordSet': {
                            'Name': domain,
                            'Type': 'MX',
                            'TTL': self.TTL,
                            'ResourceRecords': new_records
                        }
                    }]
                }
            )
            return True
        except Exception as e:
            print_status(f"Error creating MX records: {str(e)}", False)
            return False

    def create_spf_record(self, domain: str) -> bool:
        """Create SPF record"""
        zone_id = self.get_zone_id(domain)
        if not zone_id:
            return False

        try:
            existing = self.get_record(zone_id, domain, 'TXT')
            new_value = '"v=spf1 include:simplelogin.co ~all"'
            
            if existing and any(r['Value'] == new_value for r in existing.get('ResourceRecords', [])):
                print_status("SPF record already exists with correct value", True)
                return True

            self.route53.change_resource_record_sets(
                HostedZoneId=zone_id,
                ChangeBatch={
                    'Changes': [{
                        'Action': 'UPSERT',
                        'ResourceRecordSet': {
                            'Name': domain,
                            'Type': 'TXT',
                            'TTL': self.TTL,
                            'ResourceRecords': [{'Value': new_value}]
                        }
                    }]
                }
            )
            return True
        except Exception as e:
            print_status(f"Error creating SPF record: {str(e)}", False)
            return False

    def create_dkim_records(self, domain: str) -> bool:
        """Create DKIM records"""
        zone_id = self.get_zone_id(domain)
        if not zone_id:
            return False

        try:
            changes = []
            for prefix in ['dkim', 'dkim02', 'dkim03']:
                name = f'{prefix}._domainkey.{domain}'
                existing = self.get_record(zone_id, domain, 'CNAME', name)
                new_value = f'{prefix}._domainkey.simplelogin.co.'
                
                if not existing or existing.get('ResourceRecords', [{}])[0].get('Value') != new_value:
                    changes.append({
                        'Action': 'UPSERT',
                        'ResourceRecordSet': {
                            'Name': name,
                            'Type': 'CNAME',
                            'TTL': self.TTL,
                            'ResourceRecords': [{'Value': new_value}]
                        }
                    })
                else:
                    print_status(f"DKIM record for {prefix} already exists with correct value", True)

            if changes:
                self.route53.change_resource_record_sets(
                    HostedZoneId=zone_id,
                    ChangeBatch={'Changes': changes}
                )
            return True
        except Exception as e:
            print_status(f"Error creating DKIM records: {str(e)}", False)
            return False

    def create_dmarc_record(self, domain: str) -> bool:
        """Create DMARC record"""
        zone_id = self.get_zone_id(domain)
        if not zone_id:
            return False

        try:
            name = f'_dmarc.{domain}'
            existing = self.get_record(zone_id, domain, 'TXT', name)
            new_value = '"v=DMARC1; p=quarantine; pct=100; adkim=s; aspf=s"'
            
            if existing and any(r['Value'] == new_value for r in existing.get('ResourceRecords', [])):
                print_status("DMARC record already exists with correct value", True)
                return True

            self.route53.change_resource_record_sets(
                HostedZoneId=zone_id,
                ChangeBatch={
                    'Changes': [{
                        'Action': 'UPSERT',
                        'ResourceRecordSet': {
                            'Name': name,
                            'Type': 'TXT',
                            'TTL': self.TTL,
                            'ResourceRecords': [{'Value': new_value}]
                        }
                    }]
                }
            )
            return True
        except Exception as e:
            print_status(f"Error creating DMARC record: {str(e)}", False)
            return False

def get_domains() -> list:
    """Get domains from env var, supports comma-separated list"""
    domains = []
    if os.getenv('CUSTOM_DOMAINS'):
        domains = [d.strip() for d in os.getenv('CUSTOM_DOMAINS').split(',')]
    return domains

def setup_domain(domain: str, sl_manager: SimpleLoginAliasManager, aws_manager: AWSRoute53Manager) -> bool:
    """Handle complete domain setup process with manual verification"""
    print_status(f"\nStarting setup for domain: {domain}")
    
    # Get domain ID first
    domain_id = sl_manager.get_domain_id(domain)
    if not domain_id:
        print_status(f"Domain {domain} not found in SimpleLogin", False)
        return False
    
    verification_url = f"https://app.simplelogin.io/dashboard/domains/{domain_id}/dns#dns-setup"
    
    # Check if domain exists in Route53
    zone_id = aws_manager.get_zone_id(domain)
    if not zone_id:
        print_status(f"Domain {domain} not found in Route53", False)
        return False
    
    # Step 1: MX Records
    print_status("\nSetting up MX records...", True)
    if not aws_manager.create_mx_records(domain):
        print_status("Failed to setup MX records", False)
        return False
    
    print_status("\nMX records created/updated. Please verify in SimpleLogin:", True)
    print_status(f"Visit: {verification_url}", True)
    input("Press Enter after verifying MX records...")
    
    # Step 2: SPF Record
    print_status("\nSetting up SPF record...", True)
    if not aws_manager.create_spf_record(domain):
        print_status("Failed to setup SPF record", False)
        return False
    
    print_status("\nSPF record created/updated. Please verify in SimpleLogin:", True)
    print_status(f"Visit: {verification_url}", True)
    input("Press Enter after verifying SPF record...")
    
    # Step 3: DKIM Records
    print_status("\nSetting up DKIM records...", True)
    if not aws_manager.create_dkim_records(domain):
        print_status("Failed to setup DKIM records", False)
        return False
    
    print_status("\nDKIM records created/updated. Please verify in SimpleLogin:", True)
    print_status(f"Visit: {verification_url}", True)
    input("Press Enter after verifying DKIM records...")
    
    # Step 4: DMARC Record
    print_status("\nSetting up DMARC record...", True)
    if not aws_manager.create_dmarc_record(domain):
        print_status("Failed to setup DMARC record", False)
        return False
    
    print_status("\nDMARC record created/updated. Please verify in SimpleLogin:", True)
    print_status(f"Visit: {verification_url}", True)
    input("Press Enter after verifying DMARC record...")
    
    print_status(f"\nSuccessfully setup domain: {domain}", True)
    return True

def main():
    load_dotenv()
    
    api_key = os.getenv('SIMPLE_LOGIN_API_KEY')
    if not api_key:
        print_status("Error: SimpleLogin API key is required", False)
        sys.exit(1)
    
    domains = get_domains()
    if not domains:
        print_status("Error: No domains specified in CUSTOM_DOMAINS env var", False)
        sys.exit(1)
    
    # Initialize managers
    sl_manager = SimpleLoginAliasManager(api_key)
    aws_manager = AWSRoute53Manager()
    
    # Process each domain
    for domain in domains:
        if not setup_domain(domain, sl_manager, aws_manager):
            print_status(f"Setup failed for domain {domain}", False)

if __name__ == "__main__":
    main()