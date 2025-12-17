#!/usr/bin/env python3
"""
Add 50 more test emails for comprehensive feature testing
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
import uuid
import random
from core.database import SessionLocal, User, Email, Base, engine

# Ensure tables exist
Base.metadata.create_all(engine)

def add_test_emails():
    db = SessionLocal()

    try:
        # Get or create test user
        test_user = db.query(User).filter(User.email == "testuser@demo.saigbox.com").first()
        if not test_user:
            print("Test user not found. Run create_test_data.py first.")
            return

        print(f"Adding emails for user: {test_user.email}")

        # 50 diverse test emails
        emails_data = [
            # ===== URGENT EMAILS (10) =====
            {
                "sender": "ceo@company.com",
                "sender_name": "Robert CEO",
                "subject": "URGENT: Board Meeting Prep Required",
                "body_text": """Team,

URGENT - The board meeting has been moved to this Thursday at 9 AM.

I need the following from you by tomorrow EOD:
1. Q4 financial summary with projections
2. Customer acquisition metrics for the quarter
3. Product roadmap updates
4. Team headcount and hiring plan

This is critical for our funding discussion.

Robert
CEO""",
                "is_urgent": True,
                "urgency_score": 95,
                "urgency_reason": "CEO request, board meeting, tight deadline",
                "hours_ago": 1
            },
            {
                "sender": "legal@company.com",
                "sender_name": "Legal Department",
                "subject": "ACTION REQUIRED: Contract Review - Due Today",
                "body_text": """Hi,

The vendor contract expires today and we need your signature by 5 PM.

Please review and sign:
- Master Service Agreement (attached)
- Data Processing Addendum
- SLA terms

Failure to sign will result in service interruption.

Legal Team""",
                "is_urgent": True,
                "urgency_score": 90,
                "urgency_reason": "Contract deadline today, service interruption risk",
                "has_attachments": True,
                "hours_ago": 2
            },
            {
                "sender": "security@company.com",
                "sender_name": "Security Team",
                "subject": "CRITICAL: Password Reset Required Immediately",
                "body_text": """SECURITY ALERT

Your account password must be reset within the next 4 hours due to a potential security incident.

Action required:
1. Go to security.company.com/reset
2. Verify your identity with 2FA
3. Create a new password meeting requirements

Do NOT share this email or click any links other than the official security portal.

Security Team""",
                "is_urgent": True,
                "urgency_score": 92,
                "urgency_reason": "Security incident, immediate action required",
                "hours_ago": 0.5
            },
            {
                "sender": "david.client@bigcorp.com",
                "sender_name": "David Miller",
                "subject": "Re: Proposal - Need Response by EOD",
                "body_text": """Hi,

Our procurement team needs your final pricing by end of day today to include you in the Q1 budget.

Questions we need answered:
1. Can you offer a 15% volume discount?
2. What's the implementation timeline?
3. Is 24/7 support included?

If we don't hear back today, we'll have to go with another vendor.

Thanks,
David Miller
VP Procurement, BigCorp""",
                "is_urgent": True,
                "urgency_score": 88,
                "urgency_reason": "Client deadline, potential lost deal",
                "hours_ago": 3
            },
            {
                "sender": "hr@company.com",
                "sender_name": "HR Department",
                "subject": "REMINDER: Performance Review Due Tomorrow",
                "body_text": """Final Reminder!

Your self-assessment for the annual performance review is due tomorrow by 12 PM.

Please complete:
1. Self-evaluation form in Workday
2. Goal achievements for 2024
3. Development objectives for 2025

Incomplete reviews will affect bonus eligibility.

HR Team""",
                "is_urgent": True,
                "urgency_score": 75,
                "urgency_reason": "Performance review deadline, bonus impact",
                "hours_ago": 8
            },
            {
                "sender": "ops@company.com",
                "sender_name": "Operations",
                "subject": "URGENT: Production Server Down",
                "body_text": """INCIDENT ALERT - P1

Production server prod-web-03 is experiencing critical issues.

Status: DOWN
Impact: 30% of users affected
Started: 10:45 AM

