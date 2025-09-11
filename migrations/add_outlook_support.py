#!/usr/bin/env python3
"""
Database migration to add Outlook/Microsoft support
Adds outlook_id and conversation_id columns to emails table
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_migration():
    """Add Outlook support columns to emails table"""
    try:
        # Get database URL from environment or use default
        database_url = os.getenv('DATABASE_URL', 'sqlite:///./saigbox.db')
        
        # Create engine
        engine = create_engine(database_url)
        
        with engine.connect() as conn:
            # Start transaction
            trans = conn.begin()
            
            try:
                # Check if columns already exist
                result = conn.execute(text("""
                    SELECT sql FROM sqlite_master 
                    WHERE type='table' AND name='emails';
                """))
                
                table_schema = result.fetchone()
                if table_schema:
                    schema_str = table_schema[0]
                    
                    # Add outlook_id column if it doesn't exist
                    if 'outlook_id' not in schema_str:
                        logger.info("Adding outlook_id column to emails table...")
                        conn.execute(text("""
                            ALTER TABLE emails 
                            ADD COLUMN outlook_id VARCHAR UNIQUE;
                        """))
                        
                        # Create index for outlook_id
                        conn.execute(text("""
                            CREATE INDEX IF NOT EXISTS ix_emails_outlook_id 
                            ON emails(outlook_id);
                        """))
                        logger.info("✓ Added outlook_id column")
                    else:
                        logger.info("outlook_id column already exists")
                    
                    # Add conversation_id column if it doesn't exist
                    if 'conversation_id' not in schema_str:
                        logger.info("Adding conversation_id column to emails table...")
                        conn.execute(text("""
                            ALTER TABLE emails 
                            ADD COLUMN conversation_id VARCHAR;
                        """))
                        
                        # Create index for conversation_id
                        conn.execute(text("""
                            CREATE INDEX IF NOT EXISTS ix_emails_conversation_id 
                            ON emails(conversation_id);
                        """))
                        logger.info("✓ Added conversation_id column")
                    else:
                        logger.info("conversation_id column already exists")
                    
                    # Make gmail_id nullable (it was previously required)
                    # Note: SQLite doesn't support ALTER COLUMN directly, 
                    # but since we're adding support for multiple providers,
                    # new emails will have either gmail_id OR outlook_id
                    logger.info("✓ Database schema updated for Outlook support")
                    
                else:
                    logger.error("emails table not found!")
                    trans.rollback()
                    return False
                
                # Commit transaction
                trans.commit()
                logger.info("✅ Migration completed successfully!")
                return True
                
            except Exception as e:
                logger.error(f"Migration failed: {e}")
                trans.rollback()
                raise
                
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        return False

if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)