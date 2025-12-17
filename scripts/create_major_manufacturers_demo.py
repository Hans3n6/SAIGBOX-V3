#!/usr/bin/env python3
"""
Create demo user with 75 sample emails for Major Manufacturers - Industrial Equipment Sales.
The user is a sales rep selling industrial machinery, CNC equipment, and manufacturing solutions.
Tests all SAIGBOX systems: urgency detection, action items, sales dashboard, BANT scoring, objections, etc.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
import uuid
from core.database import SessionLocal, User, Email, ActionItem, BusinessProfile, Base, engine

# Ensure tables exist
Base.metadata.create_all(engine)

def create_major_manufacturers_demo():
    db = SessionLocal()

    try:
        # Check if test user already exists
        existing_user = db.query(User).filter(User.email == "testuser@demo.saigbox.com").first()
        if existing_user:
            print(f"Test user already exists: {existing_user.email}")
            print("Deleting existing test data to recreate...")
            db.query(ActionItem).filter(ActionItem.user_id == existing_user.id).delete()
            db.query(Email).filter(Email.user_id == existing_user.id).delete()
            db.query(BusinessProfile).filter(BusinessProfile.user_id == existing_user.id).delete()
            db.query(User).filter(User.id == existing_user.id).delete()
            db.commit()

        # Create test user - Industrial Equipment Sales Rep at Major Manufacturers
        test_user = User(
            id=str(uuid.uuid4()),
            email="testuser@demo.saigbox.com",
            name="Marcus Chen",
            provider="demo",
            oauth_access_token="demo-token-12345",
            oauth_refresh_token="demo-refresh-token",
            oauth_token_expires=datetime.utcnow() + timedelta(days=365),
            last_login=datetime.utcnow(),
            created_at=datetime.utcnow()
        )
        db.add(test_user)
        db.flush()

        print(f"Created demo user: {test_user.name} <{test_user.email}>")
        print("Role: Senior Sales Executive at Major Manufacturers Inc.")

        # Create business profile for Major Manufacturers
        business_profile = BusinessProfile(
            user_id=test_user.id,
            company_name="Major Manufacturers Inc.",
            company_website="https://majormanufacturers.com",
            industry="Industrial Manufacturing",
            company_size="500-1000",
            value_proposition="We deliver precision industrial equipment and CNC machinery that increases production efficiency by 40% while reducing operational costs. Our solutions are backed by 24/7 support and industry-leading warranties.",
            elevator_pitch="Major Manufacturers has been the trusted partner for precision manufacturing equipment since 1985. We help production facilities increase output, reduce downtime, and achieve Six Sigma quality standards.",
            key_differentiators=[
                "40+ years of industry expertise",
                "24/7 technical support",
                "Custom engineering solutions",
                "In-house financing options",
                "Nationwide service network"
            ],
            products_services=[
                {"name": "CNC Machining Centers", "description": "5-axis precision machining", "price_range": "$150,000-$850,000"},
                {"name": "Industrial Lathes", "description": "High-precision turning solutions", "price_range": "$75,000-$400,000"},
                {"name": "Robotic Automation", "description": "Factory automation systems", "price_range": "$200,000-$2,000,000"},
                {"name": "Quality Inspection", "description": "CMM and metrology equipment", "price_range": "$50,000-$500,000"},
                {"name": "Maintenance Contracts", "description": "Preventive maintenance programs", "price_range": "$15,000-$100,000/year"}
            ],
            pricing_model="Equipment sale + installation + optional maintenance contracts",
            average_deal_size=350000,
            notable_clients=["Boeing", "Tesla", "Lockheed Martin", "General Motors", "Caterpillar"],
            case_studies=[
                {"client": "Midwest Precision Parts", "result": "Increased throughput by 65%"},
                {"client": "Advanced Aerospace Components", "result": "Achieved 99.98% quality rate"}
            ],
            cold_email_tone="professional",
            max_emails_per_day=50,
            quality_threshold=70
        )
        db.add(business_profile)

        # 75 Industrial Manufacturing Sales Emails
        emails_data = [
            # ============================================
            # HOT LEADS - Ready to buy (High BANT scores)
            # ============================================
            {
                "sender": "robert.martinez@precisionaero.com",
                "sender_name": "Robert Martinez",
                "subject": "Ready to Purchase - DMG MORI NLX 2500 CNC Lathe",
                "body_text": """Marcus,

We've completed our evaluation and we're ready to move forward with the DMG MORI NLX 2500 you quoted.

Budget is approved at $425,000 and I have full authority from our VP of Operations to sign. We need this installed before our new aerospace contract starts in Q2.

Can you send over the final purchase agreement today? I'd like to get this wrapped up by Friday.

Also, what's included in your 3-year service package?

Thanks,
Robert Martinez
Plant Manager, Precision Aerospace Components
AS9100 Certified Facility""",
                "is_urgent": True,
                "urgency_score": 95,
                "urgency_reason": "Hot lead ready to close, requesting paperwork today",
                "hours_ago": 1
            },
            {
                "sender": "jennifer.wong@globalautomotive.com",
                "sender_name": "Jennifer Wong",
                "subject": "RE: Robotic Welding Cell Quote - Let's Finalize",
                "body_text": """Hi Marcus,

Thank you for adjusting the payment terms on the FANUC robotic welding cell. That works perfectly with our capex budget cycle.

We're ready to proceed. Our CFO has signed off and we need this operational for our new EV battery tray production line.

Quick questions before we sign:
1. Can you include operator training for our third shift team?
2. Confirm delivery timeline is 8 weeks?
3. Is the collision detection upgrade available at the quoted price?

Our production deadline is firm - we have a $40M contract with a major OEM depending on this.

Best,
Jennifer Wong
Director of Manufacturing, Global Automotive Solutions
Tier 1 Supplier""",
                "is_urgent": True,
                "urgency_score": 92,
                "urgency_reason": "Ready to sign, tied to major OEM contract",
                "hours_ago": 2
            },
            {
                "sender": "thomas.burke@midwestprecision.com",
                "sender_name": "Thomas Burke",
                "subject": "URGENT: Need Replacement CNC by End of Month",
                "body_text": """Marcus,

URGENT - Our Mazak HCN-5000 had a catastrophic spindle failure yesterday. We're dead in the water.

We need the Okuma MB-5000H you showed us at IMTS. I know you said you had one in your demo inventory.

Budget is not an issue - we'll pay full price plus expedited installation. Can you deliver within 2 weeks? We have $2M in backlogged orders and we're bleeding $50K per day in lost production.

Call me immediately.

Thomas Burke
CEO, Midwest Precision Manufacturing
Direct: (312) 555-7890""",
                "is_urgent": True,
                "urgency_score": 98,
                "urgency_reason": "Emergency purchase, production down, significant daily losses",
                "hours_ago": 3
            },
            {
                "sender": "amanda.foster@innovativemedical.com",
                "sender_name": "Amanda Foster",
                "subject": "PO Ready - Swiss-Type Lathe for Medical Components",
                "body_text": """Marcus,

Great news - our board approved the capital expenditure yesterday.

Please send the final quote for the Citizen L20-XII Swiss-type lathe with the medical package. We discussed $285,000 with the high-pressure coolant system included.

