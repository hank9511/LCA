import sqlite3
import os
from datetime import datetime


def migrate_database(db_path):

    print(f"Migrating database: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:

        cursor.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='project_report_info'
        """
        )

        if cursor.fetchone():
            print("Table 'project_report_info' already exists, skipping creation")
            return

        cursor.execute(
            """
            CREATE TABLE project_report_info (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL UNIQUE,

                -- Basic information [1-9]
                product_name TEXT,
                product_model TEXT,
                producer_name TEXT,
                report_no TEXT,
                address TEXT,
                legal_representative TEXT,
                contact_person TEXT,
                contact_phone TEXT,
                contact_email TEXT,

                -- Product function and standard [10-11]
                product_function TEXT,
                standard_used TEXT DEFAULT 'IPCC 2013 GWP 100a',

                -- Quantification purpose and scope [12-16]
                quantitative_purpose TEXT,
                functional_unit TEXT,
                system_boundary_description TEXT,
                system_boundary_stages TEXT,  -- JSON: ["raw_material", "production", "distribution", "use", "end_of_life"]
                cutoff_criteria TEXT,
                time_scale TEXT,

                -- Data sources [17-18]
                primary_data_source TEXT,
                secondary_data_source TEXT,

                -- Allocation method [19-21]
                allocation_basis TEXT,
                allocation_procedure TEXT,
                specific_allocations TEXT,

                -- Data quality assessment [22]
                data_quality_notes TEXT,

                -- Impact assessment [23]
                impact_type_description TEXT DEFAULT '100-year global warming potential (GWP) given by IPCC',

                -- Interpretation of results [27-28]
                assumptions_limitations TEXT,
                improvement_suggestions TEXT,

                -- Other settings
                enable_ai_suggestions BOOLEAN DEFAULT 1,
                report_language TEXT DEFAULT 'en',  -- en, zh

                -- Metadata
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (project_id) REFERENCES project(id) ON DELETE CASCADE
            )
        """
        )

        cursor.execute(
            """
            CREATE INDEX idx_project_report_info_project_id
            ON project_report_info(project_id)
        """
        )

        conn.commit()
        print("✓ Successfully created table 'project_report_info'")

        cursor.execute("SELECT id, name FROM project")
        projects = cursor.fetchall()

        if projects:
            print(f"Creating default report info for {len(projects)} existing projects...")
            for project_id, project_name in projects:
                cursor.execute(
                    """
                    INSERT INTO project_report_info (project_id, product_name)
                    VALUES (?, ?)
                """,
                    (project_id, project_name),
                )
            conn.commit()
            print(f"✓ Successfully created default records for {len(projects)} projects")

    except sqlite3.Error as e:
        print(f"✗ Database migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

    print("Database migration complete!")


if __name__ == "__main__":

    basedir = os.path.abspath(os.path.dirname(__file__))
    db_path = os.path.join(basedir, "instance", "lca_website.db")

    if not os.path.exists(db_path):
        print(f"Error: database file does not exist: {db_path}")
        print("Please run the main application first to create the database")
        exit(1)

    migrate_database(db_path)
