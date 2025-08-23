#!/usr/bin/env python3
"""Initialize the database with updated schema"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.database import Base, engine
from sqlalchemy import inspect

def init_database():
    """Create all tables in the database"""
    print("Initializing database...")
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    # List created tables
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    
    print(f"Database initialized with {len(tables)} tables:")
    for table in tables:
        columns = inspector.get_columns(table)
        print(f"  - {table} ({len(columns)} columns)")
    
    print("\nDatabase initialization complete!")

if __name__ == "__main__":
    init_database()