We need this for our new orthopedic implant contract with a major hospital network. FDA validation timeline starts in 60 days.

Our purchasing department will issue the PO as soon as we receive your formal quote.

Amanda Foster
VP of Operations, Innovative Medical Devices
ISO 13485 Certified""",
                "is_urgent": True,
                "urgency_score": 88,
                "urgency_reason": "Board approved, waiting for formal quote, FDA timeline pressure",
                "hours_ago": 5
            },

            # ============================================
            # WARM LEADS - Interested, need nurturing
            # ============================================
            {
                "sender": "david.chen@pacificmetalworks.com",
                "sender_name": "David Chen",
                "subject": "Question About Financing Options for 5-Axis",
                "body_text": """Hi Marcus,

I enjoyed our conversation at the WESTEC show last week. The Hermle C 42 U you demonstrated would be perfect for our aerospace work.

My concern is the financing. At $750K, this is our biggest equipment purchase ever. What options do you have? Can you work with our existing bank, or do you have in-house programs?

We're an approved supplier for Boeing and Northrop, so our business is stable, but cash flow can be tight with aerospace payment terms.

Looking forward to your thoughts.

David Chen
Owner, Pacific Metalworks Inc.
ITAR Registered""",
                "is_urgent": False,
                "urgency_score": 68,
                "urgency_reason": "Qualified lead with financing concerns, stable business",
                "hours_ago": 8
            },
            {
                "sender": "michelle.rodriguez@sunbeltfabrication.com",
                "sender_name": "Michelle Rodriguez",
                "subject": "Comparing Your Fiber Laser to Trumpf",
                "body_text": """Marcus,

We're in the final stages of selecting a new fiber laser cutter for our expansion.

Your Mazak OPTIPLEX 3015 is on our short list along with the Trumpf TruLaser 3030. Trumpf came in about 15% higher but they're offering 5 years of free preventive maintenance.

What can Major Manufacturers do to match that? Our decision committee meets next Tuesday.

We cut primarily 1/4" to 1/2" steel plate, about 60,000 lbs per month.

Michelle Rodriguez
Operations Manager, Sunbelt Fabrication
$18M annual revenue""",
                "is_urgent": False,
                "urgency_score": 72,
                "urgency_reason": "Competitive situation, decision next Tuesday",
                "hours_ago": 12
            },
            {
                "sender": "brian.thompson@thompsonmachine.com",
                "sender_name": "Brian Thompson",
                "subject": "Need ROI Analysis for New VMC",
                "body_text": """Hi Marcus,

I'm trying to justify the Haas VF-4SS to my partners. We're a small job shop and $150K is significant for us.

Can you help me build an ROI case? Currently we're outsourcing about $15K/month in work that this machine could bring in-house.

Also interested in your trade-in program. We have a 2010 Haas VF-2 that's still running but limiting our capabilities.

What numbers have other shops like ours seen after upgrading?

Brian Thompson
Thompson Machine & Tool
15-person shop""",
                "is_urgent": False,
                "urgency_score": 55,
                "urgency_reason": "Needs help justifying purchase, small business concerns",
                "hours_ago": 18
            },
            {
                "sender": "lisa.nakamura@precisionplastics.com",
                "sender_name": "Lisa Nakamura",
                "subject": "Interested in Your CMM Equipment",
                "body_text": """Marcus,

We're expanding our quality lab and looking at coordinate measuring machines. Someone at our industry association recommended Major Manufacturers.

Can you tell me more about your Zeiss and Hexagon offerings? We need something that can handle our injection molded parts - tolerances of +/- 0.001".

Our current manual inspection is creating a bottleneck. We're measuring 500 parts per day.

What would a site visit and demo look like?

Lisa Nakamura
Quality Manager, Precision Plastics Corp
ISO 9001:2015""",
                "is_urgent": False,
                "urgency_score": 50,
                "urgency_reason": "New inquiry, exploring options, referral",
                "hours_ago": 24
            },
            {
                "sender": "kevin.o'brien@obrienmanufacturing.com",
                "sender_name": "Kevin O'Brien",
                "subject": "Following Up on IMTS Conversation",
                "body_text": """Hi Marcus,

We met briefly at your IMTS booth in September. You were showing the automated pallet changing system for the Makino a51nx.

I've been thinking about it ever since. We run two shifts but can't justify a third shift operator. This could be the solution.

Our current utilization is only 65% because of setup times. What kind of improvement have your other customers seen?

I'd like to schedule a deeper dive, maybe visit one of your reference customers?

Kevin O'Brien
Plant Manager, O'Brien Manufacturing
Job shop serving medical and aerospace""",
                "is_urgent": False,
                "urgency_score": 60,
                "urgency_reason": "Trade show follow-up, interested in automation",
                "hours_ago": 36
            },

            # ============================================
            # PRICE OBJECTIONS
            # ============================================
            {
                "sender": "steve.williams@williamsfab.com",
                "sender_name": "Steve Williams",
                "subject": "RE: Quote #MM-2024-1847 - Price Concerns",
                "body_text": """Marcus,

I have to be honest - I got a quote from your competitor that's $45,000 less for a similar press brake.

I prefer doing business with Major Manufacturers because of your service reputation, but I can't justify a 20% premium to my board.

Is there any flexibility on the pricing? Or maybe a different configuration that gets us closer?

We've budgeted $180,000 for this equipment.

Steve Williams
CFO, Williams Fabrication Inc.""",
                "is_urgent": False,
                "urgency_score": 65,
                "urgency_reason": "Price objection, but prefers our company",
                "hours_ago": 6
            },
            {
                "sender": "carol.jenkins@jenkinsind.com",
                "sender_name": "Carol Jenkins",
                "subject": "Budget Constraints - Can We Phase the Purchase?",
                "body_text": """Hi Marcus,

Love the automation cell proposal, but $1.2M is more than we can handle in one fiscal year.

Is there a way to phase this? Maybe start with the machining center this year and add the robot and pallet system next year?

What would that look like from a pricing standpoint? And would we still get the integration benefits?

Carol Jenkins
Director of Manufacturing, Jenkins Industries
Automotive Tier 2""",
                "is_urgent": False,
                "urgency_score": 58,
                "urgency_reason": "Budget timing objection, open to creative solutions",
                "hours_ago": 28
            },

            # ============================================
            # TIMING OBJECTIONS
            # ============================================
            {
                "sender": "richard.hall@hallprecision.com",
                "sender_name": "Richard Hall",
                "subject": "RE: CNC Proposal - Timing Issue",
                "body_text": """Marcus,

The quote looks great, but our timing is off. We just lost a major customer (about 30% of our business) and we're not sure what the next 6 months look like.

Can we revisit this in Q2? I don't want to commit to a $300K purchase when our revenue picture is uncertain.

Keep me on your radar though - if things stabilize, we'll definitely be in the market.

Richard Hall
Owner, Hall Precision Machining""",
                "is_urgent": False,
                "urgency_score": 35,
                "urgency_reason": "Timing objection due to business uncertainty",
                "hours_ago": 72
            },
            {
                "sender": "nancy.kim@kimtooldie.com",
                "sender_name": "Nancy Kim",
                "subject": "Interested but Need to Wait for Grant",
                "body_text": """Hi Marcus,

