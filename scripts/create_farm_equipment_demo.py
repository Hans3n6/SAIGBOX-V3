#!/usr/bin/env python3
"""
Create demo user with 75 sample emails for a farm equipment sales company.
Tests all SAIGBOX systems: urgency detection, action items, sales dashboard, BANT scoring, objections, etc.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
import uuid
from core.database import SessionLocal, User, Email, ActionItem, Base, engine

# Ensure tables exist
Base.metadata.create_all(engine)

def create_farm_equipment_demo():
    db = SessionLocal()

    try:
        # Check if test user already exists
        existing_user = db.query(User).filter(User.email == "testuser@demo.saigbox.com").first()
        if existing_user:
            print(f"Test user already exists: {existing_user.email}")
            print("Deleting existing test data to recreate...")
            db.query(ActionItem).filter(ActionItem.user_id == existing_user.id).delete()
            db.query(Email).filter(Email.user_id == existing_user.id).delete()
            db.query(User).filter(User.id == existing_user.id).delete()
            db.commit()

        # Create test user - Farm Equipment Sales Rep
        test_user = User(
            id=str(uuid.uuid4()),
            email="testuser@demo.saigbox.com",
            name="Jake Morrison",
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
        print("Role: Sales Representative at Prairie King Equipment")

        # 75 Farm Equipment Sales Emails
        emails_data = [
            # ============================================
            # HOT LEADS - Ready to buy (High BANT scores)
            # ============================================
            {
                "sender": "tom.whitfield@whitfieldranch.com",
                "sender_name": "Tom Whitfield",
                "subject": "Ready to Purchase - John Deere 8R 410 Tractor",
                "body_text": """Jake,

We've made our decision. We want to move forward with the John Deere 8R 410 you quoted us last month.

Our budget is approved at $385,000 and I have full authority to sign. We need delivery before spring planting starts - ideally by March 15th.

Can you send over the final paperwork today? I'd like to get this wrapped up by end of week.

Also, what financing options do you have for the extended warranty package?

Thanks,
Tom Whitfield
Owner, Whitfield Ranch
5,200 acres - Corn & Soybeans""",
                "is_urgent": True,
                "urgency_score": 95,
                "urgency_reason": "Hot lead ready to close, requesting paperwork today",
                "hours_ago": 1
            },
            {
                "sender": "maria.gonzalez@gonzalezfarms.com",
                "sender_name": "Maria Gonzalez",
                "subject": "RE: Case IH Combine Quote - Let's Finalize",
                "body_text": """Hi Jake,

Thank you for matching the competitor's price on the Case IH 9250 Axial-Flow. That sealed the deal for us.

We're ready to sign. My father (the owner) has approved the purchase and he'll be in town Thursday to finalize everything.

Quick questions:
1. Can we get the extended cab upgrade included at that price?
2. What's the delivery timeline?
3. Do you offer operator training?

Our harvest season starts in 4 months so timing is important.

Best,
Maria Gonzalez
Operations Manager, Gonzalez Farms""",
                "is_urgent": True,
                "urgency_score": 90,
                "urgency_reason": "Ready to sign, decision maker coming Thursday",
                "hours_ago": 3
            },
            {
                "sender": "bill.henderson@hendersondairy.com",
                "sender_name": "Bill Henderson",
                "subject": "Urgent: Need Kubota M7-172 This Week",
                "body_text": """Jake,

URGENT - Our main tractor broke down yesterday and we're in a bind.

We need the Kubota M7-172 we looked at last month. I know you said you had one in stock.

Budget isn't an issue - we'll pay full asking price. Can you deliver by Friday? We have 200 cows that need feeding and our backup is barely keeping up.

Call me ASAP.

Bill Henderson
Henderson Family Dairy
Direct: (555) 234-5678""",
                "is_urgent": True,
                "urgency_score": 98,
                "urgency_reason": "Emergency purchase needed immediately, livestock at risk",
                "hours_ago": 2
            },

            # ============================================
            # WARM LEADS - Interested, need nurturing
            # ============================================
            {
                "sender": "sarah.mitchell@blueridgefarm.com",
                "sender_name": "Sarah Mitchell",
                "subject": "Question About Financing Options",
                "body_text": """Hi Jake,

I enjoyed our conversation at the county fair last week. The New Holland T7.315 you showed me would be perfect for our operation.

My concern is the financing. We had a rough year with the drought and our credit took a hit. What options do you have for farmers in our situation?

We farm 1,800 acres of wheat and canola. The equipment would really help us expand.

Looking forward to your thoughts.

Sarah Mitchell
Blue Ridge Farm""",
                "is_urgent": False,
                "urgency_score": 65,
                "urgency_reason": "Qualified lead with financing concerns",
                "hours_ago": 8
            },
            {
                "sender": "james.carpenter@carpenterfamilyfarms.com",
                "sender_name": "James Carpenter",
                "subject": "Comparing Your Quote to Peterson Equipment",
                "body_text": """Jake,

Thanks for the quote on the Fendt 942 Vario. I have to be honest - Peterson Equipment came in about $15,000 lower.

I'd prefer to buy from you because of your service reputation, but I need to justify the cost to my business partner.

Is there anything you can do on pricing? Maybe throw in some implements or extended warranty?

Let me know by next Monday when we're making our final decision.

James Carpenter
Partner, Carpenter Family Farms
3,400 acres""",
                "is_urgent": True,
                "urgency_score": 75,
                "urgency_reason": "Price objection with competitor, decision Monday",
                "hours_ago": 12
            },
            {
                "sender": "robert.chen@chenorganics.com",
                "sender_name": "Robert Chen",
                "subject": "Interested in Precision Ag Technology",
                "body_text": """Hello Jake,

I was referred to you by my neighbor Dave Wilson. He mentioned you're knowledgeable about precision agriculture technology.

We're looking to upgrade our operation with GPS guidance systems and variable rate application technology. Budget is around $50,000-75,000 for the initial setup.

I don't have a specific timeline but we'd like to have something in place before next spring. Can you put together some options for us?

We run 2,100 acres of organic vegetables - tomatoes, peppers, and lettuce.

Thanks,
Robert Chen
Chen Organics""",
                "is_urgent": False,
                "urgency_score": 55,
                "urgency_reason": "Qualified lead, referred customer, flexible timeline",
                "hours_ago": 24
            },
            {
                "sender": "amanda.foster@fosterhay.com",
                "sender_name": "Amanda Foster",
                "subject": "RE: Hay Equipment Package",
                "body_text": """Jake,

I discussed the hay equipment package with my husband last night. We're interested but not sure about the timing.

The $125,000 package looks good, but we're wondering if we should wait until the fall when equipment prices typically drop. What do you think?

Also, my husband wants to see the New Holland BigBaler 340 in action. Do you have any demos coming up?

Thanks,
Amanda Foster
Foster Hay & Feed""",
                "is_urgent": False,
                "urgency_score": 50,
                "urgency_reason": "Interested but timing objection, needs demo",
                "hours_ago": 36
            },
            {
                "sender": "mike.turner@turnervineyards.com",
                "sender_name": "Mike Turner",
                "subject": "Specialized Equipment for Vineyard",
                "body_text": """Hi Jake,

I'm expanding our vineyard operation and need specialized narrow equipment. We've been looking at the Kubota M5N-111 Narrow series.

A few questions:
1. What's your lead time on specialty orders?
2. Can you get the vineyard attachment package?
3. Do you have experience with vineyard operations?

Our budget is flexible for the right solution. We're adding 80 acres of premium wine grapes.

Mike Turner
Turner Vineyards""",
                "is_urgent": False,
                "urgency_score": 60,
                "urgency_reason": "Niche customer with expansion plans, budget flexible",
                "hours_ago": 48
            },

            # ============================================
            # COLD LEADS - New inquiries
            # ============================================
            {
                "sender": "jennifer.lawson@lawsonfarms.com",
                "sender_name": "Jennifer Lawson",
                "subject": "First-time tractor buyer - need guidance",
                "body_text": """Hello,

