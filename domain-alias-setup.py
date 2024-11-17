#!/usr/bin/env python3
"""
SimpleLogin Alias Creator with AWS Route53 Integration

Dependencies:
- boto3 (>=1.26.0)
- requests (>=2.31.0)
- python-dotenv (>=1.0.0)
- colorama (>=0.4.6)

Install with: pip install boto3 requests python-dotenv colorama
"""

import argparse
import boto3
import requests
import json
import sys
import os
from typing import Dict, Optional
from dotenv import load_dotenv
from colorama import init, Fore, Style

# Initialize colorama for cross-platform colored output
init()

def print_status(message: str, success: bool = True):
    color = Fore.GREEN if success else Fore.RED
    print(f"{color}{message}{Style.RESET_ALL}")

class SimpleLoginAliasManager:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://app.simplelogin.io/api/"
        self.headers = {
            "Authentication": api_key,
            "Content-Type": "application/json"
        }
        
    def verify_domain(self, domain: str) -> bool:
        endpoint = f"{self.base_url}domains"
        payload = {
            "domain": domain,
        }
        
        response = requests.post(endpoint, headers=self.headers, json=payload)
        if response.status_code == 201:
            return True
        else:
            print(f"Error verifying domain: {response.text}")
            return False
        
    def create_alias(self, domain: str, mailbox: str) -> Optional[Dict]:
        endpoint = f"{self.base_url}v2/alias/custom/new"
        payload = {
            "alias_prefix": mailbox,
            "signed_suffix": domain,
            "mailbox_ids": [],  # Uses default mailbox
            "note": "Created via automation script"
        }
        
        response = requests.post(endpoint, headers=self.headers, json=payload)
        if response.status_code == 201:
            return response.json()
        else:
            print(f"Error creating alias: {response.text}")
            return None

    def get_verification_code(self, domain: str) -> Optional[str]:
        endpoint = f"{self.base_url}domains/verification-code"
        payload = {"domain": domain}
        
        response = requests.post(endpoint, headers=self.headers, json=payload)
        if response.status_code == 200:
            return response.json().get('verification_code')
        else:
            print(f"Error getting verification code: {response.text}")
            return None

    def verify_domain_setup(self, domain: str, step: str) -> bool:
        endpoint = f"{self.base_url}domains/{domain}/verify/{step}"
        response = requests.get(endpoint, headers=self.headers)
        if response.status_code == 200:
            verified = response.json().get('verified', False)
            print_status(f"{step.upper()} verification {'successful' if verified else 'failed'}", verified)
            return verified
        print_status(f"Error checking {step} verification: {response.text}", False)
        return False