Required actions:
- Check CloudWatch logs
- Review recent deployments
- Contact on-call if needed

Incident channel: #incident-response

Ops Team""",
                "is_urgent": True,
                "urgency_score": 98,
                "urgency_reason": "Production incident, users affected",
                "hours_ago": 0.25
            },
            {
                "sender": "investor@vcfirm.com",
                "sender_name": "Jennifer Park",
                "subject": "Due Diligence Questions - Time Sensitive",
                "body_text": """Hi,

Following our meeting, our investment committee has some follow-up questions. We need responses by Friday to proceed with the term sheet.

1. Can you provide audited financials for 2023-2024?
2. What's your current burn rate?
3. Customer concentration - top 10 clients?
4. Any pending litigation?

Looking forward to moving quickly on this.

Best,
Jennifer Park
Partner, VC Firm""",
                "is_urgent": True,
                "urgency_score": 85,
                "urgency_reason": "Investor deadline, funding dependent",
                "hours_ago": 12
            },
            {
                "sender": "shipping@supplier.com",
                "sender_name": "Supplier Logistics",
                "subject": "URGENT: Shipment Hold - Payment Required",
                "body_text": """Your shipment #SH-2024-8876 is on hold at customs.

To release:
1. Pay outstanding invoice $12,500
2. Submit customs form B-7
3. Confirm delivery address

Deadline: 48 hours or shipment returns to origin.

Contact: shipping@supplier.com
Ref: SH-2024-8876""",
                "is_urgent": True,
                "urgency_score": 78,
                "urgency_reason": "Shipment hold, financial action needed",
                "hours_ago": 18
            },
            {
                "sender": "press@media.com",
                "sender_name": "Tech Reporter",
                "subject": "Media Inquiry - Deadline Today 3PM",
                "body_text": """Hi,

I'm writing a story about AI startups for TechCrunch and would love to include your company.

Quick questions:
1. What makes your AI approach unique?
2. Recent funding/growth metrics?
3. Any customer case studies to share?

My deadline is 3 PM today. A quick 10-minute call would work too.

Thanks!
Alex
Tech Reporter""",
                "is_urgent": True,
                "urgency_score": 72,
                "urgency_reason": "Press opportunity, tight deadline",
                "hours_ago": 4
            },
            {
                "sender": "partner@bigtech.com",
                "sender_name": "Partnership Team",
                "subject": "Partnership Agreement - Signature Needed Today",
                "body_text": """Hi,

Great news! Our partnership deal is approved. However, we need signed documents by EOD to include in this quarter's announcements.

Documents attached:
1. Partnership Agreement
2. Co-marketing Terms
3. Revenue Share Addendum

Please sign via DocuSign link below.

Best,
Partnership Team
BigTech Inc.""",
                "is_urgent": True,
                "urgency_score": 82,
                "urgency_reason": "Partnership deadline, Q4 announcement",
                "has_attachments": True,
                "hours_ago": 5
            },

            # ===== SALES OPPORTUNITIES (10) =====
            {
                "sender": "procurement@fortune500.com",
                "sender_name": "James Wilson",
                "subject": "RFP Response - Enterprise Solution",
                "body_text": """Hello,

We received your RFP response and it's been shortlisted.

Next steps:
1. Technical demo - Week of Jan 15
2. Security assessment questionnaire (attached)
3. Reference calls with similar customers

Budget approved: $500K annually
Decision timeline: End of January

Please confirm your availability.

James Wilson
Director of Procurement""",
                "is_urgent": False,
                "urgency_score": 65,
                "has_attachments": True,
                "hours_ago": 24
            },
            {
                "sender": "cto@startup.io",
                "sender_name": "Maria Chen",
                "subject": "Interested in Your Platform - Demo Request",
                "body_text": """Hi,

I'm the CTO at a Series B startup (200 employees). We're looking to replace our current solution.

What caught our attention:
- Your AI capabilities
- Integration with our stack
- Pricing model

Can we schedule a demo next week? We're evaluating 3 vendors and want to make a decision within 2 weeks.

