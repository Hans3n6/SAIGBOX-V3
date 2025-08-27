#!/usr/bin/env python3
"""
OAuth Configuration Test Script for SAIGBOX
This script helps verify that OAuth is properly configured for both Google and Microsoft.
"""

import requests
import json
import webbrowser
from urllib.parse import urlparse, parse_qs
from datetime import datetime

# Configuration
BACKEND_URL = "https://api.saigbox.com"
FRONTEND_URL = "http://www.saigbox.com"
DASHBOARD_URL = "https://dashboard.saigbox.com"

class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_header(text):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text:^60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}\n")

def print_success(text):
    print(f"{Colors.GREEN}✓ {text}{Colors.RESET}")

def print_error(text):
    print(f"{Colors.RED}✗ {text}{Colors.RESET}")

def print_warning(text):
    print(f"{Colors.YELLOW}⚠ {text}{Colors.RESET}")

def print_info(text):
    print(f"{Colors.BLUE}ℹ {text}{Colors.RESET}")

def test_backend_connectivity():
    """Test if backend API is reachable"""
    print_header("Testing Backend Connectivity")
    
    try:
        response = requests.get(f"{BACKEND_URL}/api/health", timeout=5)
        if response.status_code == 200:
            print_success(f"Backend API is reachable at {BACKEND_URL}")
            return True
        else:
            print_warning(f"Backend returned status code: {response.status_code}")
            return True
    except requests.exceptions.ConnectionError:
        print_error(f"Cannot connect to backend at {BACKEND_URL}")
        print_info("Make sure the backend server is running on EC2")
        return False
    except requests.exceptions.Timeout:
        print_error("Connection to backend timed out")
        return False
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        return False