I recently inherited my grandfather's farm (450 acres) and I'm completely new to farming equipment.

I need a tractor but have no idea where to start. What would you recommend for someone just getting started? Budget is probably around $75,000-100,000.

The farm has been mostly hay fields but I'm considering converting some to row crops.

Any guidance would be appreciated!

Jennifer Lawson""",
                "is_urgent": False,
                "urgency_score": 45,
                "urgency_reason": "New customer, early stage, needs education",
                "hours_ago": 72
            },
            {
                "sender": "david.park@parkandsonsfarm.com",
                "sender_name": "David Park",
                "subject": "Inquiry from website",
                "body_text": """Hi,

I found your dealership through your website. I'm looking for a used combine in the $150,000-200,000 range.

What do you currently have in inventory?

David Park
Park & Sons Farm""",
                "is_urgent": False,
                "urgency_score": 35,
                "urgency_reason": "Website inquiry, used equipment interest",
                "hours_ago": 96
            },
            {
                "sender": "lisa.wright@sunsetranch.net",
                "sender_name": "Lisa Wright",
                "subject": "Compact Tractor for Hobby Farm",
                "body_text": """Hi there,

My husband and I just bought a 50-acre hobby farm and we're looking for a compact tractor for general property maintenance.

We don't need anything fancy - just something reliable for mowing, moving hay bales, and light grading.

What do you have in the $25,000-40,000 range?

Thanks!
Lisa Wright""",
                "is_urgent": False,
                "urgency_score": 30,
                "urgency_reason": "Hobby farm customer, smaller sale potential",
                "hours_ago": 120
            },

            # ============================================
            # EXISTING CUSTOMERS - Service & Parts
            # ============================================
            {
                "sender": "steve.morrison@morrisongrain.com",
                "sender_name": "Steve Morrison",
                "subject": "URGENT: Combine Down - Need Parts ASAP",
                "body_text": """Jake,

Our main combine (the 2022 John Deere S790 you sold us) threw a belt and damaged the feeder house chain. We're in the middle of harvest and losing money every hour it's down.