Maria Chen
CTO, Startup.io""",
                "is_urgent": False,
                "urgency_score": 55,
                "hours_ago": 36
            },
            {
                "sender": "buyer@retailco.com",
                "sender_name": "Tom Anderson",
                "subject": "Re: Quote Request - 500 Licenses",
                "body_text": """Thanks for the quote.

We're ready to proceed but need:
1. 20% discount for annual prepay
2. 30-day payment terms
3. Dedicated support contact

If you can accommodate these terms, we can sign next week. Our current contract expires Feb 1.

Tom Anderson
IT Director, RetailCo""",
                "is_urgent": False,
                "urgency_score": 58,
                "hours_ago": 48
            },
            {
                "sender": "innovation@bank.com",
                "sender_name": "Sarah Thompson",
                "subject": "Pilot Program Interest",
                "body_text": """Hello,

Our innovation lab is exploring new technologies. Your solution was recommended by our advisory board.

We'd like to discuss:
1. 90-day pilot program
2. Compliance requirements (SOC2, PCI)
3. On-premise deployment options

Can you send over your security documentation?

Sarah Thompson
VP Innovation, Major Bank""",
                "is_urgent": False,
                "urgency_score": 48,
                "hours_ago": 72
            },
            {
                "sender": "pm@agency.com",
                "sender_name": "Mike Roberts",
                "subject": "Client Project - Tool Evaluation",
                "body_text": """Hi,

We're a digital agency evaluating tools for a Fortune 100 client project.

Requirements:
- Multi-tenant architecture
- Custom branding
- API access
- Enterprise SLA

Budget: $150K for 2-year deal
Timeline: Implementation by March

Can you send case studies from similar engagements?

Mike Roberts
Senior PM, Creative Agency""",
                "is_urgent": False,
                "urgency_score": 52,
                "hours_ago": 60
            },
            {
                "sender": "director@healthcare.org",
                "sender_name": "Dr. Lisa Park",
                "subject": "Healthcare Solution Inquiry",
                "body_text": """Hello,

Our hospital network (15 facilities) is modernizing our systems.

Key requirements:
- HIPAA compliance
- EHR integration
- 24/7 support
- Training program

We have budget allocated for Q1. Can you provide a proposal?

Dr. Lisa Park
Director of IT, Healthcare Network""",
                "is_urgent": False,
                "urgency_score": 45,
                "hours_ago": 84
            },
            {
                "sender": "vp@manufacturing.com",
                "sender_name": "Robert Kim",
                "subject": "Re: Manufacturing Solution Demo Follow-up",
                "body_text": """Great demo yesterday!

Our team is impressed. Before we proceed:
1. Can you integrate with SAP?
2. What's the typical ROI timeline?
3. Do you offer implementation services?

We're looking at a $300K investment and need board approval by end of month.

Robert Kim
VP Operations""",
                "is_urgent": False,
                "urgency_score": 62,
                "hours_ago": 28
            },
            {
                "sender": "edu@university.edu",
                "sender_name": "Prof. David Lee",
                "subject": "Academic License Inquiry",
                "body_text": """Hello,

Our Computer Science department is interested in your platform for research and teaching.

Questions:
1. Do you offer academic pricing?
2. Can students get individual accounts?
3. Is there API access for research?

We have 500+ students and 50 faculty.

Prof. David Lee
Department Chair""",
                "is_urgent": False,
                "urgency_score": 35,
                "hours_ago": 96
            },
            {
                "sender": "legal@lawfirm.com",
                "sender_name": "Jennifer Stone",
                "subject": "Legal Tech Solution Evaluation",
                "body_text": """Hi,

We're a 200-attorney firm evaluating document management solutions.

Requirements:
- Matter-centric organization
- Advanced search
- Compliance archiving
- Mobile access

Budget: $200K/year
Decision: This quarter

Please send your legal industry references.

