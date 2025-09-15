#!/usr/bin/env python3
"""
Migration script to add outlook_id column to emails table if it doesn't exist.
"""
import sqlite3
import sys

def add_outlook_column():
    """Add outlook_id and conversation_id columns to emails table if they don't exist."""
    try:
        # Connect to database
        conn = sqlite3.connect('saigbox.db')
        cursor = conn.cursor()
        
        # Check if columns exist
        cursor.execute("PRAGMA table_info(emails)")
        columns = [column[1] for column in cursor.fetchall()]
        
        # Add outlook_id if missing
        if 'outlook_id' not in columns:
            print("Adding outlook_id column to emails table...")
            cursor.execute("""
                ALTER TABLE emails 
                ADD COLUMN outlook_id VARCHAR
            """)
            
            # Create unique index for better performance
            cursor.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS ix_emails_outlook_id 
                ON emails(outlook_id)
            """)
            
            conn.commit()
            print("✅ Successfully added outlook_id column")
        else:
            print("✅ outlook_id column already exists")
        
        # Add conversation_id if missing  
        if 'conversation_id' not in columns:
            print("Adding conversation_id column to emails table...")
            cursor.execute("""
                ALTER TABLE emails 
                ADD COLUMN conversation_id VARCHAR
            """)
            
            # Create index for better performance
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS ix_emails_conversation_id 
                ON emails(conversation_id)
            """)
            
            conn.commit()
            print("✅ Successfully added conversation_id column")
        else:
            print("✅ conversation_id column already exists")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Error adding outlook_id column: {e}")
        return False

if __name__ == "__main__":
    success = add_outlook_column()
    sys.exit(0 if success else 1)