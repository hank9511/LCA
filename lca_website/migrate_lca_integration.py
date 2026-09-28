"""Database migration script for LCA integration"""

import os
import sys
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from app import app, db


def migrate_database():
    """Migrate database to add LCA integration features"""

    print("🔄 Starting database migration...")

    with app.app_context():
        try:

            print("📊 Creating LCAResult table...")

            from sqlalchemy import inspect

            inspector = inspect(db.engine)
            existing_tables = inspector.get_table_names()

            if "lca_result" in existing_tables:
                print("⚠️ LCAResult table already exists, skipping creation")
            else:

                from app import LCAResult

                db.create_all()
                print("✅ LCAResult table created successfully")

            excel_file_columns = [
                col["name"] for col in inspector.get_columns("excel_file")
            ]
            print(f"📋 Current ExcelFile table columns: {excel_file_columns}")

            print("✅ Database migration complete!")
            print("\n🎉 LCA integration features are ready!")
            print("\n📖 Instructions:")
            print("1. Ensure openLCA is running")
            print("2. Enable the IPC server in openLCA (Developer Tools → IPC Server)")
            print("3. Set the IPC server port to 8080")
            print("4. Click the 'Run LCA Analysis' button on the project detail page")
            print("5. View analysis results and details")

        except Exception as e:
            print(f"❌ Database migration failed: {e}")
            import traceback

            traceback.print_exc()
            return False

    return True


if __name__ == "__main__":
    success = migrate_database()
    if success:
        print("\n🚀 Migration succeeded! You can now use LCA analysis features.")
    else:
        print("\n💥 Migration failed! Please check the error messages and retry.")