Jennifer Stone
Partner, Managing""",
                "is_urgent": False,
                "urgency_score": 50,
                "hours_ago": 108
            },
            {
                "sender": "cfo@growthco.com",
                "sender_name": "Amanda Wright",
                "subject": "Budget Planning - Your Solution",
                "body_text": """Hi,

We're finalizing our 2025 budget and your solution is under consideration.

Need for planning:
1. Total cost of ownership for 3 years
2. Implementation timeline
3. Training costs
4. Support tiers and pricing

Our CEO is pushing for a decision by Dec 31.

Amanda Wright
CFO, GrowthCo""",
                "is_urgent": False,
                "urgency_score": 68,
                "hours_ago": 16
            },

            # ===== NEWSLETTERS & MARKETING (10) =====
            {
                "sender": "digest@hackernews.com",
                "sender_name": "Hacker News Daily",
                "subject": "HN Daily Digest - Top Stories",
                "body_text": """Today's Top Stories on Hacker News:

1. Show HN: I built a self-hosting platform (892 points)
2. The hidden cost of microservices (654 points)
3. PostgreSQL 17 released with major performance improvements
4. Why we moved from Kubernetes to bare metal
5. The decline of software quality

Read more: hackernews.com/daily

Unsubscribe | Preferences""",
                "is_urgent": False,
                "urgency_score": 0,
                "hours_ago": 6
            },
            {
                "sender": "weekly@producthunt.com",
                "sender_name": "Product Hunt",
                "subject": "This Week's Top Products",
                "body_text": """This Week on Product Hunt:

Product of the Week: AI Code Assistant
Runner up: Privacy-First Analytics
3rd Place: Open Source Notion Clone

Featured Launches:
- New design tool for developers
- AI-powered meeting notes
- Team collaboration platform

Discover more: producthunt.com/weekly""",
                "is_urgent": False,
                "urgency_score": 0,
                "hours_ago": 48
            },
            {
                "sender": "news@techcrunch.com",
                "sender_name": "TechCrunch Daily",
                "subject": "TC Daily: AI Funding Boom Continues",
                "body_text": """TechCrunch Daily

TOP STORIES:
- AI startup raises $100M Series C at $1B valuation
- Apple reportedly working on AI features for iPhone 17
- Microsoft announces major Azure updates
- Stripe expands to 10 new countries

STARTUP NEWS:
- 5 startups to watch in 2025
- The rise of vertical AI

Read full stories: techcrunch.com""",
                "is_urgent": False,
                "urgency_score": 0,
                "hours_ago": 12
            },
            {
                "sender": "marketing@saas.com",
                "sender_name": "SaaS Weekly",
                "subject": "50% Off Annual Plans - Limited Time",
                "body_text": """HOLIDAY SALE!

Get 50% off all annual plans through December 31.

What's included:
- Unlimited users
- Priority support
- Custom integrations
- Advanced analytics

Use code: HOLIDAY50

Offer expires in 3 days!

Shop now: saas.com/sale""",
                "is_urgent": False,
                "urgency_score": 15,
                "hours_ago": 36
            },
            {
                "sender": "learn@coursera.com",
                "sender_name": "Coursera",
                "subject": "New Course: AI for Business Leaders",
                "body_text": """New Course Alert!

AI for Business Leaders
by Stanford University

What you'll learn:
- AI strategy and implementation
- Managing AI teams
- Ethical considerations
- ROI measurement

4 weeks | 4-6 hours/week
Certificate included

Enroll now: coursera.com/ai-business""",
                "is_urgent": False,
                "urgency_score": 5,
                "hours_ago": 72
            },
            {
                "sender": "updates@github.com",
                "sender_name": "GitHub",
                "subject": "GitHub Universe 2024 Highlights",
                "body_text": """GitHub Universe 2024 Recap

Key Announcements:
1. Copilot X - Next generation AI assistant
2. Actions 3.0 - Faster CI/CD
3. Security Center - Unified vulnerability management
4. Enterprise Cloud - New compliance features

Watch recordings: github.com/universe

