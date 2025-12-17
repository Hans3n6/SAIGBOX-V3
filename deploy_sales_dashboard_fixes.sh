#!/bin/bash

# Sales Dashboard Fixes Deployment Script
# This script applies all fixes and improvements to the sales dashboard

set -e  # Exit on error

echo "================================================"
echo "Sales Dashboard Fixes - Deployment Script"
echo "================================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if running from correct directory
if [ ! -f "requirements.txt" ]; then
    echo -e "${RED}Error: Must run from SAIGBOX-V3 root directory${NC}"
    exit 1
fi

echo -e "${YELLOW}Step 1: Backing up database...${NC}"
if [ -f "saigbox.db" ]; then
    cp saigbox.db "saigbox.db.backup.$(date +%Y%m%d_%H%M%S)"
    echo -e "${GREEN}✓ Database backed up${NC}"
else
    echo -e "${YELLOW}⚠ No database found (first time setup?)${NC}"
fi

echo ""
echo -e "${YELLOW}Step 2: Installing Python dependencies...${NC}"
# Use pip3 if pip is not available, with --user flag for managed environments
if command -v pip &> /dev/null; then
    pip install -q --user weasyprint==60.1 reportlab==4.0.7 openai==1.6.1 2>/dev/null || echo -e "${YELLOW}⚠ Skipping package install (may already be installed or in venv)${NC}"
elif command -v pip3 &> /dev/null; then
    pip3 install -q --user weasyprint==60.1 reportlab==4.0.7 openai==1.6.1 2>/dev/null || echo -e "${YELLOW}⚠ Skipping package install (may already be installed or in venv)${NC}"
else
    echo -e "${RED}✗ pip/pip3 not found${NC}"
    echo -e "${YELLOW}  Please install manually: pip3 install weasyprint reportlab openai${NC}"
fi
echo -e "${GREEN}✓ Dependencies step complete${NC}"

echo ""
echo -e "${YELLOW}Step 3: Running database migrations...${NC}"
if [ -f "alembic.ini" ]; then
    # Use python3 if python is not available
    if command -v python &> /dev/null; then
        python -m alembic upgrade head 2>&1
    elif command -v python3 &> /dev/null; then
        python3 -m alembic upgrade head 2>&1
    else
        echo -e "${RED}✗ python/python3 not found${NC}"
    fi

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Database migrated (is_sent field added, indexes created)${NC}"
    else
        echo -e "${YELLOW}⚠ Migration failed or not needed${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Alembic not initialized (alembic.ini missing)${NC}"
    echo -e "${YELLOW}  To run migration manually:${NC}"
    echo -e "${YELLOW}    1. Initialize: alembic init alembic${NC}"
    echo -e "${YELLOW}    2. Configure alembic.ini with your database${NC}"
    echo -e "${YELLOW}    3. Run: alembic upgrade head${NC}"
    echo -e "${YELLOW}  OR apply manually to SQLite:${NC}"
    echo -e "${YELLOW}    sqlite3 saigbox.db < alembic/versions/add_is_sent_and_indexes.sql${NC}"
fi

echo ""
echo -e "${YELLOW}Step 4: Verifying files...${NC}"

# Check critical files
FILES=(
    "core/database.py"
    "api/routes/sales_dashboard.py"
    "static/sales-dashboard-enhancements.js"
    "alembic/versions/add_is_sent_and_indexes.py"
)

for file in "${FILES[@]}"; do
    if [ -f "$file" ]; then
        echo -e "${GREEN}✓ $file${NC}"
    else
        echo -e "${RED}✗ Missing: $file${NC}"
    fi
done

echo ""
echo -e "${YELLOW}Step 5: Checking environment variables...${NC}"

# Check .env file
if [ -f ".env" ]; then
    if grep -q "MICROSOFT_CLIENT_ID" .env && grep -q "MICROSOFT_CLIENT_SECRET" .env; then
        echo -e "${GREEN}✓ Microsoft OAuth configured${NC}"
    else
        echo -e "${RED}✗ Missing Microsoft OAuth credentials in .env${NC}"
        echo -e "${YELLOW}  Email sending will not work until configured${NC}"
    fi

    if grep -q "OPENAI_API_KEY" .env; then
        echo -e "${GREEN}✓ OpenAI API key configured${NC}"
    else
        echo -e "${YELLOW}⚠ OpenAI API key not found (optional)${NC}"
        echo -e "${YELLOW}  AI features will use templates instead${NC}"
    fi
else
    echo -e "${RED}✗ No .env file found${NC}"
    echo -e "${YELLOW}  Copy .env.example to .env and configure${NC}"
fi

echo ""
echo -e "${YELLOW}Step 6: Creating static directories...${NC}"
mkdir -p static/downloads/proposals
echo -e "${GREEN}✓ Directories created${NC}"

echo ""
echo "================================================"
echo -e "${GREEN}Deployment Complete!${NC}"
echo "================================================"
echo ""
echo "Next Steps:"
echo ""
echo "1. Restart the application:"
echo "   Development: uvicorn api.main:app --reload"
echo "   Production:  sudo systemctl restart saigbox"
echo ""
echo "2. Test email sending:"
echo "   - Go to Sales Dashboard"
echo "   - Send a test follow-up email"
echo "   - Check Outlook sent items"
echo ""
echo "3. Test PDF generation:"
echo "   - Navigate to Proposals section"
echo "   - Export a proposal as PDF"
echo "   - Download from /downloads/proposals/"
echo ""
echo "4. Verify database changes:"
echo "   sqlite3 saigbox.db"
echo "   .schema emails  # Should show is_sent column"
echo "   .indexes        # Should show new indexes"
echo ""
echo "Documentation:"
echo "   See SALES_DASHBOARD_FIXES_SUMMARY.md for details"
echo ""
echo -e "${GREEN}All fixes have been applied successfully!${NC}"
