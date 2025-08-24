#!/usr/bin/env python3
"""
Emergency database fix script to add missing columns
"""
import sqlite3
import sys

def fix_database():
    try:
        conn = sqlite3.connect('saigbox.db')
        cursor = conn.cursor()
        
        # Check which columns exist
        cursor.execute("PRAGMA table_info(emails)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        
        # Add missing urgency columns if they don't exist
        columns_to_add = [
            ("is_urgent", "BOOLEAN DEFAULT FALSE"),
            ("urgency_score", "INTEGER DEFAULT 0"),
            ("urgency_reason", "TEXT"),
            ("urgency_analyzed_at", "DATETIME"),
            ("auto_actions_created", "BOOLEAN DEFAULT FALSE"),
            ("action_count", "INTEGER DEFAULT 0"),
            ("created_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
            ("updated_at", "DATETIME DEFAULT CURRENT_TIMESTAMP")
        ]
        
        for column_name, column_def in columns_to_add:
            if column_name not in existing_columns:
                try:
                    alter_sql = f"ALTER TABLE emails ADD COLUMN {column_name} {column_def}"
                    cursor.execute(alter_sql)
                    print(f"✓ Added column: {column_name}")
                except sqlite3.OperationalError as e:
                    if "duplicate column name" not in str(e):
                        print(f"✗ Error adding {column_name}: {e}")
        
        conn.commit()
        print("\n✓ Database schema updated successfully!")
        
        # Verify the columns were added
        cursor.execute("PRAGMA table_info(emails)")
        columns = cursor.fetchall()
        print("\nCurrent email table columns:")
        for col in columns:
            print(f"  - {col[1]} ({col[2]})")
            
        conn.close()
        return True
        
    except Exception as e:
        print(f"✗ Database fix failed: {e}")
        return False

if __name__ == "__main__":
    success = fix_database()
    sys.exit(0 if success else 1)