Parts needed:
- Feeder house chain assembly (Part# H229538)
- Drive belt (Part# H232336)
- Feeder house sprocket (Part# H227866)

Can you get these overnighted? I don't care about the cost - we need this machine running by tomorrow morning.

Call me immediately.

Steve Morrison
(555) 345-6789 - call anytime""",
                "is_urgent": True,
                "urgency_score": 99,
                "urgency_reason": "Critical equipment down during harvest, revenue loss",
                "hours_ago": 0.5
            },
            {
                "sender": "patricia.newman@newmanfarms.com",
                "sender_name": "Patricia Newman",
                "subject": "Scheduled Maintenance Due on NH Tractor",
                "body_text": """Hi Jake,

The New Holland T8.435 we bought last year is coming up on its 500-hour service.

Can you schedule us for sometime next week? We'd also like you to look at a hydraulic leak on the front loader - it's minor but I want to get it fixed before it gets worse.

Tuesday or Wednesday works best for us.

Thanks,
Patricia Newman""",
                "is_urgent": False,
                "urgency_score": 40,
                "urgency_reason": "Routine maintenance scheduling",
                "hours_ago": 18
            },
            {
                "sender": "kevin.baker@bakerbrothers.com",
                "sender_name": "Kevin Baker",
                "subject": "Warranty Claim - GPS System Issues",
                "body_text": """Jake,

We've been having ongoing issues with the Trimble GPS system on our Case IH Magnum. This is the third time it's stopped working in 6 months.

The unit is still under warranty and frankly I'm getting frustrated. The last technician said it was fixed but the same error code came back yesterday.

I need someone who knows what they're doing to look at this. If we can't get it resolved, I want to discuss replacement options.

Please advise.

Kevin Baker
Baker Brothers Farms""",
                "is_urgent": True,
                "urgency_score": 70,
                "urgency_reason": "Frustrated customer, ongoing warranty issue",
                "hours_ago": 6
            },
            {
                "sender": "nancy.clark@clarkvalleyfarm.com",
                "sender_name": "Nancy Clark",
                "subject": "Annual Service Contract Renewal",
                "body_text": """Hi Jake,

Our annual service contract is coming up for renewal next month. Before I sign, I wanted to discuss a few things:

1. Can we add the skid steer to the contract?
2. Is there a discount for a 3-year commitment?
3. What's the response time guarantee for breakdowns?

Overall we've been happy with the service but I'm comparing against doing maintenance in-house.

Let me know when you have time to chat.

Nancy Clark
Clark Valley Farm""",
                "is_urgent": False,
                "urgency_score": 45,
                "urgency_reason": "Contract renewal discussion",
                "hours_ago": 48
            },

            # ============================================
            # OBJECTION EMAILS - Various types
            # ============================================
            {
                "sender": "richard.jones@jonesacres.com",
                "sender_name": "Richard Jones",
                "subject": "RE: Quote - Too Expensive",
                "body_text": """Jake,

I got your quote for the Massey Ferguson 8S.265 and honestly, it's more than I expected to spend.

$289,000 is a lot of money for a tractor. I've seen similar specs from other brands for $30-40k less.

What am I getting for the premium price? Can you help me understand the value?

Richard Jones
Jones Acres""",
                "is_urgent": False,
                "urgency_score": 55,
                "urgency_reason": "Price objection, needs value justification",
                "hours_ago": 30
            },
            {
                "sender": "carol.davis@davisfamilyfarm.com",
                "sender_name": "Carol Davis",
                "subject": "Need to talk to my husband",
                "body_text": """Hi Jake,

Thanks for the presentation yesterday. The Kubota M7-152 looks like it would work for us.

I need to discuss this with my husband before making any decisions. He handles the finances and he's pretty conservative about big purchases.

Can you send me some materials I can share with him? Maybe some customer testimonials from other farms our size?

I'll be in touch once we've talked it over.

Carol Davis""",
                "is_urgent": False,
                "urgency_score": 40,
                "urgency_reason": "Authority objection - not the decision maker",
                "hours_ago": 44
            },
            {
                "sender": "mark.thompson@thompsonranching.com",
                "sender_name": "Mark Thompson",
                "subject": "RE: Follow Up - Not Sure We Need It",
                "body_text": """Jake,

I've been thinking about the planter upgrade you proposed. Honestly, our current equipment is getting the job done fine.

I know the new technology is impressive, but is it really worth $85,000 when our old planter still works?

Convince me why we need to upgrade now rather than running our current equipment for another few years.

Mark Thompson
Thompson Ranching Co.""",
                "is_urgent": False,
                "urgency_score": 35,
                "urgency_reason": "Need objection - doesn't see necessity",
                "hours_ago": 60
            },
            {
                "sender": "brian.williams@williamsharvestllc.com",
                "sender_name": "Brian Williams",
                "subject": "Going with Peterson Equipment",
                "body_text": """Jake,

I wanted to let you know that we've decided to go with Peterson Equipment for the combine.

Their service team has been in business longer and several of my neighbors have had good experiences with them. With equipment this expensive, we want to go with someone we trust.

Nothing personal - I appreciate your time.

Brian Williams""",
                "is_urgent": False,
                "urgency_score": 20,
                "urgency_reason": "Trust/competitor objection - lost deal",
                "hours_ago": 72
            },
            {
                "sender": "susan.martinez@martinezfarms.com",
                "sender_name": "Susan Martinez",
                "subject": "RE: Sprayer Quote - Bad Timing",
                "body_text": """Jake,

The self-propelled sprayer looks great but the timing is terrible for us.

We just had to replace our irrigation system after the freeze and we're stretched thin financially. There's no way we can take on another major purchase this year.

Can we revisit this in 6 months? Maybe after harvest when our cash flow improves?

Susan Martinez
Martinez Farms""",
                "is_urgent": False,
                "urgency_score": 30,
                "urgency_reason": "Timing objection - financial constraints",
                "hours_ago": 84
            },

            # ============================================
            # INTERNAL EMAILS - Team & Management
            # ============================================
            {
                "sender": "jim.hartley@prairiekingequip.com",
                "sender_name": "Jim Hartley",
                "subject": "Monthly Sales Meeting - Tomorrow 9AM",
                "body_text": """Team,

Reminder: Monthly sales meeting tomorrow at 9 AM in the conference room.

Agenda:
1. Q4 quota review
2. New product training - John Deere ExactEmerge planters
3. Holiday promotion planning
4. Pipeline review

Please come prepared with your:
- Updated pipeline reports
- Lost deal analysis from November
- Q1 targets and strategy

Breakfast provided.

Jim Hartley
Sales Manager
Prairie King Equipment""",
                "is_urgent": False,
                "urgency_score": 50,
                "urgency_reason": "Team meeting with prep required",
                "hours_ago": 16
            },
            {
                "sender": "jim.hartley@prairiekingequip.com",
                "sender_name": "Jim Hartley",
                "subject": "URGENT: Henderson Dairy Deal - Need Approval",
                "body_text": """Jake,

I saw your request for a 12% discount on the Henderson Dairy tractor deal. That's above my approval limit.

Need more info before I can take this to Dave:
1. What's the total deal value?
2. Are there other equipment in the pipeline?
3. Have we held at 8%?

This needs to close this week for December numbers. Get back to me today.

Jim""",
                "is_urgent": True,
                "urgency_score": 80,
                "urgency_reason": "Manager needs info for deal approval urgently",
                "hours_ago": 4
            },
            {
                "sender": "rachel.green@prairiekingequip.com",
                "sender_name": "Rachel Green",
                "subject": "Training Next Week - GPS Systems",
                "body_text": """Hi Jake,

You're signed up for the advanced GPS and precision ag training next Tuesday and Wednesday.

Details:
- Location: Conference Room B
- Time: 8 AM - 5 PM both days
- Instructor: John Deere certified trainer

Please complete the pre-training module before attending: [link]

Let me know if you have any conflicts.

Rachel Green
Training Coordinator""",
                "is_urgent": False,
                "urgency_score": 35,
                "urgency_reason": "Training reminder",
                "hours_ago": 52
            },
            {
                "sender": "dave.martinez@prairiekingequip.com",
                "sender_name": "Dave Martinez",
                "subject": "Great Job on the Whitfield Deal!",
                "body_text": """Jake,

Just heard that Whitfield Ranch is ready to close on the 8R 410. That's a $385,000 deal - fantastic work!

This puts you at 115% of quota for the quarter. Keep it up!

I'm putting together the President's Club list and you're looking like a lock.

Let's grab lunch next week to discuss your goals for next year.

Dave Martinez
General Manager
Prairie King Equipment""",
                "is_urgent": False,
                "urgency_score": 10,
                "urgency_reason": "Positive feedback, no action needed",
                "hours_ago": 5
            },

            # ============================================
            # VENDOR/SUPPLIER EMAILS
            # ============================================
            {
                "sender": "orders@johndeere.com",
                "sender_name": "John Deere Dealer Portal",
                "subject": "Order Confirmation #JD-2024-78432",
                "body_text": """Order Confirmation

Order Number: JD-2024-78432
Dealer: Prairie King Equipment

Items Ordered:
1x John Deere 8R 410 Tractor - $342,500
  - Premium Cab Package
  - IVT Transmission
  - AutoTrac Activation
  - 5-Year Extended Warranty

Estimated Ship Date: March 1, 2025
Delivery Location: Prairie King Equipment - Main Lot

Please confirm delivery acceptance within 48 hours.

Thank you for your order.
John Deere Dealer Operations""",
                "is_urgent": False,
                "urgency_score": 45,
                "urgency_reason": "Order confirmation requires acknowledgment",
                "hours_ago": 10
            },
            {
                "sender": "accounts@caseih.com",
                "sender_name": "Case IH Accounts",
                "subject": "Invoice Due - Dealer Account #PKE-3847",
                "body_text": """Prairie King Equipment,

This is a reminder that the following invoices are due:

Invoice #3847-1122: $45,780.00 - Due Dec 15
Invoice #3847-1098: $23,450.00 - Due Dec 20

Total Due: $69,230.00

Please remit payment to avoid late fees and potential credit hold.

Payment Methods:
- ACH Transfer: Routing# 021000089, Account# 384756123
- Check: Mail to address on invoice

Questions? Contact dealer.accounts@caseih.com

Case IH Dealer Accounting""",
                "is_urgent": True,
                "urgency_score": 65,
                "urgency_reason": "Payment deadline approaching",
                "hours_ago": 20
            },
            {
                "sender": "promotions@kubotausa.com",
                "sender_name": "Kubota Dealer Programs",
                "subject": "Year-End Dealer Incentives - Action Required",
                "body_text": """DEALER BULLETIN

Year-End Retail Incentive Program

Sell 5+ qualifying units by December 31 and receive:
- Additional 2% dealer margin
- Co-op advertising bonus: $5,000
- Priority 2025 allocation

Qualifying Units:
- M7 Series Tractors
- SVL Series Track Loaders
- RTV-X Series UTVs

Register your deals in the portal by December 28 to qualify.

Current Status: 3 of 5 units sold (Need 2 more!)

Don't miss this opportunity!

Kubota Dealer Programs""",
                "is_urgent": True,
                "urgency_score": 70,
                "urgency_reason": "Incentive deadline, 2 units needed",
                "hours_ago": 28
            },

            # ============================================
            # FINANCING & LEASE INQUIRIES
            # ============================================
            {
                "sender": "underwriting@agrilend.com",
                "sender_name": "AgriLend Financing",
                "subject": "Application Approved - Peterson Application #AL-89234",
                "body_text": """FINANCING APPROVAL NOTICE

Applicant: Peterson Family Farms
Application: #AL-89234
Status: APPROVED

Approved Terms:
- Amount: $275,000
- Term: 72 months
- Rate: 5.9% APR
- Monthly Payment: $4,523.00

Conditions:
- Proof of crop insurance required
- First payment due 30 days from funding

This approval is valid for 30 days. Please send signed loan documents to complete funding.

AgriLend Commercial Financing
NMLS# 384756""",
                "is_urgent": False,
                "urgency_score": 60,
                "urgency_reason": "Financing approved, needs customer follow-up",
                "hours_ago": 14
            },
            {
                "sender": "john.peterson@petersonfamilyfarms.com",
                "sender_name": "John Peterson",
                "subject": "Financing Question - Monthly Payment",
                "body_text": """Jake,

Got the financing approval from AgriLend. The $4,523 monthly payment is higher than I budgeted for.

Is there a longer term option? Or could we look at a lease instead of purchase? I'm trying to keep my monthly under $4,000 if possible.

Also, I haven't told my accountant yet - should I loop him in on this?

John Peterson""",
                "is_urgent": False,
                "urgency_score": 55,
                "urgency_reason": "Financing structure question",
                "hours_ago": 12
            },
            {
                "sender": "tony.russo@russoenterprises.com",
                "sender_name": "Tony Russo",
                "subject": "Lease Buyout Options",
                "body_text": """Hey Jake,

Our 3-year lease on the Fendt 939 is coming up in February. What are our options?

1. What's the buyout price?
2. Can we roll into a new lease on a newer model?
3. What about the residual value - can we negotiate?

We've been happy with the equipment so we're likely to either buy or upgrade. Just want to understand the numbers.

Tony Russo
Russo Enterprises""",
                "is_urgent": False,
                "urgency_score": 50,
                "urgency_reason": "Lease renewal opportunity",
                "hours_ago": 56
            },

            # ============================================
            # TRADE-IN & USED EQUIPMENT
            # ============================================
            {
                "sender": "gary.schmidt@schmidtfarms.net",
                "sender_name": "Gary Schmidt",
                "subject": "Trade-In Value on 2019 Combine",
                "body_text": """Jake,

I'm thinking about upgrading my combine. Before we talk about new equipment, I need to know what my trade-in is worth.

Current equipment:
- 2019 John Deere S780 Combine
- 1,247 separator hours
- Full maintenance records
- Some cosmetic wear but mechanically sound
- Original owner

What can you give me on trade? This will determine what I can afford for the upgrade.

Gary Schmidt
Schmidt Farms""",
                "is_urgent": False,
                "urgency_score": 45,
                "urgency_reason": "Trade-in inquiry, potential new sale",
                "hours_ago": 40
            },
            {
                "sender": "alan.brooks@brooksagriculture.com",
                "sender_name": "Alan Brooks",
                "subject": "Looking for Used 4WD Tractor",
                "body_text": """Hi Jake,

I'm in the market for a used 4WD tractor, 400+ HP. Don't need the latest and greatest - just something reliable with decent hours.

Budget: $150,000-180,000

Brands I'm open to:
- John Deere 9R Series
- Case IH Steiger
- New Holland T9

Let me know what comes through your lot.

Alan Brooks
Brooks Agriculture LLC""",
                "is_urgent": False,
                "urgency_score": 35,
                "urgency_reason": "Used equipment inquiry",
                "hours_ago": 80
            },
            {
                "sender": "heather.mills@millsranch.com",
                "sender_name": "Heather Mills",
                "subject": "Multiple Equipment Trade-In",
                "body_text": """Jake,

We're doing some fleet consolidation and want to trade multiple pieces:

1. 2018 Kubota M135X Tractor - 2,100 hours
2. 2017 New Holland Round Baler BR7090 - Good condition
3. 2020 John Deere Z994R Zero-Turn - 450 hours

Looking to trade all three toward a single larger tractor. Can you come out and do appraisals?

Heather Mills
Mills Ranch
Call: (555) 456-7890""",
                "is_urgent": False,
                "urgency_score": 50,
                "urgency_reason": "Multiple trade-ins, potential large sale",
                "hours_ago": 32
            },

            # ============================================
            # PARTS & INVENTORY
            # ============================================
            {
                "sender": "parts@prairiekingequip.com",
                "sender_name": "Parts Department",
                "subject": "Low Inventory Alert - Popular Items",
                "body_text": """INTERNAL - Inventory Alert

The following items are below minimum stock levels:

CRITICAL (Out of Stock):
- John Deere Filters (RE62418) - 0 units
- Hydraulic Hose 3/4" x 36" - 2 units
- Case IH Belts (87660234) - 0 units

LOW STOCK:
- Grease cartridges - 15 units (min: 50)
- Universal joints - 4 units (min: 10)
- LED work lights - 8 units (min: 20)

Please submit reorder requests by EOD Friday.

Parts Department""",
                "is_urgent": True,
                "urgency_score": 60,
                "urgency_reason": "Parts inventory critically low",
                "hours_ago": 8
            },
            {
                "sender": "charles.wright@wrightbrotherfarms.com",
                "sender_name": "Charles Wright",
                "subject": "Parts Order - Need by Monday",
                "body_text": """Jake,

Need these parts for our Massey Ferguson 7720:

- Front axle pivot pin (Part# 4359270M1)
- Wheel bearing kit (Part# 1860288M91)
- Hydraulic pump seal kit

Can you check if these are in stock? We need them by Monday to finish a repair.

Also, can you look up what this noise might be? The tractor is making a clicking sound when turning left. Video attached.

Charlie Wright
(555) 567-8901""",
                "is_urgent": True,
                "urgency_score": 65,
                "urgency_reason": "Parts needed Monday, repair pending",
                "hours_ago": 15
            },

            # ============================================
            # DELIVERY & LOGISTICS
            # ============================================
            {
                "sender": "transport@heavyhaulpro.com",
                "sender_name": "Heavy Haul Pro Transport",
                "subject": "Delivery Scheduled - Load #HHP-9234",
                "body_text": """DELIVERY CONFIRMATION

Load Number: HHP-9234
Equipment: John Deere 9RX 640 Tractor

Pickup: John Deere Factory, Waterloo IA
Delivery: Prairie King Equipment, Your Location

Scheduled Delivery: December 15, 2024, 2:00 PM

Driver: Mike Johnson
Driver Cell: (555) 234-8901
Truck: Kenworth T880

Please ensure delivery area is clear and accessible.
Forklift/equipment for unloading required.

Heavy Haul Pro Transport""",
                "is_urgent": False,
                "urgency_score": 45,
                "urgency_reason": "Delivery scheduled, prep needed",
                "hours_ago": 22
            },
            {
                "sender": "logistics@prairiekingequip.com",
                "sender_name": "Logistics Team",
                "subject": "Customer Delivery Needed - Anderson Farm",
                "body_text": """DELIVERY REQUEST

Customer: Anderson Farm
Equipment: New Holland T6.180 Tractor
Destination: 4521 County Road 12, Oakville

Requested Delivery Date: December 18
Special Instructions:
- Gate code is 4521
- Deliver to main barn (red building)
- Customer wants delivery walkthrough

Contact: Bob Anderson (555) 345-6712

Please schedule with transport team and confirm with customer.

Logistics Team""",
                "is_urgent": False,
                "urgency_score": 40,
                "urgency_reason": "Customer delivery scheduling needed",
                "hours_ago": 26
            },

            # ============================================
            # COMPLAINTS & ISSUES
            # ============================================
            {
                "sender": "angry.farmer@angrymail.com",
                "sender_name": "Ed Franklin",
                "subject": "TERRIBLE SERVICE - WANT MY MONEY BACK",
                "body_text": """I am FURIOUS right now.

I bought a tractor from you 3 months ago and it's been nothing but problems. First the PTO didn't work right. Then the AC went out. Now the engine is overheating!

Your service department keeps telling me to "bring it in" but I can't afford to be without my tractor for a week during planting prep!

I want either a full refund or a replacement tractor. This is unacceptable.

You have until Friday to make this right or I'm going to the BBB and posting on every farming forum I can find.

Ed Franklin
VERY UNHAPPY CUSTOMER""",
                "is_urgent": True,
                "urgency_score": 85,
                "urgency_reason": "Angry customer threatening action, needs immediate response",
                "hours_ago": 7
            },
            {
                "sender": "careful.customer@gmail.com",
                "sender_name": "Doug Hamilton",
                "subject": "Concern About Recent Purchase",
                "body_text": """Jake,

I hope I'm worrying over nothing, but I noticed something on the sprayer I bought last month.

There appears to be some overspray residue in the tank that wasn't there when I looked at it. It makes me wonder if this was really "new" like you said.

Can you clarify the history of this unit? I paid new equipment prices and I want to make sure I got what I paid for.

Please call me when you get this.

Doug Hamilton
(555) 678-9012""",
                "is_urgent": True,
                "urgency_score": 70,
                "urgency_reason": "Trust issue, needs prompt clarification",
                "hours_ago": 11
            },

            # ============================================
            # EVENTS & MARKETING
            # ============================================
            {
                "sender": "events@prairiekingequip.com",
                "sender_name": "Events Team",
                "subject": "Farm Show Booth - Volunteer Signup",
                "body_text": """Team,

The State Farm Show is January 15-18. We need volunteers for our booth.

Available Shifts:
- Setup: Jan 14 (afternoon)
- Day 1: Jan 15 (morning/afternoon)
- Day 2: Jan 16 (morning/afternoon)
- Day 3: Jan 17 (morning/afternoon)
- Day 4: Jan 18 (morning/afternoon)
- Teardown: Jan 18 (evening)

We're displaying:
- John Deere 8R 410 (customer demo unit)
- Kubota M7-152
- Various implements

Please reply with your availability. Commission on leads from the show!

Events Team""",
                "is_urgent": False,
                "urgency_score": 30,
                "urgency_reason": "Event signup request",
                "hours_ago": 96
            },
            {
                "sender": "marketing@prairiekingequip.com",
                "sender_name": "Marketing Department",
                "subject": "Customer Success Story - Need Your Help",
                "body_text": """Hi Jake,

We're putting together customer success stories for the website and Tom Whitfield agreed to be featured.

Since he's your customer, can you:
1. Coordinate a time for photos (about 1 hour)
2. Provide any background on the deal
3. Suggest talking points about why he chose us

We'd like to shoot this before the end of the month.

Thanks!
Marketing Team""",
                "is_urgent": False,
                "urgency_score": 35,
                "urgency_reason": "Marketing request, not time-sensitive",
                "hours_ago": 64
            },

            # ============================================
            # HR & ADMINISTRATIVE
            # ============================================
            {
                "sender": "hr@prairiekingequip.com",
                "sender_name": "Human Resources",
                "subject": "Open Enrollment Reminder - Deadline Dec 20",
                "body_text": """BENEFITS ENROLLMENT REMINDER

Open enrollment for 2025 benefits ends December 20.

Action Required:
1. Log into benefits portal
2. Review/select health insurance plan
3. Update HSA/FSA contributions
4. Review life insurance beneficiaries
5. Confirm dental and vision selections

If no changes are made, your current selections will continue.

New This Year:
- Mental health coverage expanded
- New pet insurance option
- Gym membership reimbursement increased

Questions? Contact HR at benefits@prairiekingequip.com

Human Resources""",
                "is_urgent": True,
                "urgency_score": 55,
                "urgency_reason": "Benefits deadline approaching",
                "hours_ago": 48
            },
            {
                "sender": "payroll@prairiekingequip.com",
                "sender_name": "Payroll Department",
                "subject": "December Commission Statement",
                "body_text": """Commission Statement - December 2024

Employee: Jake Morrison
Period: December 1-31, 2024

Closed Deals:
1. Whitfield Ranch - JD 8R 410 - $385,000 x 3% = $11,550
2. Chen Organics - GPS Package - $62,000 x 4% = $2,480
3. Various Parts Sales - $8,450 x 10% = $845

Total Commissions: $14,875

Quarterly Bonus (Q4): $2,500
Year-to-Date Commissions: $142,350

Payment will be included in December 31 paycheck.

Payroll Department""",
                "is_urgent": False,
                "urgency_score": 15,
                "urgency_reason": "Informational only",
                "hours_ago": 2
            },
            {
                "sender": "safety@prairiekingequip.com",
                "sender_name": "Safety Committee",
                "subject": "Mandatory Safety Training - Complete by Dec 31",
                "body_text": """REQUIRED: Annual Safety Training

All employees must complete the following online modules by December 31:

1. Forklift Operations Refresher (30 min)
2. Hazardous Materials Handling (45 min)
3. Fire Safety Update (20 min)
4. Active Shooter Preparedness (15 min)

Access training at: training.prairiekingequip.com
Your login: jmorrison
Temp password: Safety2024!

Failure to complete by deadline may result in inability to access shop floor.

Safety Committee""",
                "is_urgent": True,
                "urgency_score": 60,
                "urgency_reason": "Mandatory training deadline",
                "hours_ago": 100
            },

            # ============================================
            # FOLLOW-UP SEQUENCES
            # ============================================
            {
                "sender": "emily.watson@watsonacres.com",
                "sender_name": "Emily Watson",
                "subject": "RE: RE: RE: Tractor Quote Follow-Up",
                "body_text": """Hi Jake,

Sorry for the delayed response - harvest has been crazy.

I'm still interested in the New Holland T7.290 but I need to wait until after we sell this year's crop. Should have a better picture of our finances by mid-January.

Can you keep me on your list and check back then?

Emily Watson
Watson Acres""",
                "is_urgent": False,
                "urgency_score": 35,
                "urgency_reason": "Delayed interest, follow-up in January",
                "hours_ago": 38
            },
            {
                "sender": "no-reply@prairiekingequip.com",
                "sender_name": "CRM System",
                "subject": "Follow-Up Reminder: Anderson Farm",
                "body_text": """AUTOMATED REMINDER

Lead: Bob Anderson
Company: Anderson Farm
Last Contact: 30 days ago
Status: Quote Sent

Notes:
- Quoted Kubota M6-141 at $125,000
- Said he was waiting for harvest revenue
- Wife is the financial decision maker

Suggested Action: Follow up on quote status

This lead has been idle for 30+ days. Consider reaching out.

CRM System""",
                "is_urgent": False,
                "urgency_score": 40,
                "urgency_reason": "Automated follow-up reminder",
                "hours_ago": 4
            },
            {
                "sender": "paul.garrett@garrettproducellc.com",
                "sender_name": "Paul Garrett",
                "subject": "Haven't Heard Back - Still Interested?",
                "body_text": """Jake,

I sent a reply to your quote about 2 weeks ago but haven't heard back. Not sure if it got lost in the shuffle?

Quick recap - I was interested in the sprayer package but had questions about the boom width options.

Are you still able to help me with this? Let me know if I should be talking to someone else.

Paul Garrett
Garrett Produce LLC""",
                "is_urgent": True,
                "urgency_score": 70,
                "urgency_reason": "Customer waiting for response, risk of losing deal",
                "hours_ago": 9
            },

            # ============================================
            # NEWSLETTERS & PROMOTIONAL
            # ============================================
            {
                "sender": "newsletter@tractortime.com",
                "sender_name": "Tractor Time Magazine",
                "subject": "This Month: Best Compact Tractors of 2024",
                "body_text": """TRACTOR TIME - December 2024

Featured This Month:
- Best Compact Tractors of 2024 [READ MORE]
- Winter Equipment Maintenance Checklist
- Interview: Kubota's New Product Line Director
- Used Equipment Market Outlook for 2025

Subscriber Spotlight:
"Using precision ag technology, we reduced input costs by 15%"
- Featured Farm: Chen Organics

Industry News:
- John Deere announces 2025 pricing
- Case IH restructures dealer network
- Electric tractor development continues

[View Full Newsletter]

Unsubscribe | Update Preferences""",
                "is_urgent": False,
                "urgency_score": 5,
                "urgency_reason": "Newsletter, no action needed",
                "hours_ago": 72
            },
            {
                "sender": "promos@johndeere.com",
                "sender_name": "John Deere Promotions",
                "subject": "Year-End Savings Event - 0% for 60 Months!",
                "body_text": """JOHN DEERE YEAR-END SAVINGS EVENT

Special Financing Offer:
0% APR for 60 months on select models*

Qualifying Equipment:
- 8 Series Row Crop Tractors
- S7 Series Combines
- 1700 Series Planters

Offer ends December 31, 2024

Find a dealer: dealer.johndeere.com

*With approved credit through John Deere Financial. See dealer for details.

John Deere - Nothing Runs Like a Deere""",
                "is_urgent": False,
                "urgency_score": 40,
                "urgency_reason": "Time-limited promotion",
                "hours_ago": 36
            },

            # ============================================
            # WEATHER & MARKET ALERTS
            # ============================================
            {
                "sender": "alerts@farmerweather.com",
                "sender_name": "Farmer Weather Alerts",
                "subject": "FREEZE WARNING - Next 48 Hours",
                "body_text": """WEATHER ALERT - YOUR REGION

FREEZE WARNING
Effective: Tonight through Sunday morning

Expected Conditions:
- Low temps: 18-25°F
- Wind chill: 5-10°F
- Duration: 36-48 hours

Impact on Farming:
- Winterize all equipment
- Protect livestock water sources
- Check stored crop conditions

Equipment Recommendations:
- Drain water from tractors if not using antifreeze
- Store sensitive electronics indoors
- Check hydraulic fluid levels

Stay safe!
Farmer Weather Alert Service""",
                "is_urgent": True,
                "urgency_score": 45,
                "urgency_reason": "Weather alert affecting operations",
                "hours_ago": 6
            },
            {
                "sender": "markets@commodityalerts.com",
                "sender_name": "Commodity Price Alerts",
                "subject": "Market Update: Corn Futures Up 5%",
                "body_text": """COMMODITY MARKET UPDATE

Daily Summary - December 11, 2024

CORN: $4.85/bu (+$0.23, +4.9%)
SOYBEANS: $12.45/bu (+$0.18, +1.5%)
WHEAT: $6.12/bu (-$0.08, -1.3%)

Market Analysis:
The jump in corn futures is driven by lower-than-expected yields in South America. This could be positive for farmers looking to sell stored grain.

What This Means:
- Consider selling stored corn
- Strong prices may increase equipment buying power
- Watch for continued volatility

Tomorrow's Reports:
- USDA Export Sales (8:30 AM EST)
- Weekly Ethanol Production (10:30 AM EST)

Commodity Alert Service""",
                "is_urgent": False,
                "urgency_score": 25,
                "urgency_reason": "Market information",
                "hours_ago": 8
            },

            # ============================================
            # ADDITIONAL SALES OPPORTUNITIES
            # ============================================
            {
                "sender": "corporate@bigagricompany.com",
                "sender_name": "BigAgri Purchasing",
                "subject": "RFQ: Fleet of 10 Tractors",
                "body_text": """To Whom It May Concern,

BigAgri Company is soliciting quotes for the following equipment purchase:

Requirement:
- Quantity: 10 tractors
- HP Range: 200-250 HP
- Must include: Front loader capability, GPS ready
- Delivery: Q1 2025

Timeline:
- RFQ Due: December 20, 2024
- Selection: January 10, 2025
- Delivery: March 2025

Please submit quotes to purchasing@bigagricompany.com

Include:
1. Equipment specifications
2. Unit and total pricing
3. Delivery timeline
4. Warranty terms
5. Service agreement options

Questions: Contact Ryan Mitchell at (555) 890-1234

BigAgri Company Purchasing Department""",
                "is_urgent": True,
                "urgency_score": 85,
                "urgency_reason": "Large fleet RFQ with deadline",
                "hours_ago": 48
            },
            {
                "sender": "miguel.sanchez@sanchezfamilyfarms.com",
                "sender_name": "Miguel Sanchez",
                "subject": "Expanding Operation - Need Multiple Units",
                "body_text": """Jake,

Big news - we just closed on 2,000 additional acres adjacent to our current operation. This doubles our size!

We're going to need significant equipment:
- 2-3 additional tractors (300+ HP)
- 1 combine
- Planter upgrade for wider acreage
- Various implements

Budget is around $1.5 million total. We've got financing pre-approved through Farm Credit.

When can you come out to discuss? This is our biggest expansion ever and I want to make sure we get it right.

Miguel Sanchez
Sanchez Family Farms
(555) 901-2345""",
                "is_urgent": True,
                "urgency_score": 90,
                "urgency_reason": "Large expansion, pre-approved financing, multiple units",
                "hours_ago": 5
            },
            {
                "sender": "beth.carpenter@carpentercommunity.org",
                "sender_name": "Beth Carpenter",
                "subject": "Equipment for Youth Agriculture Program",
                "body_text": """Hello,

I'm reaching out on behalf of the Carpenter Community Foundation. We run a youth agriculture education program teaching farming to at-risk teens.

We're looking for a donated or heavily discounted tractor for our program. Even older used equipment would be valuable.

Our program:
- 15 students per year
- 40-acre teaching farm
- Funded by grants and donations
- 501(c)(3) nonprofit

Tax deduction receipt available for any donation.

Is this something Prairie King might consider? Happy to discuss.

Beth Carpenter
Program Director
Carpenter Community Foundation""",
                "is_urgent": False,
                "urgency_score": 20,
                "urgency_reason": "Donation request, community relations",
                "hours_ago": 120
            },
            {
                "sender": "lucas.bennett@bennettdairy.com",
                "sender_name": "Lucas Bennett",
                "subject": "Thinking About Switching Brands",
                "body_text": """Jake,

I've been a Case IH guy my whole life, but I'm not happy with the service I've been getting from my current dealer.

Tell me why I should switch to buying from you guys. What do you have that competes with the Case IH Magnum 380?

I run a 3,500 acre dairy operation and need reliable equipment. Current dealer takes forever on parts and their service rates are outrageous.

Convince me.

Lucas Bennett
Bennett Dairy""",
                "is_urgent": False,
                "urgency_score": 65,
                "urgency_reason": "Competitive switch opportunity",
                "hours_ago": 52
            },
            {
                "sender": "inventory@prairiekingequip.com",
                "sender_name": "Inventory System",
                "subject": "Trade-In Ready for Resale: 2020 JD 8R 340",
                "body_text": """INVENTORY ALERT - USED EQUIPMENT

A trade-in is ready for resale listing:

Unit: 2020 John Deere 8R 340 Tractor
Serial: 1RW8340RVLD123456
Hours: 1,850
Condition: Excellent

Features:
- IVT Transmission
- Premium Cab
- AutoTrac Ready
- Extended Warranty to 2025

Trade-In Value: $185,000
Suggested Retail: $225,000-235,000

Action Needed:
1. Photograph unit
2. Complete inspection checklist
3. Set retail price
4. List on website and equipment trader

This unit should sell quickly - similar units selling in 30-45 days.

Inventory System""",
                "is_urgent": False,
                "urgency_score": 35,
                "urgency_reason": "Used inventory to list",
                "hours_ago": 16
            },

            # ============================================
            # REFERRAL & TESTIMONIAL REQUESTS
            # ============================================
            {
                "sender": "tom.whitfield@whitfieldranch.com",
                "sender_name": "Tom Whitfield",
                "subject": "Referral - My Neighbor is Looking for Equipment",
                "body_text": """Jake,

Quick note - my neighbor Dave Reynolds mentioned he's looking for a new planter setup.

He saw my new John Deere and was impressed. Told him to give you a call but wanted to give you a heads up.

Dave's contact:
dave.reynolds@reynoldsfarms.com
(555) 432-1098
About 1,200 acres of corn

Tell him I sent you - maybe there's a referral bonus in it for me? 😄

Tom""",
                "is_urgent": False,
                "urgency_score": 55,
                "urgency_reason": "Warm referral from happy customer",
                "hours_ago": 3
            },
            {
                "sender": "reviews@google.com",
                "sender_name": "Google Business",
                "subject": "New Review on Prairie King Equipment",
                "body_text": """New Google Review

Prairie King Equipment has received a new review:

⭐⭐⭐⭐⭐ (5 stars)

"Jake Morrison went above and beyond to help us find the right tractor for our operation. No pressure, just honest advice. When we had an issue during harvest, their service team was there same day. This is how equipment dealers should operate. Highly recommend!"

- Tom Whitfield, Whitfield Ranch

Respond to this review: [link]

Google Business""",
                "is_urgent": False,
                "urgency_score": 25,
                "urgency_reason": "Positive review to acknowledge",
                "hours_ago": 24
            },

            # ============================================
            # ADDITIONAL EMAILS TO REACH 75
            # ============================================
            {
                "sender": "wayne.foster@fosteragri.com",
                "sender_name": "Wayne Foster",
                "subject": "Demo Request - Autonomous Tractor Technology",
                "body_text": """Jake,

I've been reading about the autonomous tractor technology and I'm intrigued. Our labor costs are killing us.

Do you have any units with autonomous capabilities available for demo? I want to see how it handles our terrain before committing.

Our operation:
- 4,500 acres of row crops
- Hilly terrain in some sections
- Currently running 5 tractors with 3 full-time operators

If this technology works as advertised, it could save us $150k+ annually in labor.

Wayne Foster
Foster Agriculture""",
                "is_urgent": False,
                "urgency_score": 60,
                "urgency_reason": "High-value technology inquiry with clear ROI interest",
                "hours_ago": 19
            },
            {
                "sender": "linda.morgan@morganfarmllc.com",
                "sender_name": "Linda Morgan",
                "subject": "Insurance Requirement - Equipment Appraisal",
                "body_text": """Hi Jake,

My insurance company is requiring updated appraisals on all our equipment for the new policy year.

Can you provide written appraisals for the following units you sold us:
1. 2022 John Deere 8R 370
2. 2023 Case IH 9250 Combine
3. 2021 Kinze 3660 Planter

They need official dealer letterhead with current market values.

Need this by next Friday if possible.

Thanks,
Linda Morgan
Morgan Farm LLC""",
                "is_urgent": False,
                "urgency_score": 50,
                "urgency_reason": "Service request with deadline",
                "hours_ago": 42
            },
            {
                "sender": "jason.reed@reedcattleco.com",
                "sender_name": "Jason Reed",
                "subject": "Looking for Cattle Equipment",
                "body_text": """Jake,

My brother mentioned you might carry livestock equipment as well as row crop stuff.

We need:
- Cattle squeeze chute
- Portable corral panels (about 200 feet)
- Stock trailer (20-24 foot gooseneck)

Do you deal in this type of equipment or should I look elsewhere?

Thanks,
Jason Reed
Reed Cattle Company
850 head cow-calf operation""",
                "is_urgent": False,
                "urgency_score": 35,
                "urgency_reason": "Cross-sell opportunity, livestock equipment",
                "hours_ago": 68
            },
            {
                "sender": "compliance@aginsurance.com",
                "sender_name": "AgInsurance Compliance",
                "subject": "Equipment Safety Certification Required",
                "body_text": """Dear Prairie King Equipment,

Our records show the following equipment sold through your dealership requires updated safety certification:

Customer: Morrison Grain LLC
Equipment: 2023 John Deere S780 Combine
Issue: ROPS (Rollover Protection) certification expired

To maintain insurance coverage, please submit Form AG-7 with:
1. ROPS inspection results
2. SMV (Slow Moving Vehicle) emblem verification
3. Fire extinguisher certification

Deadline: December 31, 2024

Failure to submit may result in coverage suspension.

AgInsurance Compliance Department""",
                "is_urgent": True,
                "urgency_score": 65,
                "urgency_reason": "Customer insurance compliance deadline",
                "hours_ago": 54
            },
            {
                "sender": "pete.jackson@jacksonwheat.com",
                "sender_name": "Pete Jackson",
                "subject": "Winter Wheat Drill - Spring Delivery?",
                "body_text": """Jake,

Looking ahead to next fall - we want to expand our winter wheat acreage and need a bigger drill.

Currently running a 30-foot but want to move up to 40 or 45 feet.

Questions:
1. What's the lead time on a Great Plains 4000HD?
2. If I order now, can I get spring delivery?
3. Trade-in value on my current drill?

No rush on this - just planning ahead.

Pete Jackson
Jackson Wheat Farms""",
                "is_urgent": False,
                "urgency_score": 40,
                "urgency_reason": "Future planning inquiry, long sales cycle",
                "hours_ago": 78
            },
            {
                "sender": "dispatch@prairiekingequip.com",
                "sender_name": "Service Dispatch",
                "subject": "URGENT: Field Call Request - Stevens Farm",
                "body_text": """FIELD SERVICE REQUEST

Customer: Stevens Farm
Contact: Randy Stevens
Phone: (555) 789-0123

Equipment: John Deere 9620RX Track Tractor
Issue: Undercarriage making grinding noise, track tension warning light on

Location: 8 miles north on County Rd 15
Severity: HIGH - Customer in the middle of fall tillage

Customer says he can work slowly for a few more hours but needs service today.

Available Technicians:
- Mike: Currently on another call (ETA 3 hours)
- Steve: Available now

Please assign and confirm with customer.

Service Dispatch""",
                "is_urgent": True,
                "urgency_score": 80,
                "urgency_reason": "Emergency field service needed today",
                "hours_ago": 1
            },
            {
                "sender": "amy.walsh@walshfamilyfarms.net",
                "sender_name": "Amy Walsh",
                "subject": "Retiring - Selling Everything",
                "body_text": """Jake,

After 45 years, I'm finally hanging it up. Doctor says my back can't take it anymore.

I need to liquidate our entire operation:
- 2019 John Deere 8345R Tractor (3,200 hours)
- 2017 Case IH 2150 Planter
- 2018 John Deere S770 Combine
- Various tillage equipment
- Shop full of tools and parts

Would Prairie King be interested in purchasing the whole package? Or could you help us with an auction?

Kids aren't interested in farming so it all has to go.

Amy Walsh
Walsh Family Farms""",
                "is_urgent": False,
                "urgency_score": 70,
                "urgency_reason": "Large estate/retirement liquidation opportunity",
                "hours_ago": 33
            },
            {
                "sender": "grants@usdafsa.gov",
                "sender_name": "USDA Farm Service Agency",
                "subject": "EQIP Funding Approved - Customer Notification",
                "body_text": """EQUIPMENT PURCHASE GRANT NOTIFICATION

This notice is to inform you that the following customer has been approved for EQIP (Environmental Quality Incentives Program) funding:

Customer: Chen Organics
Contact: Robert Chen
Application: #EQIP-2024-89432

Approved Items:
- Precision Agriculture Technology: $45,000
- Conservation Tillage Equipment: $30,000

Total Approved: $75,000

Important: Customer must make purchases within 60 days of this notice.

Please coordinate with the customer to complete qualifying purchases.

USDA Farm Service Agency""",
                "is_urgent": True,
                "urgency_score": 75,
                "urgency_reason": "Grant-funded purchase with deadline",
                "hours_ago": 13
            },
            {
                "sender": "troy.anderson@andersonorganics.com",
                "sender_name": "Troy Anderson",
                "subject": "Organic Farming Equipment Needs",
                "body_text": """Hello Jake,

We're converting 600 acres to certified organic production and need equipment that's compatible with organic practices.

Specifically looking for:
1. Mechanical cultivation equipment (not herbicide-based)
2. Cover crop seeding attachments
3. Compost spreader

I know this is specialized stuff. Do you handle this or can you point me in the right direction?

Budget is flexible for the right solutions.

Troy Anderson
Anderson Organics""",
                "is_urgent": False,
                "urgency_score": 50,
                "urgency_reason": "Niche market opportunity, organic farming",
                "hours_ago": 58
            },
            {
                "sender": "scheduler@prairiekingequip.com",
                "sender_name": "Shop Scheduler",
                "subject": "Winter Service Appointments Filling Up",
                "body_text": """INTERNAL NOTICE

Winter service schedule is 75% booked for January/February.

Remaining Slots:
- January: 8 slots
- February: 12 slots

Priority should go to:
1. Warranty work (manufacturer requirements)
2. Pre-season prep for spring planters
3. Combine maintenance before storage

Customers on waitlist: 15

Please push customers to book now. After-season rates end December 31.

Shop Scheduler""",
                "is_urgent": False,
                "urgency_score": 45,
                "urgency_reason": "Internal scheduling notice",
                "hours_ago": 29
            },
            {
                "sender": "derek.collins@collinsharvest.com",
                "sender_name": "Derek Collins",
                "subject": "Custom Harvesting Fleet Needs",
                "body_text": """Jake,

We run a custom harvesting operation and we're looking to add two more combines to our fleet for next season.

Requirements:
- Late model combines (2021 or newer)
- Corn and soybean heads
- Identical units if possible (simplifies parts/training)

We follow the harvest from Texas to North Dakota so reliability is critical. Can't afford breakdowns when we're 1,000 miles from home.

What do you have available? We can pay cash.

Derek Collins
Collins Custom Harvesting
Currently running 6 John Deere S780s""",
                "is_urgent": False,
                "urgency_score": 65,
                "urgency_reason": "Fleet purchase, cash buyer",
                "hours_ago": 47
            },
            {
                "sender": "coop@farmerscoopcentral.com",
                "sender_name": "Farmers Coop Central",
                "subject": "Dealer Meeting - January 8th",
                "body_text": """Prairie King Equipment,

You're invited to our annual Dealer Appreciation Meeting:

Date: January 8, 2025
Time: 11:30 AM - 2:00 PM
Location: Farmers Coop Central - Conference Room

Agenda:
- 2024 Partnership Review
- 2025 Financing Programs
- Co-Marketing Opportunities
- Lunch Provided

Please RSVP by January 3rd.

We look forward to continuing our partnership.

Farmers Coop Central
Member Services""",
                "is_urgent": False,
                "urgency_score": 30,
                "urgency_reason": "Partner meeting invitation",
                "hours_ago": 88
            },
            {
                "sender": "kelly.torres@torresdairy.com",
                "sender_name": "Kelly Torres",
                "subject": "Urgent Parts Need - Mixer Wagon Down",
                "body_text": """Jake,

Our Kuhn vertical mixer wagon broke down this morning. The auger bearings seized up.

I need:
- 2x Auger bearing assemblies (Part# if you can look it up)
- Auger shaft inspection

We have 400 dairy cows that need to be fed. Currently borrowing our neighbor's mixer but that's not sustainable.

How fast can you get parts? Willing to pay rush shipping.

Kelly Torres
Torres Dairy
(555) 234-5670 - call anytime""",
                "is_urgent": True,
                "urgency_score": 88,
                "urgency_reason": "Livestock operation, equipment critical for feeding",
                "hours_ago": 4
            },
            {
                "sender": "education@countyfair.org",
                "sender_name": "County Fair Board",
                "subject": "Equipment Display Request - Summer Fair",
                "body_text": """Dear Prairie King Equipment,

The County Fair Board is planning the 2025 Summer Fair (July 15-20) and we'd like to invite you to display equipment.

Display Options:
- Main equipment row: $500 (20x40 space)
- Demo area: $750 (includes time slots for live demos)
- Title sponsor: $2,000 (premium placement + banner)

Benefits:
- 50,000+ attendees over 5 days
- Farm family demographics
- Live demo opportunities

This is a great lead generation event. Last year's equipment dealers reported strong sales leads.

Please confirm interest by March 1.

County Fair Board""",
                "is_urgent": False,
                "urgency_score": 25,
                "urgency_reason": "Marketing opportunity, future event",
                "hours_ago": 110
            },
            {
                "sender": "nick.brown@brownseedcompany.com",
                "sender_name": "Nick Brown",
                "subject": "Planter Population Monitors - Compatibility?",
                "body_text": """Jake,

I'm looking to upgrade the population monitors on my John Deere 1790 planter.

Currently have the basic system but want to add individual row clutches and high-speed capabilities.

Questions:
1. Is the ExactEmerge system compatible with my 2018 frame?
2. What's the typical ROI on the upgrade?
3. Can it be installed before planting season?

This is partly driven by my seed company - they're pushing precision planting for their new hybrids.

Nick Brown
Brown Seed Company""",
                "is_urgent": False,
                "urgency_score": 55,
                "urgency_reason": "Technology upgrade inquiry, deadline-aware",
                "hours_ago": 62
            },
            {
                "sender": "regulations@statedeptag.gov",
                "sender_name": "State Dept of Agriculture",
                "subject": "Notice: New Emissions Regulations for Ag Equipment",
                "body_text": """REGULATORY NOTICE

Attention: Farm Equipment Dealers

New emissions regulations for agricultural equipment will take effect January 1, 2026.

Key Changes:
- All diesel equipment over 175 HP must meet Tier 4 Final standards
- DEF (Diesel Exhaust Fluid) systems required on new sales
- Annual emissions testing for equipment over 10 years old

Dealer Requirements:
- Update sales documentation
- Provide emissions compliance certificates
- Train staff on new requirements

Information sessions will be held in March. Registration details to follow.

State Department of Agriculture
Air Quality Division""",
                "is_urgent": False,
                "urgency_score": 35,
                "urgency_reason": "Regulatory notice, future compliance",
                "hours_ago": 144
            },
            {
                "sender": "sam.ortiz@ortizagventures.com",
                "sender_name": "Sam Ortiz",
                "subject": "Investor Looking at Ag Tech Dealership",
                "body_text": """Mr. Morrison,

I'm a private equity investor looking at the agricultural equipment sector in your region.

I'm interested in understanding:
1. Market trends in farm equipment sales
2. Growth of precision ag technology adoption
3. Competitive landscape

Would you be open to a 30-minute call to share your perspective? I'm not trying to sell anything - just doing market research.

I can offer some insights into what we're seeing from an investment perspective.

Sam Ortiz
Ortiz Agricultural Ventures
Investor Relations""",
                "is_urgent": False,
                "urgency_score": 20,
                "urgency_reason": "Networking/research call request",
                "hours_ago": 76
            },
        ]

        # Create emails
        for i, email_data in enumerate(emails_data):
            hours_ago = email_data.pop("hours_ago", 0)
            email = Email(
                id=str(uuid.uuid4()),
                user_id=test_user.id,
                gmail_id=f"demo-farm-{i+1:04d}",
                subject=email_data["subject"],
                sender=email_data["sender"],
                sender_name=email_data["sender_name"],
                body_text=email_data["body_text"],
                snippet=email_data["body_text"][:100] + "...",
                is_urgent=email_data.get("is_urgent", False),
                urgency_score=email_data.get("urgency_score", 0),
                urgency_reason=email_data.get("urgency_reason"),
                has_attachments=email_data.get("has_attachments", False),
                is_read=email_data.get("is_read", hours_ago > 48),
                received_at=datetime.utcnow() - timedelta(hours=hours_ago),
                created_at=datetime.utcnow()
            )
            db.add(email)

        db.flush()
        db.commit()

        # Print summary
        email_count = db.query(Email).filter(Email.user_id == test_user.id).count()
        urgent_count = db.query(Email).filter(
            Email.user_id == test_user.id,
            Email.is_urgent == True
        ).count()

        print(f"\n✅ Farm Equipment Demo Data Created!")
        print(f"   - Total Emails: {email_count}")
        print(f"   - Urgent Emails: {urgent_count}")
        print(f"\n📧 Demo User:")
        print(f"   Name: Jake Morrison")
        print(f"   Email: testuser@demo.saigbox.com")
        print(f"   Role: Sales Rep at Prairie King Equipment")
        print(f"\n🚜 Email Categories:")

        # Count by category
        hot_leads = sum(1 for e in emails_data if e.get("urgency_score", 0) >= 85)
        warm_leads = sum(1 for e in emails_data if 50 <= e.get("urgency_score", 0) < 85)
        cold_leads = sum(1 for e in emails_data if e.get("urgency_score", 0) < 50)

        print(f"   - Hot Leads (ready to buy): {hot_leads}")
        print(f"   - Warm Leads (interested): {warm_leads}")
        print(f"   - Cold/Informational: {cold_leads}")

        return test_user

    except Exception as e:
        db.rollback()
        print(f"❌ Error creating demo data: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    create_farm_equipment_demo()