We've applied for a state manufacturing modernization grant that would cover 40% of the EDM machine cost.

Results come out in March. If we get it, we're definitely buying. If not, we'll need to reconsider our budget.

Can you hold the pricing until then? And what's your typical lead time for the Sodick AG60L?

Nancy Kim
Kim Tool & Die Company
Third generation family business""",
                "is_urgent": False,
                "urgency_score": 45,
                "urgency_reason": "Timing objection, waiting for grant decision",
                "hours_ago": 48
            },

            # ============================================
            # AUTHORITY OBJECTIONS
            # ============================================
            {
                "sender": "james.morrison@morrisoncorp.com",
                "sender_name": "James Morrison",
                "subject": "RE: Robotic System Quote - Need Board Approval",
                "body_text": """Marcus,

I'm personally sold on the solution, but anything over $500K requires board approval at Morrison Corp.

Our next board meeting is January 15th. Can you prepare a presentation I can share with them? They'll want to see:
- ROI analysis
- Customer references (preferably in our industry)
- Implementation timeline
- Risk mitigation plan

I'll champion this internally but I need ammunition.

James Morrison
VP of Operations, Morrison Corporation
$200M diversified manufacturer""",
                "is_urgent": False,
                "urgency_score": 62,
                "urgency_reason": "Authority objection, board approval needed",
                "hours_ago": 16
            },
            {
                "sender": "patricia.dunn@dunnmfg.com",
                "sender_name": "Patricia Dunn",
                "subject": "Involving Our Engineering Team",
                "body_text": """Hi Marcus,

Before we go further, I need to loop in our engineering team. They're the ones who will actually run this equipment and their buy-in is critical.

Can we schedule a technical demo? I'd like to bring 3-4 of our machinists to see the Brother Speedio in action.

Do you have a demo facility nearby, or could we visit a customer site?

Patricia Dunn
Purchasing Manager, Dunn Manufacturing
Note: I handle procurement but the floor decides on equipment""",
                "is_urgent": False,
                "urgency_score": 55,
                "urgency_reason": "Need to involve technical decision makers",
                "hours_ago": 40
            },

            # ============================================
            # COMPETITOR MENTIONS
            # ============================================
            {
                "sender": "mark.stevens@stevensprecision.com",
                "sender_name": "Mark Stevens",
                "subject": "Comparing Major Manufacturers to Grainger Industrial",
                "body_text": """Marcus,

We've been a Grainger customer for 20 years and they're pushing hard to keep our business on this CNC purchase.

What makes Major Manufacturers different? They're offering similar specs at a lower price point.

I'm open to switching if the value is there, but I need to understand what we're getting for the premium.

Mark Stevens
Stevens Precision Engineering""",
                "is_urgent": False,
                "urgency_score": 60,
                "urgency_reason": "Competitive situation with established incumbent",
                "hours_ago": 20
            },
            {
                "sender": "rachel.green@greenindustries.com",
                "sender_name": "Rachel Green",
                "subject": "Your Turn-Key Solution vs Buying Components Separately",
                "body_text": """Hi Marcus,

I'm torn between your integrated automation cell and piecing together a solution from individual vendors.

Your system is $200K more expensive, but I understand there are integration benefits. Can you quantify those?

We've had bad experiences with "integration nightmares" before where different vendors pointed fingers at each other.

Rachel Green
CEO, Green Industries
50-person precision machine shop""",
                "is_urgent": False,
                "urgency_score": 58,
                "urgency_reason": "Build vs buy decision, concerned about integration",
                "hours_ago": 30
            },

            # ============================================
            # SERVICE & SUPPORT REQUESTS
            # ============================================
            {
                "sender": "maintenance@acmeprecision.com",
                "sender_name": "ACME Precision Maintenance",
                "subject": "URGENT: Spindle Error on Mori NLX - Production Down",
                "body_text": """EMERGENCY SERVICE REQUEST

Customer: ACME Precision Parts
Contact: Joe Martinez (Floor Supervisor)
Phone: (555) 123-4567

Equipment: DMG MORI NLX 2500/700
Serial: NLX-2024-00847
Issue: Spindle alarm code 1584, machine stopped, cannot restart

Production Status: CRITICAL - Line down
Customer says they have $100K of parts due to Boeing by Friday

Contract: Gold Service Agreement (4-hour response)

Please dispatch immediately.

ACME Precision Maintenance Team""",
                "is_urgent": True,
                "urgency_score": 95,
                "urgency_reason": "Emergency service call, production down, major customer deadline",
                "hours_ago": 1
            },
            {
                "sender": "mike.russo@russomachine.com",
                "sender_name": "Mike Russo",
                "subject": "Scheduling Annual PM for Our Haas Fleet",
                "body_text": """Hi Marcus,

We need to schedule our annual preventive maintenance for the five Haas machines we bought through Major Manufacturers.

Ideally we'd do this during our holiday shutdown (Dec 23 - Jan 2).

Can your service team handle all five in that window? Here's what we have:
- 2x VF-2SS (2021)
- 2x ST-25Y (2022)
- 1x UMC-750 (2023)

Also, the UMC is due for its spindle bearing service - wanted to get that done at the same time.

Mike Russo
Russo Machine Works""",
                "is_urgent": False,
                "urgency_score": 50,
                "urgency_reason": "Routine PM scheduling request",
                "hours_ago": 52
            },
            {
                "sender": "sarah.patel@patelmfg.com",
                "sender_name": "Sarah Patel",
                "subject": "Training Request - New Operator on Mazak",
                "body_text": """Marcus,

We just hired a new CNC operator and need to get him trained on our Mazak INTEGREX i-200.

He has experience on basic lathes but nothing with live tooling or Y-axis capability.

Does your training program cover this? How long is the course and what's the cost?

He's available to travel to your facility in January.

Sarah Patel
HR Manager, Patel Manufacturing""",
                "is_urgent": False,
                "urgency_score": 40,
                "urgency_reason": "Training request for existing customer",
                "hours_ago": 60
            },

            # ============================================
            # PARTS & CONSUMABLES
            # ============================================
            {
                "sender": "purchasing@precisioncomponents.com",
                "sender_name": "Precision Components Purchasing",
                "subject": "Quote Request - Tooling Package for New Okuma",
                "body_text": """Hi Marcus,

Following up on our recent Okuma LB3000 purchase - we need to order the initial tooling package.

Please quote:
- Complete live tool set (12 stations)
- Collet chuck system (5C)
- Bar feeder interface
- Chip conveyor extension

When can you have pricing? We want to order everything together for a single shipment.

Purchasing Department
Precision Components Inc.""",
                "is_urgent": False,
                "urgency_score": 55,
                "urgency_reason": "Accessories order for recent equipment purchase",
                "hours_ago": 22
            },
            {
                "sender": "shop@atlanticmachine.com",
                "sender_name": "Atlantic Machine Shop",
                "subject": "Coolant System Upgrade Options",
                "body_text": """Marcus,

Our Brother TC-32BN is performing great but we're running into issues with the coolant system on some of our harder materials.

What are our options for upgrading to high-pressure through-spindle coolant? We're machining a lot of Inconel now for aerospace work.

Is this something your service team can retrofit, or would we need to trade up to a different machine?

