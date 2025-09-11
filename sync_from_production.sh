#!/bin/bash
# Sync all data from production to local development

echo "🔄 Syncing SAIGBOX from production to local..."
echo "⚠️  This will replace your local data with production data!"
read -p "Are you sure you want to continue? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Sync cancelled."
    exit 1
fi

# Create temporary SSH key for EC2 Instance Connect
TEMP_KEY="/tmp/ec2-sync-$$"
ssh-keygen -t rsa -f "$TEMP_KEY" -N "" -q

# Send public key to EC2
echo "📡 Connecting to production server..."
aws ec2-instance-connect send-ssh-public-key \
    --instance-id i-0d394d6974a0e8021 \
    --instance-os-user ubuntu \
    --ssh-public-key file://"${TEMP_KEY}.pub" \
    --availability-zone us-east-1c \
    --region us-east-1 > /dev/null 2>&1

# Step 1: Download production database
echo "📥 Downloading production database..."
ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i "$TEMP_KEY" ubuntu@3.233.250.55 << 'ENDSSH' > /tmp/prod_db_dump.sql
cd /home/ubuntu/SAIGBOX-V3
source venv/bin/activate
python3 << 'PYTHON'
import sqlite3
import json
from datetime import datetime

# Connect to database
conn = sqlite3.connect('saigbox.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Export schema
print("-- SAIGBOX Production Database Dump")
print(f"-- Generated: {datetime.now()}")
print()

# Get all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()

for table in tables:
    table_name = table['name']
    if table_name == 'sqlite_sequence':
        continue
    
    # Get table schema
    cursor.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table_name}';")
    schema = cursor.fetchone()
    if schema:
        print(f"{schema['sql']};")
        print()
    
    # Export data
    cursor.execute(f"SELECT * FROM {table_name}")
    rows = cursor.fetchall()
    
    if rows:
        columns = rows[0].keys()
        for row in rows:
            values = []
            for col in columns:
                val = row[col]
                if val is None:
                    values.append('NULL')
                elif isinstance(val, str):
                    # Escape single quotes
                    val = val.replace("'", "''")
                    values.append(f"'{val}'")
                else:
                    values.append(str(val))
            
            insert_sql = f"INSERT INTO {table_name} ({','.join(columns)}) VALUES ({','.join(values)});"
            print(insert_sql)
        print()

conn.close()
PYTHON
ENDSSH

if [ -s /tmp/prod_db_dump.sql ]; then
    echo "✅ Database downloaded successfully"
else
    echo "❌ Failed to download database"
    rm -f "$TEMP_KEY" "${TEMP_KEY}.pub"
    exit 1
fi

# Step 2: Download production code files
echo "📥 Downloading production code..."
mkdir -p /tmp/prod_backup

# Download key Python files
for file in "api/main.py" "api/routes/emails.py" "api/routes/trash.py" "api/routes/saig.py" \
            "core/saig_assistant.py" "core/saig_assistant_simple.py" "core/gmail_service.py" \
            "core/urgency_detector.py" "static/index.html" "static/dashboard-index.html"; do
    echo "  Downloading $file..."
    scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i "$TEMP_KEY" \
        ubuntu@3.233.250.55:/home/ubuntu/SAIGBOX-V3/$file \
        /tmp/prod_backup/$(basename $file) 2>/dev/null || echo "  ⚠️  Couldn't download $file"
done

# Step 3: Get production environment variables (sanitized)
echo "📥 Getting production configuration..."
ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i "$TEMP_KEY" ubuntu@3.233.250.55 << 'ENDSSH' > /tmp/prod_env.txt
cd /home/ubuntu/SAIGBOX-V3
# Get non-sensitive environment variables
grep -E "^(URGENCY_|ACTION_|ENABLE_|BATCH_|CONFIDENCE_)" .env 2>/dev/null || true
echo "DATABASE_URL=sqlite:///./saigbox.db"
ENDSSH

# Step 4: Backup local database
echo "💾 Backing up local database..."
if [ -f "saigbox.db" ]; then
    cp saigbox.db "saigbox.db.backup.$(date +%Y%m%d_%H%M%S)"
    echo "✅ Local database backed up"
fi

# Step 5: Import production database
echo "📤 Importing production database..."
rm -f saigbox.db
sqlite3 saigbox.db < /tmp/prod_db_dump.sql
echo "✅ Production database imported"

# Step 6: Update environment variables
echo "⚙️  Updating environment configuration..."
if [ -f "/tmp/prod_env.txt" ]; then
    echo "" >> .env
    echo "# Production sync settings - $(date)" >> .env
    cat /tmp/prod_env.txt >> .env
    echo "✅ Environment variables updated"
fi

# Step 7: Sync static files
echo "📥 Syncing static files from production..."
for file in /tmp/prod_backup/*.html; do
    if [ -f "$file" ]; then
        filename=$(basename "$file")
        cp "$file" "static/$filename"
        echo "  ✅ Updated static/$filename"
    fi
done

# Step 8: Sync Python files (optional - ask user)
echo ""
echo "🤔 Do you want to replace your local Python files with production versions?"
echo "   This will overwrite any local changes you've made!"
read -p "Replace Python files? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    for file in /tmp/prod_backup/*.py; do
        if [ -f "$file" ]; then
            filename=$(basename "$file")
            # Find the right directory
            if [[ $filename == saig_assistant* ]] || [[ $filename == gmail_service* ]] || [[ $filename == urgency_detector* ]]; then
                cp "$file" "core/$filename"
                echo "  ✅ Updated core/$filename"
            elif [[ $filename == main.py ]]; then
                cp "$file" "api/$filename"
                echo "  ✅ Updated api/$filename"
            else
                cp "$file" "api/routes/$filename"
                echo "  ✅ Updated api/routes/$filename"
            fi
        fi
    done
fi

# Clean up temporary files
rm -f "$TEMP_KEY" "${TEMP_KEY}.pub"
rm -f /tmp/prod_db_dump.sql
rm -f /tmp/prod_env.txt
rm -rf /tmp/prod_backup

# Step 9: Restart local server
echo ""
echo "🔄 Restarting local server..."
./restart_dev.sh

echo ""
echo "✅ Production sync complete!"
echo ""
echo "📊 Summary:"
echo "  • Database: Synced from production"
echo "  • Static files: Updated to match production"
echo "  • Environment: Production settings applied"
echo ""
echo "🌐 Access your local server at: http://localhost:8000"
echo "   Login with your production credentials"
echo ""
echo "⚠️  Note: Secrets (API keys, tokens) were NOT synced for security."
echo "   You may need to update these in .env if features don't work."