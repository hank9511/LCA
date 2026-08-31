import sqlite3
import os


def migrate_project_tables_cascade():

    db_path = os.path.join(os.path.dirname(__file__), "instance", "lca_website.db")

    if not os.path.exists(db_path):
        print(f"数据库文件不存在: {db_path}")
        return

    print(f"正在迁移数据库: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        print("开始迁移项目关联表...")

        cursor.execute("PRAGMA foreign_keys=OFF")

        print("\n[1/2] 迁移 assessment_boundary 表...")

        cursor.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='assessment_boundary'
        """
        )

        if cursor.fetchone():

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS assessment_boundary_backup AS
                SELECT * FROM assessment_boundary
            """
            )
            print("  ✓ 已备份现有数据")

            cursor.execute("DROP TABLE IF EXISTS assessment_boundary")
            print("  ✓ 已删除旧表")

            cursor.execute(
                """
                CREATE TABLE assessment_boundary (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id VARCHAR(8) NOT NULL,
                    lifecycle_model VARCHAR(50) DEFAULT 'cradle_to_gate',
                    lifecycle_stages TEXT,
                    stages_config TEXT,
                    boundary_description TEXT,
                    functional_unit VARCHAR(100),
                    reference_flow VARCHAR(100),
                    cutoff_criteria TEXT,
                    cutoff_threshold FLOAT DEFAULT 1.0,
                    process_flow_diagram VARCHAR(500),
                    geographical_boundary VARCHAR(200),
                    temporal_boundary VARCHAR(200),
                    technological_boundary TEXT,
                    allocation_method VARCHAR(50) DEFAULT 'mass',
                    allocation_description TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES project(id) ON DELETE CASCADE
                )
            """
            )
            print("  ✓ 已创建新表（带级联删除）")

            cursor.execute(
                """
                INSERT INTO assessment_boundary
                SELECT * FROM assessment_boundary_backup
            """
            )
            print("  ✓ 已恢复数据")

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_assessment_boundary_project
                ON assessment_boundary(project_id)
            """
            )
            print("  ✓ 已创建索引")

            cursor.execute("DROP TABLE IF EXISTS assessment_boundary_backup")
            print("  ✓ 已清理备份")
        else:
            print("  ⚠️  表不存在，跳过")

        print("\n[2/2] 迁移 project_report_info 表...")

        cursor.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='project_report_info'
        """
        )

        if cursor.fetchone():

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS project_report_info_backup AS
                SELECT * FROM project_report_info
            """
            )
            print("  ✓ 已备份现有数据")

            cursor.execute("DROP TABLE IF EXISTS project_report_info")
            print("  ✓ 已删除旧表")

            cursor.execute(
                """
                CREATE TABLE project_report_info (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id VARCHAR(8) NOT NULL UNIQUE,
                    product_name TEXT,
                    product_model TEXT,
                    producer_name TEXT,
                    report_no TEXT,
                    address TEXT,
                    legal_representative TEXT,
                    contact_person TEXT,
                    contact_phone TEXT,
                    contact_email TEXT,
                    product_function TEXT,
                    standard_used TEXT DEFAULT 'IPCC 2013 GWP 100a',
                    quantitative_purpose TEXT,
                    functional_unit TEXT,
                    system_boundary_description TEXT,
                    system_boundary_stages TEXT,
                    cutoff_criteria TEXT,
                    time_scale TEXT,
                    primary_data_source TEXT,
                    secondary_data_source TEXT,
                    allocation_basis TEXT,
                    allocation_procedure TEXT,
                    specific_allocations TEXT,
                    data_quality_notes TEXT,
                    impact_type_description TEXT DEFAULT '100-year global warming potential (GWP) given by IPCC',
                    assumptions_limitations TEXT,
                    improvement_suggestions TEXT,
                    enable_ai_suggestions BOOLEAN DEFAULT 1,
                    report_language VARCHAR(10) DEFAULT 'en',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES project(id) ON DELETE CASCADE
                )
            """
            )
            print("  ✓ 已创建新表（带级联删除）")

            cursor.execute(
                """
                INSERT INTO project_report_info
                SELECT * FROM project_report_info_backup
            """
            )
            print("  ✓ 已恢复数据")

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_project_report_info_project
                ON project_report_info(project_id)
            """
            )
            print("  ✓ 已创建索引")

            cursor.execute("DROP TABLE IF EXISTS project_report_info_backup")
            print("  ✓ 已清理备份")
        else:
            print("  ⚠️  表不存在，跳过")

        cursor.execute("PRAGMA foreign_keys=ON")

        conn.commit()
        print("\n✅ 迁移成功完成！")

        print("\n验证外键约束...")
        cursor.execute("PRAGMA foreign_key_check(assessment_boundary)")
        errors = cursor.fetchall()
        if errors:
            print("⚠️ assessment_boundary 外键约束检查发现问题:")
            for error in errors:
                print(f"  - {error}")
        else:
            print("✓ assessment_boundary 外键约束检查通过")

        cursor.execute("PRAGMA foreign_key_check(project_report_info)")
        errors = cursor.fetchall()
        if errors:
            print("⚠️ project_report_info 外键约束检查发现问题:")
            for error in errors:
                print(f"  - {error}")
        else:
            print("✓ project_report_info 外键约束检查通过")

    except Exception as e:
        conn.rollback()
        print(f"\n❌ 迁移失败: {str(e)}")
        print("正在尝试恢复...")

        try:

            cursor.execute("DROP TABLE IF EXISTS assessment_boundary")
            cursor.execute(
                """
                CREATE TABLE assessment_boundary AS
                SELECT * FROM assessment_boundary_backup
            """
            )
            cursor.execute("DROP TABLE IF EXISTS assessment_boundary_backup")

            cursor.execute("DROP TABLE IF EXISTS project_report_info")
            cursor.execute(
                """
                CREATE TABLE project_report_info AS
                SELECT * FROM project_report_info_backup
            """
            )
            cursor.execute("DROP TABLE IF EXISTS project_report_info_backup")

            conn.commit()
            print("✓ 已从备份恢复")
        except Exception as restore_error:
            print(f"❌ 恢复失败: {str(restore_error)}")

    finally:
        conn.close()


if __name__ == "__main__":
    print("=" * 70)
    print("修复项目关联表的级联删除配置")
    print("- assessment_boundary")
    print("- project_report_info")
    print("=" * 70)
    print()

    migrate_project_tables_cascade()

    print()
    print("=" * 70)
    print("迁移脚本执行完成")
    print("=" * 70)