class AWSRoute53Manager:
    def __init__(self):
        self.route53 = boto3.client('route53')
        
    def get_zone_id(self, domain: str) -> Optional[str]:
        try:
            zones = self.route53.list_hosted_zones()
            for zone in zones['HostedZones']:
                # Remove trailing dot from zone name
                zone_name = zone['Name'].rstrip('.')
                if zone_name == domain:
                    return zone['Id'].replace('/hostedzone/', '')
            return None
        except Exception as e:
            print(f"Error getting zone ID: {str(e)}")
            return None

    def create_verification_record(self, domain: str, verification_code: str) -> bool:
        zone_id = self.get_zone_id(domain)
        if not zone_id:
            return False
            
        try:
            self.route53.change_resource_record_sets(
                HostedZoneId=zone_id,
                ChangeBatch={
                    'Changes': [
                        {
                            'Action': 'UPSERT',
                            'ResourceRecordSet': {
                                'Name': domain,
                                'Type': 'TXT',
                                'TTL': 3600,
                                'ResourceRecords': [
                                    {'Value': f'"{verification_code}"'}
                                ]
                            }
                        }
                    ]
                }
            )
            return True
        except Exception as e:
            print(f"Error creating verification record: {str(e)}")
            return False

    def create_mx_records(self, domain: str) -> bool:
        zone_id = self.get_zone_id(domain)
        if not zone_id:
            return False
            
        try:
            self.route53.change_resource_record_sets(
                HostedZoneId=zone_id,
                ChangeBatch={
                    'Changes': [
                        {
                            'Action': 'UPSERT',
                            'ResourceRecordSet': {
                                'Name': domain,
                                'Type': 'MX',
                                'TTL': 3600,
                                'ResourceRecords': [
                                    {'Value': '10 mx1.simplelogin.co.'},
                                    {'Value': '20 mx2.simplelogin.co.'}
                                ]
                            }
                        }
                    ]
                }
            )
            return True
        except Exception as e:
            print(f"Error creating MX records: {str(e)}")
            return False

    def create_spf_record(self, domain: str) -> bool:
        zone_id = self.get_zone_id(domain)
        if not zone_id:
            return False
            
        try:
            self.route53.change_resource_record_sets(
                HostedZoneId=zone_id,
                ChangeBatch={
                    'Changes': [
                        {
                            'Action': 'UPSERT',
                            'ResourceRecordSet': {
                                'Name': domain,
                                'Type': 'TXT',
                                'TTL': 3600,
                                'ResourceRecords': [
                                    {'Value': '"v=spf1 include:simplelogin.co ~all"'}
                                ]
                            }
                        }
                    ]
                }
            )
            return True
        except Exception as e:
            print(f"Error creating SPF record: {str(e)}")
            return False

    def create_dkim_records(self, domain: str) -> bool:
        zone_id = self.get_zone_id(domain)
        if not zone_id:
            return False
            
        try:
            self.route53.change_resource_record_sets(
                HostedZoneId=zone_id,
                ChangeBatch={
                    'Changes': [
                        {
                            'Action': 'UPSERT',
                            'ResourceRecordSet': {
                                'Name': f'dkim._domainkey.{domain}',
                                'Type': 'CNAME',
                                'TTL': 3600,
                                'ResourceRecords': [
                                    {'Value': 'dkim._domainkey.simplelogin.co.'}
                                ]
                            }
                        },
                        {
                            'Action': 'UPSERT',
                            'ResourceRecordSet': {
                                'Name': f'dkim02._domainkey.{domain}',
                                'Type': 'CNAME',
                                'TTL': 3600,
                                'ResourceRecords': [
                                    {'Value': 'dkim02._domainkey.simplelogin.co.'}
                                ]
                            }
                        },
                        {
                            'Action': 'UPSERT',
                            'ResourceRecordSet': {
                                'Name': f'dkim03._domainkey.{domain}',
                                'Type': 'CNAME',
                                'TTL': 3600,
                                'ResourceRecords': [
                                    {'Value': 'dkim03._domainkey.simplelogin.co.'}
                                ]
                            }
                        }
                    ]
                }
            )
            return True
        except Exception as e:
            print(f"Error creating DKIM records: {str(e)}")
            return False

    def create_dmarc_record(self, domain: str) -> bool:
        zone_id = self.get_zone_id(domain)
        if not zone_id:
            return False
            
        try:
            self.route53.change_resource_record_sets(
                HostedZoneId=zone_id,
                ChangeBatch={
                    'Changes': [
                        {
                            'Action': 'UPSERT',
                            'ResourceRecordSet': {
                                'Name': f'_dmarc.{domain}',
                                'Type': 'TXT',
                                'TTL': 3600,
                                'ResourceRecords': [
                                    {'Value': '"v=DMARC1; p=quarantine; pct=100; adkim=s; aspf=s"'}
                                ]
                            }
                        }
                    ]
                }
            )
            return True
        except Exception as e:
            print(f"Error creating DMARC record: {str(e)}")
            return False

    def create_dns_record(self, zone_id: str, record_set: dict) -> bool:
        try:
            self.route53.change_resource_record_sets(
                HostedZoneId=zone_id,
                ChangeBatch={'Changes': [{'Action': 'UPSERT', 'ResourceRecordSet': record_set}]}
            )
            return True
        except Exception as e:
            print_status(f"Error creating DNS record: {str(e)}", False)
            return False