Atlantic Machine Shop
Tom Brennan (Floor Lead)""",
                "is_urgent": False,
                "urgency_score": 45,
                "urgency_reason": "Upgrade inquiry, expanding capabilities",
                "hours_ago": 38
            },

            # ============================================
            # RFQ / NEW INQUIRIES
            # ============================================
            {
                "sender": "rfq@defensecontractor.com",
                "sender_name": "Defense Contractor RFQ",
                "subject": "RFQ-2024-1892: Multi-Axis Machining Center",
                "body_text": """REQUEST FOR QUOTATION

RFQ Number: RFQ-2024-1892
Due Date: December 20, 2024

Scope: Supply of one (1) 5-Axis Vertical Machining Center for aerospace component production.

Specifications:
- Table size: minimum 40" x 20"
- Spindle: 20,000 RPM minimum
- Tool capacity: 60+ positions
- Full 5-axis simultaneous capability
- Must be USA/NATO country origin

Requirements:
- ITAR compliant facility
- 24-month warranty minimum
- On-site installation and training
- 5-year service availability guarantee

Submit proposals to procurement@defensecontractor.com

Defense Contractor Inc.
Procurement Department""",
                "is_urgent": True,
                "urgency_score": 75,
                "urgency_reason": "Formal RFQ with near deadline, defense industry",
                "hours_ago": 4
            },
            {
                "sender": "engineering@techinnovate.com",
                "sender_name": "Tech Innovate Engineering",
                "subject": "Looking for Turn-Key Production Cell",
                "body_text": """Hello,

We're a startup scaling up production of our IoT sensor housings. Currently we're 3D printing everything but need to move to CNC for production volumes.

Looking for a turn-key solution that can:
- Machine aluminum 6061 and some plastics
- Run unmanned overnight (lights out)
- Produce 500-1000 parts per week
- Fit in a 20x20 foot space

What would you recommend? We're venture-backed with $5M in Series A, so budget is available for the right solution.

Tech Innovate Engineering Team
Silicon Valley, CA""",
                "is_urgent": False,
                "urgency_score": 70,
                "urgency_reason": "New lead, startup with funding, clear requirements",
                "hours_ago": 10
            },
            {
                "sender": "facilities@universityeng.edu",
                "sender_name": "University Engineering Dept",
                "subject": "Quote Request for Teaching Lab Equipment",
                "body_text": """Dear Major Manufacturers,

Our university is upgrading our manufacturing engineering lab and seeking quotes for educational CNC equipment.

We're looking for:
- 2x Entry-level CNC mills (educational features important)
- 1x CNC lathe with live tooling capability
- Software licenses for 20 student seats

We have state grant funding that must be spent by June 30, 2025.

Please advise on educational pricing programs and if you offer curriculum support.

Dr. William Chen
Department of Manufacturing Engineering
State University""",
                "is_urgent": False,
                "urgency_score": 55,
                "urgency_reason": "Educational sale, grant funded, defined timeline",
                "hours_ago": 44
            },

            # ============================================
            # EXISTING CUSTOMER - EXPANSION
            # ============================================
            {
                "sender": "operations@reliablemachine.com",
                "sender_name": "Reliable Machine Operations",
                "subject": "Ready to Expand - Adding Second Shift",
                "body_text": """Marcus,

Great news - we landed the Caterpillar contract we've been chasing!

We need to add capacity fast. Thinking about duplicating our current cell (the Doosan you sold us in 2022).

Can you get me pricing on an identical setup? Also interested in exploring automation this time - we couldn't justify it before but with the guaranteed volume, it makes sense now.

Let's talk this week.

Jim Patterson
VP Operations, Reliable Machine Corp
Your customer since 2018""",
                "is_urgent": True,
                "urgency_score": 80,
                "urgency_reason": "Existing customer, expansion opportunity, new major contract",
                "hours_ago": 7
            },
            {
                "sender": "quality@aerospacedynamics.com",
                "sender_name": "Aerospace Dynamics Quality",
                "subject": "Adding CMM Capability - Follow Up",
                "body_text": """Hi Marcus,

Following up on our conversation at the aerospace supplier conference.

We've been your customer for the machining side (3 Makino cells) but now need to bring inspection in-house. Currently outsourcing CMM work at $15K/month.

Can you put together options for us? We'd want something that integrates with our existing Makino automation.

Also, any chance of a package deal since we're already a Major Manufacturers customer?

Quality Engineering
Aerospace Dynamics LLC""",
                "is_urgent": False,
                "urgency_score": 65,
                "urgency_reason": "Existing customer cross-sell opportunity",
                "hours_ago": 26
            },

            # ============================================
            # TRADE-IN / UPGRADE
            # ============================================
            {
                "sender": "owner@customfab.com",
                "sender_name": "Custom Fab Owner",
                "subject": "Trade-In Value on Old Equipment?",
                "body_text": """Marcus,

We're looking at upgrading our shop. Have some older equipment we'd like to trade:
- 1998 Cincinnati Arrow 750 VMC
- 2005 Haas SL-20 lathe
- 2008 Amada RG-50 press brake

What kind of trade-in value could we get if we're buying new equipment from Major Manufacturers?

Looking to spend around $400K on new machines if the trade-in values make sense.

Custom Fabrication LLC
Frank Davis, Owner""",
                "is_urgent": False,
                "urgency_score": 52,
                "urgency_reason": "Trade-in inquiry, potential multiple machine sale",
                "hours_ago": 56
            },
            {
                "sender": "ceo@growthmanufacturing.com",
                "sender_name": "Growth Manufacturing CEO",
                "subject": "Planning Major Capital Upgrade - 2025",
                "body_text": """Marcus,

We're planning a significant modernization of our facility in 2025. Budget is $3-4M.

Want to start the conversation now about:
1. Replacing our aging Fadal fleet (8 machines)
2. Adding automation capability
3. Improving our quality inspection
4. Getting into 5-axis for new market opportunities

Can we schedule a facility assessment? I want your team to see what we have and recommend a roadmap.

Growth Manufacturing Inc.
800,000 sq ft facility
$75M annual revenue""",
                "is_urgent": False,
                "urgency_score": 72,
                "urgency_reason": "Major capital planning, large potential deal",
                "hours_ago": 32
            },

            # ============================================
            # INTERNAL COMMUNICATIONS
            # ============================================
            {
                "sender": "sales.manager@majormanufacturers.com",
                "sender_name": "Regional Sales Manager",
                "subject": "Q4 Push - Bonus Accelerator Active",
                "body_text": """Team,

Reminder that our Q4 bonus accelerator kicks in at 110% of quota. We're at 94% as a region.

Priority accounts to close before Dec 31:
- Precision Aerospace ($425K) - Marcus, this is yours
- Global Automotive ($650K) - Working with you on FANUC deal
- Midwest Precision ($380K emergency) - HOT LEAD

Factory incentives available:
- Additional 2% on Okuma
- 5% on DMG MORI NLX series
- Demo inventory at 15% discount

Let's finish strong!

