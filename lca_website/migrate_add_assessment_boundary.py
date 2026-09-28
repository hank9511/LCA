import sqlite3
import os
from datetime import datetime

basedir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(basedir, "instance", "lca_website.db")


def migrate():

    print(f"连接数据库: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:

        cursor.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='assessment_boundary'
        """
        )

        if cursor.fetchone():
            print("[OK] 评价边界表已存在，跳过创建")
        else:

            cursor.execute(
                """
                CREATE TABLE assessment_boundary (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id VARCHAR(8) NOT NULL,

                    -- Lifecycle model type
                    lifecycle_model VARCHAR(50) DEFAULT 'cradle_to_gate',
                    -- cradle_to_gate: cradle-to-gate
                    -- cradle_to_grave: cradle-to-grave
                    -- gate_to_gate: gate-to-gate
                    -- cradle_to_cradle: cradle-to-cradle

                    -- Lifecycle stages (JSON array)
                    lifecycle_stages TEXT,
                    -- Example: ["raw_material", "production", "transport", "use", "disposal"]

                    -- Per-stage configuration (JSON object)
                    stages_config TEXT,
                    -- Example: {"raw_material": {"enabled": true, "description": "raw material acquisition"}, ...}

                    -- System boundary description
                    boundary_description TEXT,

                    -- Functional unit
                    functional_unit VARCHAR(100),

                    -- Reference flow
                    reference_flow VARCHAR(100),

                    -- Cut-off criteria
                    cutoff_criteria TEXT,
                    cutoff_threshold FLOAT DEFAULT 1.0,
                    -- Default 1% cut-off threshold

                    -- Process flow diagram
                    process_flow_diagram VARCHAR(500),
                    -- Stores the process flow diagram file path

                    -- Geographical boundary
                    geographical_boundary VARCHAR(200),

                    -- Temporal boundary
                    temporal_boundary VARCHAR(200),

                    -- Technological boundary
                    technological_boundary TEXT,

                    -- Allocation method
                    allocation_method VARCHAR(50) DEFAULT 'mass',
                    -- mass: mass allocation
                    -- economic: economic allocation
                    -- physical: physical causal allocation

                    -- Allocation description
                    allocation_description TEXT,

                    -- Metadata
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                    FOREIGN KEY (project_id) REFERENCES project (id) ON DELETE CASCADE
                )
            """
            )

            cursor.execute(
                """
                CREATE INDEX idx_assessment_boundary_project
                ON assessment_boundary(project_id)
            """
            )

            print("[OK] 成功创建评价边界表")

        conn.commit()
        print("[SUCCESS] 数据库迁移完成！")

    except Exception as e:
        print(f"[ERROR] 迁移失败: {str(e)}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