def get_domains() -> list:
    domains = []
    if os.getenv('DOMAINS'):
        domains = [d.strip() for d in os.getenv('DOMAINS').split(',')]
    return domains

def get_mailbox_prefixes() -> list:
    """Get mailbox prefixes from env var, supports comma-separated list"""
    prefixes = []
    if os.getenv('MAILBOX_PREFIX'):
        prefixes = [p.strip() for p in os.getenv('MAILBOX_PREFIX').split(',')]
    return prefixes

def wait_for_verification(sl_manager: SimpleLoginAliasManager, domain: str, step: str, max_attempts: int = 10) -> bool:
    import time
    attempts = 0
    while attempts < max_attempts:
        if sl_manager.verify_domain_setup(domain, step):
            return True
        print_status(f"Waiting for {step} verification (attempt {attempts + 1}/{max_attempts})...", True)
        time.sleep(30)
        attempts += 1
    print_status(f"Maximum verification attempts reached for {step}", False)
    return False

def setup_domain(domain: str, sl_manager: SimpleLoginAliasManager, aws_manager: AWSRoute53Manager) -> bool:
    """Handle complete domain setup process"""
    print_status(f"\nStarting setup for domain: {domain}")
    
    # Get verification code
    print_status("Getting verification code...", True)
    verification_code = sl_manager.get_verification_code(domain)
    if not verification_code:
        return False
    
    # Create all required DNS records
    dns_setup_steps = [
        ('verification', lambda: aws_manager.create_verification_record(domain, verification_code)),
        ('MX', lambda: aws_manager.create_mx_records(domain)),
        ('SPF', lambda: aws_manager.create_spf_record(domain)),
        ('DKIM', lambda: aws_manager.create_dkim_records(domain)),
        ('DMARC', lambda: aws_manager.create_dmarc_record(domain))
    ]
    
    for step_name, setup_func in dns_setup_steps:
        print_status(f"Creating {step_name} record(s)...", True)
        if not setup_func():
            print_status(f"Failed to create {step_name} record(s)", False)
            return False
        
        if step_name != 'DMARC':  # DMARC doesn't have verification
            if not wait_for_verification(sl_manager, domain, step_name.lower()):
                print_status(f"{step_name} verification failed", False)
                return False
    
    return True

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
    
    parser = argparse.ArgumentParser(description='Create SimpleLogin alias with DNS setup')
    parser.add_argument('--api-key', help='SimpleLogin API key')
    parser.add_argument('--domain', help='Domain name')
    parser.add_argument('--mailbox', help='Mailbox prefix')
    
    args = parser.parse_args()
    
    # Get API key from args or env
    api_key = args.api_key or os.getenv('SIMPLE_LOGIN_API_KEY')
    if not api_key:
        print("Error: SimpleLogin API key is required")
        sys.exit(1)

    # Get domains and mailbox prefixes
    domains = get_domains()
    if not domains:
        print_status("Error: No domains specified in DOMAINS env var", False)
        sys.exit(1)

    mailbox_prefixes = get_mailbox_prefixes()
    if not mailbox_prefixes:
        print_status("Error: No mailbox prefixes specified in MAILBOX_PREFIX env var", False)
        sys.exit(1)

    # Initialize managers
    sl_manager = SimpleLoginAliasManager(api_key)
    aws_manager = AWSRoute53Manager()
    
    # Process each domain
    for domain in domains:
        if setup_domain(domain, sl_manager, aws_manager):
            if not create_domain_aliases(domain, mailbox_prefixes, sl_manager):
                print_status(f"Some aliases failed for domain {domain}", False)
        else:
            print_status(f"Setup failed for domain {domain}", False)

if __name__ == "__main__":
    main() 