Regional Sales Manager
Major Manufacturers Inc.""",
                "is_urgent": False,
                "urgency_score": 60,
                "urgency_reason": "Internal sales push, quota tracking",
                "hours_ago": 14
            },
            {
                "sender": "product.manager@majormanufacturers.com",
                "sender_name": "Product Manager",
                "subject": "New Mazak INTEGREX i-500 Now Available",
                "body_text": """Sales Team,

Excited to announce we now have allocation for the new Mazak INTEGREX i-500 series.

Key selling points:
- 40% faster cycle times vs previous generation
- New CNC control with AI-assisted programming
- Improved energy efficiency (important for California customers)
- Extended spindle warranty (3 years standard)

First units available March 2025. Taking pre-orders now.

Let me know if you need technical specs or comparison sheets.

Product Management
Major Manufacturers Inc.""",
                "is_urgent": False,
                "urgency_score": 35,
                "urgency_reason": "Internal product announcement",
                "hours_ago": 68
            },
            {
                "sender": "credit@majormanufacturers.com",
                "sender_name": "Credit Department",
                "subject": "Credit Approval - Thompson Machine & Tool",
                "body_text": """Marcus,

Credit review completed for Thompson Machine & Tool.

Approved: $200,000 equipment financing
Terms: 60 months, 7.9% APR
Down payment: 10% required
Conditions: Personal guarantee from owner

This is a marginal credit - recommend getting deposit before ordering equipment.

Let me know if you need anything else for this deal.

Credit Department
Major Manufacturers Inc.""",
                "is_urgent": False,
                "urgency_score": 45,
                "urgency_reason": "Internal credit approval notification",
                "hours_ago": 42
            },

            # ============================================
            # MARKETING / LEAD GEN
            # ============================================
            {
                "sender": "events@majormanufacturers.com",
                "sender_name": "Events Team",
                "subject": "FABTECH 2025 Booth Assignments",
                "body_text": """Sales Team,

Booth assignments for FABTECH 2025 (Chicago, Sept 8-11):

Major Manufacturers Booth #A1847 (Corner position!)

Equipment displayed:
- DMG MORI NLX 2500
- Mazak OPTIPLEX Fiber Laser
- FANUC Robotic Welding Demo
- Hexagon CMM

Your scheduled booth times will follow. Please submit your VIP customer invitations by August 1.

Let's make this our biggest show yet!

Events Team
Major Manufacturers Inc.""",
                "is_urgent": False,
                "urgency_score": 25,
                "urgency_reason": "Trade show planning",
                "hours_ago": 96
            },
            {
                "sender": "webinar@majormanufacturers.com",
                "sender_name": "Marketing Webinars",
                "subject": "Webinar Lead Alert - Automation ROI Calculator Download",
                "body_text": """NEW LEAD ALERT

Contact: Eric Vandenberg
Company: Vandenberg Tool & Die
Email: eric@vandenbergtool.com
Phone: (616) 555-3456

Downloaded: Automation ROI Calculator
Pages Visited:
- Robotic Machine Tending
- FANUC Product Page
- Customer Case Studies

Lead Score: 72/100
Assignment: Marcus Chen (Michigan territory)

Please follow up within 24 hours.

Marketing Automation
Major Manufacturers Inc.""",
                "is_urgent": False,
                "urgency_score": 58,
                "urgency_reason": "Marketing qualified lead",
                "hours_ago": 9
            },

            # ============================================
            # COLD LEADS / EARLY STAGE
            # ============================================
            {
                "sender": "info@newstartupmanufacturing.com",
                "sender_name": "New Startup Manufacturing",
                "subject": "Just Starting Out - Equipment Advice?",
                "body_text": """Hello,

We're a new machine shop just getting started. Two partners, both experienced machinists, starting our own business.

We have about $300K in startup capital for equipment. What would you recommend for a general job shop setup?

We don't have any customers yet but have good industry connections in automotive.

New Startup Manufacturing
Detroit, MI""",
                "is_urgent": False,
                "urgency_score": 40,
                "urgency_reason": "New startup, exploratory stage",
                "hours_ago": 80
            },
            {
                "sender": "research@academiclab.edu",
                "sender_name": "Academic Research Lab",
                "subject": "Inquiry About Research Collaboration",
                "body_text": """Dear Major Manufacturers,

Our research lab is investigating advanced machining processes for next-generation materials.

We're interested in whether Major Manufacturers has any equipment loan or partnership programs for academic research.

Our work has been published in Journal of Manufacturing Science and we have DOD funding.

Is this something you'd consider?

Dr. Sarah Mitchell
Advanced Manufacturing Research Lab
Research University""",
                "is_urgent": False,
                "urgency_score": 30,
                "urgency_reason": "Academic inquiry, non-standard opportunity",
                "hours_ago": 120
            },

            # ============================================
            # FOLLOW-UP NEEDED
            # ============================================
            {
                "sender": "gone.quiet@silentprospect.com",
                "sender_name": "Silent Prospect",
                "subject": "RE: RE: RE: Quote Follow Up",
                "body_text": """Marcus,

Sorry for going dark. Things got crazy here.

Still interested but the project got pushed to next quarter. Can you refresh the quote with current pricing?

Also, any year-end specials I should know about?

Will try to have a decision by January.

Silent Prospect Inc.""",
                "is_urgent": False,
                "urgency_score": 48,
                "urgency_reason": "Prospect re-engaging after going silent",
                "hours_ago": 15
            },
            {
                "sender": "office@oldquote.com",
                "sender_name": "Old Quote Customer",
                "subject": "Question About Quote from 6 Months Ago",
                "body_text": """Marcus,

I know this is an old conversation, but we're finally ready to revisit that Okuma lathe quote from June.

Is that price still valid? Our situation has stabilized and we have budget available now.

Let me know if we need to start fresh or if you can just update the existing quote.

Old Quote Customer
Originally quoted $275,000""",
                "is_urgent": False,
                "urgency_score": 55,
                "urgency_reason": "Reviving old opportunity",
                "hours_ago": 11
            },

            # ============================================
            # ADDITIONAL EMAILS TO REACH 75
            # ============================================
            {
                "sender": "safety@oshaaudit.com",
                "sender_name": "OSHA Compliance",
                "subject": "Equipment Safety Certification Required - Customer Site",
                "body_text": """Major Manufacturers,

During a recent inspection at one of your customer sites (Precision Parts LLC), we noted the following equipment requires updated safety documentation:

Equipment: Haas VF-4 VMC (sold through Major Manufacturers)
Issue: Emergency stop circuit documentation needed
Customer: Precision Parts LLC

Please provide:
1. CE/UL certification documentation
2. Emergency stop circuit diagram
3. Safety interlock specifications

Required by: December 31, 2024

OSHA Compliance Division""",
                "is_urgent": True,
                "urgency_score": 70,
                "urgency_reason": "Compliance deadline, customer issue",
                "hours_ago": 34
            },
            {
                "sender": "warranty@majormanufacturers.com",
                "sender_name": "Warranty Claims",
                "subject": "Extended Warranty Renewal Due - Collins Manufacturing",
                "body_text": """Warranty Renewal Notice

Customer: Collins Manufacturing
Equipment: DMG MORI CMX 800 V
Serial: CMX-2021-00234
Current Coverage: Expires January 15, 2025

Renewal Options:
1. Bronze (Parts only): $8,500/year
2. Silver (Parts + Labor): $15,000/year
3. Gold (All-inclusive + PM): $22,000/year