What's next for GitHub: github.com/roadmap""",
                "is_urgent": False,
                "urgency_score": 10,
                "hours_ago": 120
            },
            {
                "sender": "newsletter@stripe.com",
                "sender_name": "Stripe",
                "subject": "Stripe Sessions: What's New",
                "body_text": """What's New at Stripe

Product Updates:
- Revenue Recognition now supports 150+ countries
- New Invoicing features for subscriptions
- Improved fraud detection with Radar 2.0
- Connect updates for platforms

Developer Resources:
- New SDK versions released
- API documentation improvements
- Sample apps updated

Learn more: stripe.com/blog""",
                "is_urgent": False,
                "urgency_score": 8,
                "hours_ago": 96
            },
            {
                "sender": "events@aws.com",
                "sender_name": "AWS Events",
                "subject": "re:Invent 2024 - Session Recordings Available",
                "body_text": """AWS re:Invent 2024

Session recordings are now available!

Popular Sessions:
- Keynote with Adam Selipsky
- What's New in AI/ML Services
- Building Serverless Applications
- Security Best Practices

Access all 1,000+ sessions: aws.amazon.com/reinvent

Early bird for 2025 now open!""",
                "is_urgent": False,
                "urgency_score": 5,
                "hours_ago": 144
            },
            {
                "sender": "community@slack.com",
                "sender_name": "Slack Community",
                "subject": "Tips for Remote Team Collaboration",
                "body_text": """Slack Tips & Tricks

This Week's Focus: Remote Team Collaboration

Top Tips:
1. Use huddles for quick sync-ups
2. Set up automated workflows
3. Integrate your tools
4. Create team channels for transparency
5. Use canvas for documentation

New Feature: Slack AI
Summarize channels, catch up on conversations, and more.

Learn more: slack.com/features""",
                "is_urgent": False,
                "urgency_score": 3,
                "hours_ago": 168
            },
            {
                "sender": "weekly@linkedin.com",
                "sender_name": "LinkedIn News",
                "subject": "This Week's Top Professional News",
                "body_text": """LinkedIn Weekly

TOP STORIES:
- Tech hiring rebounds in Q4
- Remote work policies evolving
- AI skills most in-demand
- Salary trends for 2025

CAREER TIPS:
- How to negotiate in this market
- Building your personal brand
- Networking in the AI age

Read more: linkedin.com/news""",
                "is_urgent": False,
                "urgency_score": 2,
                "hours_ago": 84
            },

            # ===== INTERNAL TEAM EMAILS (10) =====
            {
                "sender": "team@company.com",
                "sender_name": "Engineering Team",
                "subject": "Sprint Planning - Monday 10 AM",
                "body_text": """Hi team,

Sprint planning is scheduled for Monday at 10 AM.

Please prepare:
1. Your velocity estimate for next sprint
2. Any carryover items from current sprint
3. Technical debt items to address
4. Dependencies on other teams

Meeting link: zoom.us/j/123456789

See you there!""",
                "is_urgent": False,
                "urgency_score": 35,
                "hours_ago": 20
            },
            {
                "sender": "pm@company.com",
                "sender_name": "Product Manager",
                "subject": "Feature Prioritization Feedback Needed",
                "body_text": """Hi everyone,

I need input on Q1 feature prioritization by Friday.

Candidates:
1. Dashboard redesign
2. API v2.0
3. Mobile app improvements
4. Reporting enhancements
5. Integration marketplace

Please rank 1-5 and add comments in the shared doc.

Doc link: docs.google.com/prioritization

Thanks!""",
                "is_urgent": False,
                "urgency_score": 45,
                "hours_ago": 32
            },
            {
                "sender": "design@company.com",
                "sender_name": "Design Team",
                "subject": "New Brand Guidelines Released",
                "body_text": """Hi all,

Our updated brand guidelines are now available!

What's new:
- Refreshed color palette
- Updated typography
- New icon library
- Motion guidelines
- Accessibility standards

Access the guidelines: figma.com/brandbook

Please update any customer-facing materials by end of month.

Design Team""",
                "is_urgent": False,
                "urgency_score": 30,
                "hours_ago": 56
            },
            {
                "sender": "devops@company.com",
                "sender_name": "DevOps",
                "subject": "Scheduled Maintenance - This Weekend",
                "body_text": """Maintenance Notice

When: Saturday 2 AM - 6 AM EST
What: Database migration and infrastructure updates

Impact:
- 2-4 hours of downtime
- API unavailable during window
- Webhooks will be queued and replayed

What to do:
- No deployments after Friday 3 PM
- Monitor #ops channel for updates

Questions? Reply to this thread.

DevOps Team""",
                "is_urgent": False,
                "urgency_score": 40,
                "hours_ago": 44
            },
            {
                "sender": "finance@company.com",
                "sender_name": "Finance Team",
                "subject": "Expense Reports Due - End of Month",
                "body_text": """Reminder: Expense Reports

All expense reports for December must be submitted by Dec 31.

Process:
1. Submit in Expensify
2. Include receipts for items > $25
3. Get manager approval
4. Finance review takes 3-5 days

Reimbursement will be in January 15 paycheck.

Questions? Contact finance@company.com""",
                "is_urgent": False,
                "urgency_score": 28,
                "hours_ago": 68
            },
            {
                "sender": "allhands@company.com",
                "sender_name": "CEO",
                "subject": "All Hands Meeting - Thursday",
                "body_text": """Team,

Join us for our monthly all-hands this Thursday at 4 PM.

Agenda:
1. Q4 results preview
2. 2025 company goals
3. New product announcements
4. Team recognition
5. Q&A

Zoom link: zoom.us/allhands
Recording will be available for those who can't attend.

Looking forward to seeing everyone!""",
                "is_urgent": False,
                "urgency_score": 32,
                "hours_ago": 40
            },
            {
                "sender": "recruiting@company.com",
                "sender_name": "Recruiting",
                "subject": "Referral Bonus Update",
                "body_text": """Great news!

We're increasing referral bonuses for Q1:
- Engineering: $5,000 -> $7,500
- Sales: $3,000 -> $5,000
- Other roles: $2,000 -> $3,000

Hot roles we're hiring:
1. Senior Backend Engineer
2. Enterprise AE
3. Product Designer
4. Customer Success Manager

Submit referrals: company.com/referrals

Help us build the team!""",
                "is_urgent": False,
                "urgency_score": 18,
                "hours_ago": 80
            },
            {
                "sender": "it@company.com",
                "sender_name": "IT Support",
                "subject": "New Software Rollout - Training Available",
                "body_text": """Software Update

We're rolling out the new project management tool company-wide.

Training sessions:
- Monday 2 PM: Basic features
- Tuesday 2 PM: Advanced workflows
- Wednesday 2 PM: Admin training

All sessions recorded and available in Confluence.

Migration timeline:
- Week 1: Teams A-M
- Week 2: Teams N-Z

Support: it@company.com or #it-help""",
                "is_urgent": False,
                "urgency_score": 25,
                "hours_ago": 52
            },
            {
                "sender": "social@company.com",
                "sender_name": "Culture Committee",
                "subject": "Holiday Party - RSVP Required",
                "body_text": """You're Invited!

Annual Holiday Party
Date: Friday, December 20
Time: 6 PM - 10 PM
Location: The Grand Ballroom

What to expect:
- Dinner and drinks
- DJ and dancing
- Photo booth
- Awards ceremony
- Plus ones welcome!

RSVP by Dec 15: company.com/rsvp

See you there!""",
                "is_urgent": False,
                "urgency_score": 22,
                "hours_ago": 100
            },
            {
                "sender": "qa@company.com",
                "sender_name": "QA Team",
                "subject": "Release Testing - Help Needed",
                "body_text": """Hi team,

We need help with release testing for v2.5.

Areas needing coverage:
1. New dashboard features
2. API endpoint changes
3. Mobile responsiveness
4. Accessibility compliance

Test environment: staging.company.com
Test accounts: test1@test.com / password123

Report bugs in Jira project QA-RELEASE.

Thanks for your help!
QA Team""",
                "is_urgent": False,
                "urgency_score": 38,
                "hours_ago": 28
            },

            # ===== INVOICES & BILLING (5) =====
            {
                "sender": "billing@cloudprovider.com",
                "sender_name": "Cloud Provider",
                "subject": "Invoice #INV-2024-5567 - December Usage",
                "body_text": """Invoice Summary

Invoice #: INV-2024-5567
Period: December 1-31, 2024
Amount Due: $8,450.00
Due Date: January 15, 2025

Breakdown:
- Compute: $4,200
- Storage: $1,800
- Network: $950
- Support: $1,500

Pay online: cloudprovider.com/billing

Questions? Reply to this email.""",
                "is_urgent": False,
                "urgency_score": 42,
                "has_attachments": True,
                "hours_ago": 24
            },
            {
                "sender": "accounts@saastool.com",
                "sender_name": "SaaS Tool Billing",
                "subject": "Your Subscription Renews in 7 Days",
                "body_text": """Renewal Notice

Your annual subscription renews on January 10, 2025.

Current plan: Enterprise
Amount: $12,000/year
Payment method: Visa ending in 4242

What's included:
- Unlimited users
- Priority support
- Custom integrations
- Advanced security

Update payment: saastool.com/billing
Cancel: Contact support before renewal

Thank you for being a customer!""",
                "is_urgent": False,
                "urgency_score": 35,
                "hours_ago": 72
            },
            {
                "sender": "receipts@expensify.com",
                "sender_name": "Expensify",
                "subject": "Payment Received - $2,340.00",
                "body_text": """Payment Confirmation

We've received your payment.

Amount: $2,340.00
Date: December 10, 2024
Invoice: #EXP-2024-1234
Method: ACH Transfer

Your account is current.

View receipt: expensify.com/receipts

Thank you!""",
                "is_urgent": False,
                "urgency_score": 10,
                "hours_ago": 48
            },
            {
                "sender": "ar@vendor.com",
                "sender_name": "Vendor AR",
                "subject": "Past Due Notice - Invoice #7789",
                "body_text": """Payment Reminder

Invoice #7789 is 15 days past due.

Original Due Date: November 25, 2024
Amount Due: $3,500.00
Late Fee Applied: $50.00
Total Due: $3,550.00

Please remit payment immediately to avoid service interruption.

Pay online: vendor.com/pay
Questions: ar@vendor.com

Thank you for your prompt attention.""",
                "is_urgent": True,
                "urgency_score": 70,
                "urgency_reason": "Past due payment, service interruption risk",
                "hours_ago": 36
            },
            {
                "sender": "subscription@newsletter.com",
                "sender_name": "Newsletter Pro",
                "subject": "Payment Failed - Action Required",
                "body_text": """Payment Failed

We couldn't process your payment for Newsletter Pro.

Amount: $29.00/month
Reason: Card declined
Next retry: December 15, 2024

To continue service:
1. Update payment method
2. Verify billing address
3. Contact your bank if needed

Update now: newsletter.com/billing

Service will be suspended after 3 failed attempts.""",
                "is_urgent": False,
                "urgency_score": 55,
                "hours_ago": 60
            },

            # ===== CUSTOMER SUPPORT (5) =====
            {
                "sender": "support@customer.com",
                "sender_name": "Customer Support Request",
                "subject": "Re: Ticket #45678 - Integration Issue",
                "body_text": """Hi Support,

We're still experiencing the API integration issue.

Error: 429 Too Many Requests
Frequency: Every 5 minutes
Impact: Data sync failing

We've tried:
1. Reducing request rate
2. Implementing backoff
3. Checking rate limits

This is blocking our go-live. Please escalate if needed.

Ticket #45678
Priority: High""",
                "is_urgent": True,
                "urgency_score": 75,
                "urgency_reason": "Customer escalation, go-live blocked",
                "hours_ago": 8
            },
            {
                "sender": "feedback@product.com",
                "sender_name": "Customer Feedback",
                "subject": "Feature Request: Bulk Export",
                "body_text": """Feature Request

From: Enterprise Customer
Account: Premium Tier

Request: Bulk data export functionality

Use case:
- Monthly reporting
- Compliance audits
- Data backup

Current workaround: Manual CSV downloads (time-consuming)

Desired: One-click export of all data in multiple formats

Priority: Medium
Votes: 47 other customers requested this""",
                "is_urgent": False,
                "urgency_score": 30,
                "hours_ago": 120
            },
            {
                "sender": "help@service.com",
                "sender_name": "Help Desk",
                "subject": "Your ticket has been resolved",
                "body_text": """Ticket Update

Ticket #99887 - Login Issues
Status: RESOLVED

Summary:
Your account was locked due to multiple failed login attempts. We've reset your account and enabled additional security measures.

Resolution:
1. Password has been reset
2. 2FA has been enabled
3. Session tokens cleared

If you continue to experience issues, please reply to this email.

Thank you for your patience!""",
                "is_urgent": False,
                "urgency_score": 15,
                "hours_ago": 16
            },
            {
                "sender": "nps@company.com",
                "sender_name": "Customer Success",
                "subject": "How likely are you to recommend us?",
                "body_text": """Quick Survey

Hi!

We'd love your feedback.

On a scale of 0-10, how likely are you to recommend us to a colleague?

[0] [1] [2] [3] [4] [5] [6] [7] [8] [9] [10]

Click your rating above or reply with your score.

Optional: What's the main reason for your score?

Thank you for being a valued customer!

- Customer Success Team""",
                "is_urgent": False,
                "urgency_score": 5,
                "hours_ago": 96
            },
            {
                "sender": "onboarding@platform.com",
                "sender_name": "Onboarding Team",
                "subject": "Welcome! Let's get you started",
                "body_text": """Welcome to Platform!

Your account is ready. Here's how to get started:

Step 1: Complete your profile
Step 2: Connect your first integration
Step 3: Invite your team
Step 4: Schedule onboarding call

Resources:
- Getting Started Guide: docs.platform.com/start
- Video tutorials: platform.com/learn
- Community forum: community.platform.com

Your dedicated success manager: success@platform.com

Let's make this a success!""",
                "is_urgent": False,
                "urgency_score": 20,
                "hours_ago": 140
            },
        ]

        # Create emails
        created_count = 0
        for i, email_data in enumerate(emails_data):
            hours_ago = email_data.pop("hours_ago", 0)
            email = Email(
                id=str(uuid.uuid4()),
                user_id=test_user.id,
                gmail_id=f"demo-gmail-{1000 + i:04d}",
                subject=email_data["subject"],
                sender=email_data["sender"],
                sender_name=email_data["sender_name"],
                body_text=email_data["body_text"],
                snippet=email_data["body_text"][:100] + "...",
                is_urgent=email_data.get("is_urgent", False),
                urgency_score=email_data.get("urgency_score", 0),
                urgency_reason=email_data.get("urgency_reason"),
                has_attachments=email_data.get("has_attachments", False),
                is_read=hours_ago > 48,  # Mark older emails as read
                received_at=datetime.utcnow() - timedelta(hours=hours_ago),
                created_at=datetime.utcnow()
            )
            db.add(email)
            created_count += 1

        db.commit()

        # Print summary
        total_emails = db.query(Email).filter(Email.user_id == test_user.id).count()
        urgent_count = db.query(Email).filter(
            Email.user_id == test_user.id,
            Email.is_urgent == True
        ).count()

        print(f"\n✅ Added {created_count} new test emails!")
        print(f"   - Total emails now: {total_emails}")
        print(f"   - Urgent emails: {urgent_count}")
        print(f"\n📧 Categories added:")
        print(f"   - 10 Urgent emails (deadlines, incidents, etc.)")
        print(f"   - 10 Sales opportunities")
        print(f"   - 10 Newsletters & marketing")
        print(f"   - 10 Internal team emails")
        print(f"   - 5 Invoices & billing")
        print(f"   - 5 Customer support")

    except Exception as e:
        db.rollback()
        print(f"❌ Error adding test emails: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    add_test_emails()