def test_google_oauth():
    """Test Google OAuth configuration"""
    print_header("Testing Google OAuth Configuration")
    
    try:
        response = requests.get(f"{BACKEND_URL}/api/auth/google/url", timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            
            if 'url' in data and data['url']:
                print_success("Google OAuth URL generated successfully")
                
                # Parse the OAuth URL
                parsed = urlparse(data['url'])
                params = parse_qs(parsed.query)
                
                # Display important parameters
                print_info(f"OAuth Provider: {parsed.netloc}")
                
                if 'redirect_uri' in params:
                    redirect_uri = params['redirect_uri'][0]
                    print_info(f"Redirect URI: {redirect_uri}")
                    
                    # Check if redirect URI matches expected
                    expected_redirect = f"{BACKEND_URL}/api/auth/google/callback"
                    if redirect_uri == expected_redirect:
                        print_success(f"Redirect URI is correctly configured")
                    else:
                        print_warning(f"Redirect URI mismatch!")
                        print_warning(f"Expected: {expected_redirect}")
                        print_warning(f"Got: {redirect_uri}")
                
                if 'client_id' in params:
                    client_id = params['client_id'][0]
                    print_info(f"Client ID: {client_id[:20]}...")
                
                if 'scope' in params:
                    scopes = params['scope'][0].split(' ')
                    print_info(f"Scopes requested: {len(scopes)} scopes")
                    for scope in scopes[:3]:  # Show first 3 scopes
                        print(f"  - {scope}")
                
                return True
            else:
                print_error("No OAuth URL in response")
                return False
        else:
            print_error(f"Failed to get Google OAuth URL: Status {response.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        print_error(f"Request failed: {e}")
        return False
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        return False

def test_microsoft_oauth():
    """Test Microsoft OAuth configuration"""
    print_header("Testing Microsoft OAuth Configuration")
    
    try:
        response = requests.get(f"{BACKEND_URL}/api/auth/microsoft/url", timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            
            if 'url' in data and data['url']:
                print_success("Microsoft OAuth URL generated successfully")
                
                # Parse the OAuth URL
                parsed = urlparse(data['url'])
                params = parse_qs(parsed.query)
                
                # Display important parameters
                print_info(f"OAuth Provider: {parsed.netloc}")
                
                if 'redirect_uri' in params:
                    redirect_uri = params['redirect_uri'][0]
                    print_info(f"Redirect URI: {redirect_uri}")
                    
                    # Check if redirect URI matches expected
                    expected_redirect = f"{BACKEND_URL}/api/auth/microsoft/callback"
                    if redirect_uri == expected_redirect:
                        print_success(f"Redirect URI is correctly configured")
                    else:
                        print_warning(f"Redirect URI mismatch!")
                        print_warning(f"Expected: {expected_redirect}")
                        print_warning(f"Got: {redirect_uri}")
                
                if 'client_id' in params:
                    client_id = params['client_id'][0]
                    print_info(f"Client ID: {client_id[:20]}...")
                
                if 'scope' in params:
                    scopes = params['scope'][0].split(' ')
                    print_info(f"Scopes requested: {len(scopes)} scopes")
                    for scope in scopes[:3]:  # Show first 3 scopes
                        print(f"  - {scope}")
                
                return True
            else:
                print_error("No OAuth URL in response")
                return False
        else:
            print_error(f"Failed to get Microsoft OAuth URL: Status {response.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        print_error(f"Request failed: {e}")
        return False
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        return False

def display_oauth_urls():
    """Display the URLs that need to be configured in OAuth providers"""
    print_header("OAuth URLs to Configure")
    
    print(f"{Colors.BOLD}GOOGLE OAUTH - Configure at: https://console.cloud.google.com/{Colors.RESET}")
    print("\nAuthorized JavaScript Origins:")
    origins = [
        "http://www.saigbox.com",
        "https://www.saigbox.com",
        f"{BACKEND_URL}",
        "http://localhost:8000"
    ]
    for origin in origins:
        print(f"  • {origin}")
    
    print("\nAuthorized Redirect URIs:")
    google_redirects = [
        f"{BACKEND_URL}/api/auth/google/callback",
        "http://www.saigbox.com/api/auth/google/callback",
        "https://www.saigbox.com/api/auth/google/callback",
        "http://localhost:8000/api/auth/google/callback"
    ]
    for uri in google_redirects:
        print(f"  • {uri}")
    
    print(f"\n{Colors.BOLD}MICROSOFT OAUTH - Configure at: https://portal.azure.com/{Colors.RESET}")
    print("\nRedirect URIs (Web Platform):")
    ms_redirects = [
        f"{BACKEND_URL}/api/auth/microsoft/callback",
        "http://www.saigbox.com/api/auth/microsoft/callback",
        "https://www.saigbox.com/api/auth/microsoft/callback",
        "http://localhost:8000/api/auth/microsoft/callback"
    ]
    for uri in ms_redirects:
        print(f"  • {uri}")
    
    print("\nAlso ensure:")
    print("  • Supported account types: Multitenant + Personal accounts")
    print("  • Implicit grant: Access tokens and ID tokens enabled")

def open_configuration_pages():
    """Open the OAuth configuration pages in browser"""
    print_header("Quick Links")
    
    print("1. Google Cloud Console")
    print("   https://console.cloud.google.com/apis/credentials")
    print("\n2. Azure Portal")
    print("   https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps/ApplicationsListBlade")
    print("\n3. Test Login Page")
    print(f"   {FRONTEND_URL}/login")
    print("\n4. Backend Health Check")
    print(f"   {BACKEND_URL}/api/health")
    
    choice = input("\nOpen any link in browser? (1-4, or 'n' to skip): ").strip()
    
    urls = {
        '1': "https://console.cloud.google.com/apis/credentials",
        '2': "https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps/ApplicationsListBlade",
        '3': f"{FRONTEND_URL}/login",
        '4': f"{BACKEND_URL}/api/health"
    }
    
    if choice in urls:
        webbrowser.open(urls[choice])
        print_success(f"Opened in browser: {urls[choice]}")

def main():
    """Run all tests"""
    print_header("SAIGBOX OAuth Configuration Test")
    print(f"Testing at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Backend URL: {BACKEND_URL}")
    print(f"Frontend URL: {FRONTEND_URL}")
    
    # Run tests
    backend_ok = test_backend_connectivity()
    
    if backend_ok:
        google_ok = test_google_oauth()
        microsoft_ok = test_microsoft_oauth()
        
        # Summary
        print_header("Test Summary")
        if google_ok and microsoft_ok:
            print_success("All OAuth endpoints are working!")
            print_info("Next step: Configure the redirect URIs in Google and Azure consoles")
        elif google_ok:
            print_warning("Google OAuth is working, but Microsoft needs configuration")
        elif microsoft_ok:
            print_warning("Microsoft OAuth is working, but Google needs configuration")
        else:
            print_error("Both OAuth providers need configuration")
    else:
        print_error("Backend is not accessible. Please check the EC2 instance.")
    
    # Display configuration URLs
    display_oauth_urls()
    
    # Offer to open configuration pages
    open_configuration_pages()

if __name__ == "__main__":
    main()