Customer contact: Tim Collins, tim@collinsmfg.com

Please reach out for renewal discussion.

Warranty Department
Major Manufacturers Inc.""",
                "is_urgent": False,
                "urgency_score": 55,
                "urgency_reason": "Warranty renewal opportunity",
                "hours_ago": 46
            },
            {
                "sender": "logistics@shippingupdate.com",
                "sender_name": "Shipping Logistics",
                "subject": "Delivery Delay Notice - Nakamura-Tome Equipment",
                "body_text": """SHIPPING UPDATE

Order: MM-PO-2024-4521
Customer: Advanced Machining Solutions
Equipment: Nakamura-Tome WT-150II

Original Delivery: December 15, 2024
Revised Delivery: January 5, 2025

Reason: Port congestion in Long Beach

Customer has been notified but may have questions. Please follow up to maintain relationship.

Logistics Department""",
                "is_urgent": True,
                "urgency_score": 65,
                "urgency_reason": "Delivery delay requiring customer communication",
                "hours_ago": 6
            },
            {
                "sender": "andy.white@whitebrothers.com",
                "sender_name": "Andy White",
                "subject": "Recommendation Request - Best VMC for Aluminum",
                "body_text": """Hi Marcus,

We're an aluminum extrusion company looking to add in-house machining capability.

90% of our work will be aluminum 6061-T6, some with anodizing, tight tolerances.

What would you recommend? Budget is around $175K. High spindle speed is important to us.

Also, do you have any aerospace customers doing similar work we could visit?

Andy White
White Brothers Extrusions
Phoenix, AZ""",
                "is_urgent": False,
                "urgency_score": 60,
                "urgency_reason": "New lead with specific requirements",
                "hours_ago": 19
            },
            {
                "sender": "beth.crawford@crawfordind.com",
                "sender_name": "Beth Crawford",
                "subject": "Adding Wire EDM Capability",
                "body_text": """Marcus,

We've been outsourcing wire EDM work and it's killing our lead times.

Looking to bring this in-house. We're a precision mold shop, typical work is tool steel, tolerances of +/- 0.0001".

What's your Sodick vs Mitsubishi recommendation? Pros and cons?

We need something reliable - can't afford downtime when molds are due.

Beth Crawford
Crawford Industries - Tool & Die Division
ISO 9001:2015, IATF 16949""",
                "is_urgent": False,
                "urgency_score": 58,
                "urgency_reason": "Qualified lead, specific technology need",
                "hours_ago": 27
            },
            {
                "sender": "charlie.nguyen@nguyenprecision.com",
                "sender_name": "Charlie Nguyen",
                "subject": "Looking at Swiss-Type Machines",
                "body_text": """Hi Marcus,

We're getting into medical component manufacturing and need Swiss-type capability.

Currently quoting on a contract for titanium bone screws - 50,000 pieces per year.

What Swiss machines do you carry? We need something that can handle titanium efficiently.

Also interested in understanding what certifications we'd need (ISO 13485?).

Charlie Nguyen
Nguyen Precision Manufacturing
Currently: General job shop
Target: Medical components""",
                "is_urgent": False,
                "urgency_score": 65,
                "urgency_reason": "Market expansion opportunity, specific contract pending",
                "hours_ago": 23
            },
            {
                "sender": "dan.kowalski@kowalskitool.com",
                "sender_name": "Dan Kowalski",
                "subject": "Upgrading Our CAM Software",
                "body_text": """Marcus,

When we bought our Mazak from you, it came with basic Mazatrol programming.

Now we're looking at more complex 5-axis work and need better CAM software.

Do you sell/support Mastercam or Hypermill? Or is there something else you'd recommend for our Mazak VARIAXIS i-700?

Want to make sure whatever we buy is optimized for our machine.

Dan Kowalski
Kowalski Tool & Engineering""",
                "is_urgent": False,
                "urgency_score": 45,
                "urgency_reason": "Software upgrade inquiry, existing customer",
                "hours_ago": 54
            },
            {
                "sender": "elena.volkov@volkovmfg.com",
                "sender_name": "Elena Volkov",
                "subject": "Energy Efficiency - New Machine vs Retrofit",
                "body_text": """Hi Marcus,

Our utility bills are killing us. Looking at options to reduce energy consumption in our shop.

We have three older machines (2005-2010 vintage).

Question: Is it more cost-effective to:
A) Retrofit with VFDs and efficient motors
B) Replace with modern machines

Also interested in any green manufacturing incentives you know about.

Elena Volkov
Volkov Manufacturing
$2M+ annual electricity cost""",
                "is_urgent": False,
                "urgency_score": 50,
                "urgency_reason": "Operational cost reduction inquiry",
                "hours_ago": 62
            },
            {
                "sender": "fred.jackson@jacksonworks.com",
                "sender_name": "Fred Jackson",
                "subject": "Succession Planning - Automating Before I Retire",
                "body_text": """Marcus,

I'm 62 and starting to think about retirement. Want to automate my shop so it can run without my 40 years of knowledge.

We're a 10-person shop, mostly manual machines with a couple old CNCs.

My goal: Get to a point where my son-in-law can run things without me, even though he's not a machinist.

What kind of automation investment are we looking at? And is this realistic?

Fred Jackson
Jackson Machine Works
Started this place in 1985""",
                "is_urgent": False,
                "urgency_score": 55,
                "urgency_reason": "Succession planning opportunity, major transformation",
                "hours_ago": 76
            },
            {
                "sender": "grace.kim@kimstamping.com",
                "sender_name": "Grace Kim",
                "subject": "Deburring & Finishing Equipment Needed",
                "body_text": """Hi Marcus,

Our stamping operation creates parts that need secondary deburring. Currently doing this by hand - very labor intensive.

Looking for automated deburring solutions. We process:
- Steel stampings, 0.060" to 0.125" thick
- 10,000+ parts per day
- Various geometries

What do you have in this space?

Grace Kim
Kim Stamping & Fabrication
Tier 2 automotive""",
                "is_urgent": False,
                "urgency_score": 52,
                "urgency_reason": "Secondary equipment need, high volume",
                "hours_ago": 43
            },
            {
                "sender": "henry.adams@adamswelding.com",
                "sender_name": "Henry Adams",
                "subject": "Robotic Welding for Small Batch Work?",
                "body_text": """Marcus,

Is robotic welding viable for job shop work? We do small batches (10-50 pieces) of structural weldments.

I've heard robots only make sense for high volume, but I'm seeing new offline programming that might change that.

What's your honest opinion? Our average batch size is 25 pieces, maybe 50 different part numbers per month.

Henry Adams
Adams Welding & Fabrication
Union shop, $15M revenue""",
                "is_urgent": False,
                "urgency_score": 48,
                "urgency_reason": "Technology exploration, skeptical prospect",
                "hours_ago": 88
            },
            {
                "sender": "irene.baker@bakerprecision.com",
                "sender_name": "Irene Baker",
                "subject": "URGENT: Need Quote by Tomorrow - Government Deadline",
                "body_text": """Marcus,

We're responding to a government RFQ and need an equipment quote as part of our proposal.

The prime contractor deadline is tomorrow at 3 PM EST.

