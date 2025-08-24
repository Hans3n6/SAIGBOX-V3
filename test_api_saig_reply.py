#!/usr/bin/env python3
"""Test SAIG reply via API to ensure threading works"""

import requests
import json
import sys

# Test authentication
auth_headers = {
    "Cookie": "session=eyJpZCI6MX0.Z0kY2Q.hXQkkD0QP7JKisBBr_0MYaIXRaY"
}

# First, get the list of emails
emails_response = requests.get(
    "http://localhost:8000/api/emails/",
    headers=auth_headers
)

if emails_response.status_code != 200:
    print(f"Failed to get emails: {emails_response.status_code}")
    print(emails_response.text)
    sys.exit(1)

emails_data = emails_response.json()
if not emails_data.get("emails"):
    print("No emails found. Please sync emails first.")
    sys.exit(1)

# Get the first email
first_email = emails_data["emails"][0]
email_id = first_email["id"]
print(f"Testing SAIG reply for email: {first_email['subject']}")
print(f"Email ID: {email_id}")
print(f"Thread ID: {first_email.get('thread_id', 'None')}")

# Test SAIG reply generation
saig_reply_data = {
    "message": """Please read this email and generate an appropriate, professional reply.
                
Generate a thoughtful and contextually appropriate response that:
1. Acknowledges the sender's message
2. Addresses any questions or requests
3. Maintains a professional tone
4. Includes a proper greeting and closing""",
    "context": {
        "email_id": email_id
    }
}

print("\n=== Testing SAIG Reply Generation ===")
saig_response = requests.post(
    "http://localhost:8000/api/saig/message",
    headers=auth_headers,
    json=saig_reply_data
)

if saig_response.status_code == 200:
    result = saig_response.json()
    print(f"✅ SAIG Reply Generated Successfully")
    print(f"Intent: {result.get('intent')}")
    print(f"Actions: {result.get('actions_taken')}")
    print("\n--- Generated Reply ---")
    print(result.get('response', 'No response'))
else:
    print(f"❌ Failed to generate SAIG reply: {saig_response.status_code}")
    print(saig_response.text)

# Now test actual email reply to ensure threading
if saig_response.status_code == 200:
    print("\n=== Testing Email Reply with Threading ===")
    
    # Extract the reply content from SAIG response
    saig_reply_content = result.get('response', '')
    
    # Send the reply via the reply endpoint
    reply_data = {
        "email_id": email_id,
        "body": saig_reply_content,
        "reply_all": False
    }
    
    reply_response = requests.post(
        "http://localhost:8000/api/emails/reply",
        headers=auth_headers,
        json=reply_data
    )
    
    if reply_response.status_code == 200:
        reply_result = reply_response.json()
        print(f"✅ Email Reply Sent Successfully")
        print(f"Thread ID maintained: {reply_result.get('thread_id')}")
        print(f"Success: {reply_result.get('success')}")
        print(f"Message: {reply_result.get('message')}")
    else:
        print(f"❌ Failed to send email reply: {reply_response.status_code}")
        print(reply_response.text)