Can you get me formal pricing on:
- Doosan DVF 5000 5-axis VMC
- 2-year extended warranty
- Installation and training

I know this is last minute - I'll owe you one!

Irene Baker
Baker Precision Machining
GSA Schedule holder""",
                "is_urgent": True,
                "urgency_score": 85,
                "urgency_reason": "Urgent quote needed for government proposal",
                "hours_ago": 8
            },
            {
                "sender": "jack.rivers@riversindustrial.com",
                "sender_name": "Jack Rivers",
                "subject": "Starting a Second Location - Equipment Needs",
                "body_text": """Hi Marcus,

We're opening a second facility in Guadalajara, Mexico to be closer to our automotive customers.

Need to outfit it with the same capabilities as our Ohio plant:
- 4x VMCs
- 2x HMCs
- 2x Lathes with live tooling
- CMM

What does that look like from a budget standpoint? And can you support equipment in Mexico?

Jack Rivers
Rivers Industrial
Expanding to nearshoring market""",
                "is_urgent": False,
                "urgency_score": 70,
                "urgency_reason": "Major expansion opportunity, multiple machines",
                "hours_ago": 17
            },
            {
                "sender": "karen.lee@leemachinery.com",
                "sender_name": "Karen Lee",
                "subject": "Replacing Our Burned Down Shop Equipment",
                "body_text": """Marcus,

Terrible news - we had a fire last month. Total loss of our machining area.

Insurance is covering replacement at current value. We need to rebuild from scratch.

This is actually an opportunity to modernize. What would you recommend for a shop doing:
- Aerospace components (AS9100 work)
- Volumes of 100-500 pieces per order
- Aluminum and titanium primarily

Our insurance settlement is $1.8M for equipment.

Karen Lee
Lee Machinery
Rebuilding in 2025""",
                "is_urgent": True,
                "urgency_score": 78,
                "urgency_reason": "Urgent rebuild situation, large budget",
                "hours_ago": 21
            },
            {
                "sender": "larry.morgan@morgantools.com",
                "sender_name": "Larry Morgan",
                "subject": "Tool Presetter Recommendations",
                "body_text": """Hi Marcus,

We're setting up tool length and diameter offline to reduce setup time at the machine.

What tool presetting equipment do you recommend? We have a mix of CAT40 and HSK63 tooling.

Budget is around $35K. Accuracy requirement is +/- 0.0001".

Larry Morgan
Morgan Tool Company""",
                "is_urgent": False,
                "urgency_score": 42,
                "urgency_reason": "Accessory equipment inquiry",
                "hours_ago": 66
            },
            {
                "sender": "mary.jones@joneseng.com",
                "sender_name": "Mary Jones",
                "subject": "RE: Automation Demo - Very Impressed!",
                "body_text": """Marcus,

Thank you for the tour of your demo facility yesterday. Our team was very impressed with the automated cell.

We'd like to move forward with a formal proposal. Can you include:
- The Okuma MB-5000H with pallet system we saw
- Integration costs
- Timeline
- ROI projections based on our current situation

We're targeting implementation for summer 2025.

Mary Jones
VP of Operations, Jones Engineering
Toured with our CTO and Floor Supervisor""",
                "is_urgent": False,
                "urgency_score": 72,
                "urgency_reason": "Post-demo follow-up, ready for proposal",
                "hours_ago": 13
            },
            {
                "sender": "nick.santini@santiniaerospace.com",
                "sender_name": "Nick Santini",
                "subject": "Nadcap Preparation - Equipment Requirements",
                "body_text": """Hi Marcus,

We're pursuing Nadcap certification for heat treat and chemical processing.

I've been told there are specific equipment documentation and calibration requirements.

Can you help ensure our Zeiss CMM (purchased through Major Manufacturers) has proper certification and calibration records for Nadcap?

Also, do you have experience with other shops going through Nadcap? Any advice?

Nick Santini
Quality Manager, Santini Aerospace
Targeting Nadcap certification Q2 2025""",
                "is_urgent": False,
                "urgency_score": 55,
                "urgency_reason": "Certification support request",
                "hours_ago": 37
            },
            {
                "sender": "olivia.chen@chensolutions.com",
                "sender_name": "Olivia Chen",
                "subject": "Smart Factory / Industry 4.0 Questions",
                "body_text": """Marcus,

Our company is pushing a "Smart Factory" initiative. My job is to figure out what that actually means for our machining department.

Questions:
1. What IIoT/data collection comes standard on new machines?
2. What can be retrofitted to our existing fleet?
3. How do we connect everything to our ERP system?
4. What are other shops doing with this data?

I feel like I'm drinking from a fire hose with all the buzzwords. Help!

Olivia Chen
Continuous Improvement Manager, Chen Solutions
6 Sigma Black Belt""",
                "is_urgent": False,
                "urgency_score": 50,
                "urgency_reason": "Industry 4.0 inquiry, internal initiative",
                "hours_ago": 51
            },
            {
                "sender": "paul.taylor@taylorparts.com",
                "sender_name": "Paul Taylor",
                "subject": "Micro-Machining Capabilities?",
                "body_text": """Hi Marcus,

We're getting requests for micro-features that our current equipment can't handle.

Talking tolerances under 0.0005" and feature sizes around 0.010".

Do you carry equipment for micro-machining? We're in the medical and electronics space.

What kind of environment (temperature controlled?) do we need?

Paul Taylor
Taylor Precision Parts
Looking to enter micro-machining market""",
                "is_urgent": False,
                "urgency_score": 58,
                "urgency_reason": "Specialty capability inquiry, new market entry",
                "hours_ago": 74
            },
            {
                "sender": "quinn.murphy@murphymachine.com",
                "sender_name": "Quinn Murphy",
                "subject": "Consolidating Vendors - Your Chance",
                "body_text": """Marcus,

We currently buy from 6 different equipment vendors. It's a headache for service and parts.

Considering consolidating to 2-3 vendors max. Major Manufacturers is on my short list.

What would it take to make you our primary partner? We spend about $500K/year on new equipment and $100K on service/parts.

Looking for:
- Competitive pricing
- Single point of contact
- Streamlined service
- Inventory management help

Quinn Murphy
Purchasing Director, Murphy Machine Corp
$80M manufacturer""",
                "is_urgent": False,
                "urgency_score": 68,
                "urgency_reason": "Strategic partnership opportunity",
                "hours_ago": 29
            },
            {
                "sender": "roger.simmons@simmonsgroup.com",
                "sender_name": "Roger Simmons",
                "subject": "Visiting Your Facility - Partner Evaluation",
                "body_text": """Hi Marcus,

The Simmons Group is evaluating equipment partners for our portfolio of 12 manufacturing companies.

We'd like to visit Major Manufacturers to assess:
- Demo capabilities
- Service infrastructure
- Technical support
- Financial stability

We spend $5-8M annually across our companies on capital equipment.

Can you arrange a comprehensive visit for our operations team?

Roger Simmons
COO, The Simmons Group
Private equity manufacturing portfolio""",
                "is_urgent": False,
                "urgency_score": 75,
                "urgency_reason": "Major strategic opportunity, PE group",
                "hours_ago": 18
            },
            {
                "sender": "steve.reynolds@reynoldsind.com",
                "sender_name": "Steve Reynolds",
                "subject": "Disappointed with Recent Purchase",
                "body_text": """Marcus,

I need to vent. The Doosan DNM 5700 we bought 3 months ago has been down twice for major repairs.

I trusted Major Manufacturers' recommendation and now I'm questioning that decision.

What are you going to do to make this right? My team is losing confidence and we have production to meet.

Steve Reynolds
Reynolds Industries
Very frustrated customer""",
                "is_urgent": True,
                "urgency_score": 80,
                "urgency_reason": "Customer complaint requiring immediate attention",
                "hours_ago": 5
            },
            {
                "sender": "tina.brooks@brooksmetals.com",
                "sender_name": "Tina Brooks",
                "subject": "Thank You for the Great Service!",
                "body_text": """Marcus,

Just wanted to send a note of appreciation.

When our Makino went down during our biggest production week, your service team had a tech on-site within 4 hours. He worked through the night to get us running.

That's the kind of partnership we value. Please share this with your service manager.

We'll definitely be coming back to Major Manufacturers for our next purchase.

Tina Brooks
Brooks Metals Manufacturing
Happy customer!""",
                "is_urgent": False,
                "urgency_score": 25,
                "urgency_reason": "Positive customer feedback",
                "hours_ago": 58
            },
            {
                "sender": "victor.hernandez@hernandezfab.com",
                "sender_name": "Victor Hernandez",
                "subject": "Considering First CNC Purchase",
                "body_text": """Hello Marcus,

I run a small fabrication shop (5 people) and we've always been manual machines. Looking to make the leap to CNC.

Honestly, I'm nervous. Biggest concerns:
- Learning curve for my team
- Ongoing maintenance costs
- Whether we have enough work to justify it

Our typical work is small batch steel and aluminum parts, tolerances around +/- 0.005".

Where do I even start?

Victor Hernandez
Hernandez Fabrication
First-time CNC buyer""",
                "is_urgent": False,
                "urgency_score": 45,
                "urgency_reason": "First-time CNC buyer, needs education",
                "hours_ago": 82
            },
            {
                "sender": "wendy.park@parkprecision.com",
                "sender_name": "Wendy Park",
                "subject": "Financing Approval Question",
                "body_text": """Hi Marcus,

We submitted our financing application last week for the Okuma LU3000 EX. Any update?

We're trying to finalize our capex plan for next year and this is a big piece of it.

Also, if we're approved, what's the earliest we could take delivery?

Wendy Park
Park Precision Engineering
Application submitted 12/5""",
                "is_urgent": False,
                "urgency_score": 52,
                "urgency_reason": "Financing follow-up, deal in progress",
                "hours_ago": 35
            },
            {
                "sender": "xavier.jones@jonesauto.com",
                "sender_name": "Xavier Jones",
                "subject": "EV Component Manufacturing Setup",
                "body_text": """Marcus,

We're repositioning our shop for the EV market. Currently tier 2 for ICE components but need to pivot.

Looking for equipment to machine:
- Battery enclosures (large aluminum)
- Motor housings
- Inverter cases

What's the right setup? We have space for 3-4 new machines.

This is strategic for us - ICE work is declining.

Xavier Jones
Jones Automotive Components
Making the EV transition""",
                "is_urgent": False,
                "urgency_score": 65,
                "urgency_reason": "Strategic market transition, multiple machine opportunity",
                "hours_ago": 24
            },
            {
                "sender": "yolanda.garcia@garciamfg.com",
                "sender_name": "Yolanda Garcia",
                "subject": "Women in Manufacturing Event Sponsorship",
                "body_text": """Hi Marcus,

I'm organizing a Women in Manufacturing networking event in March. Expecting 100+ attendees from local manufacturing companies.

Would Major Manufacturers be interested in sponsoring? Options:
- Gold ($5,000): Speaking slot + table
- Silver ($2,500): Table + logo
- Bronze ($1,000): Logo recognition

Great opportunity to build relationships with decision-makers.

Yolanda Garcia
Garcia Manufacturing
Women in Manufacturing Chapter President""",
                "is_urgent": False,
                "urgency_score": 30,
                "urgency_reason": "Sponsorship request, networking opportunity",
                "hours_ago": 90
            },
            {
                "sender": "zach.miller@millermachining.com",
                "sender_name": "Zach Miller",
                "subject": "Apprentice Program Question",
                "body_text": """Marcus,

We're starting an apprentice program and looking for equipment that's good for training.

Do you have any educational or entry-level machines that are more forgiving for new operators?

Also, do you offer any training partnerships? We want to set our apprentices up for success.

Zach Miller
Miller Machining
Investing in workforce development""",
                "is_urgent": False,
                "urgency_score": 40,
                "urgency_reason": "Educational/training inquiry",
                "hours_ago": 70
            },
        ]

        # Create emails
        for i, email_data in enumerate(emails_data):
            hours_ago = email_data.pop("hours_ago", 0)
            email = Email(
                id=str(uuid.uuid4()),
                user_id=test_user.id,
                gmail_id=f"demo-gmail-{i+1:04d}",
                subject=email_data["subject"],
                sender=email_data["sender"],
                sender_name=email_data["sender_name"],
                body_text=email_data["body_text"],
                snippet=email_data["body_text"][:100] + "...",
                is_urgent=email_data.get("is_urgent", False),
                urgency_score=email_data.get("urgency_score", 0),
                urgency_reason=email_data.get("urgency_reason"),
                has_attachments=email_data.get("has_attachments", False),
                is_read=email_data.get("is_read", hours_ago > 24),
                received_at=datetime.utcnow() - timedelta(hours=hours_ago),
                created_at=datetime.utcnow()
            )
            db.add(email)

        db.commit()

        # Print summary
        email_count = db.query(Email).filter(Email.user_id == test_user.id).count()
        urgent_count = db.query(Email).filter(
            Email.user_id == test_user.id,
            Email.is_urgent == True
        ).count()

        print(f"\n{'='*60}")
        print(f"DEMO DATA CREATED SUCCESSFULLY!")
        print(f"{'='*60}")
        print(f"\nUser Profile:")
        print(f"  Name: {test_user.name}")
        print(f"  Email: {test_user.email}")
        print(f"  Role: Senior Sales Executive")
        print(f"  Company: Major Manufacturers Inc.")
        print(f"\nEmail Stats:")
        print(f"  Total Emails: {email_count}")
        print(f"  Urgent Emails: {urgent_count}")
        print(f"\nBusiness Profile Created:")
        print(f"  Industry: Industrial Manufacturing")
        print(f"  Products: CNC Equipment, Robotics, Quality Inspection")
        print(f"  Avg Deal Size: $350,000")
        print(f"\nLogin: Use Demo Login button on the auth page")
        print(f"{'='*60}")

        # List some key senders
        print(f"\nKey Contacts for Testing:")
        hot_leads = ["robert.martinez@precisionaero.com", "jennifer.wong@globalautomotive.com",
                     "thomas.burke@midwestprecision.com", "amanda.foster@innovativemedical.com"]
        for sender in hot_leads:
            print(f"  HOT: {sender}")

        return test_user

    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    create_major_manufacturers_demo()
