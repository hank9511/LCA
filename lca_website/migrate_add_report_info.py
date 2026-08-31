import sqlite3
import os
from datetime import datetime


def migrate_database(db_path):

    print(f"正在迁移数据库: {db_path}")

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
            print("表 'project_report_info' 已存在，跳过创建")
            return

        cursor.execute(
            """
            CREATE TABLE project_report_info (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL UNIQUE,

                -- 基本信息 [1-9]
                product_name TEXT,
                product_model TEXT,
                producer_name TEXT,
                report_no TEXT,
                address TEXT,
                legal_representative TEXT,
                contact_person TEXT,
                contact_phone TEXT,
                contact_email TEXT,

                -- 产品功能与标准 [10-11]
                product_function TEXT,
                standard_used TEXT DEFAULT 'IPCC 2013 GWP 100a',

                -- 量化目的与范围 [12-16]
                quantitative_purpose TEXT,
                functional_unit TEXT,
                system_boundary_description TEXT,
                system_boundary_stages TEXT,  -- JSON: ["raw_material", "production", "distribution", "use", "end_of_life"]
                cutoff_criteria TEXT,
                time_scale TEXT,

                -- 数据来源 [17-18]
                primary_data_source TEXT,
                secondary_data_source TEXT,

                -- 分配方法 [19-21]
                allocation_basis TEXT,
                allocation_procedure TEXT,
                specific_allocations TEXT,

                -- 数据质量评价 [22]
                data_quality_notes TEXT,

                -- 影响评估 [23]
                impact_type_description TEXT DEFAULT '100-year global warming potential (GWP) given by IPCC',

                -- 结果解释 [27-28]
                assumptions_limitations TEXT,
                improvement_suggestions TEXT,

                -- 其他设置
                enable_ai_suggestions BOOLEAN DEFAULT 1,
                report_language TEXT DEFAULT 'en',  -- en, zh

                -- 元数据
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
        print("✓ 成功创建表 'project_report_info'")

        cursor.execute("SELECT id, name FROM project")
        projects = cursor.fetchall()

        if projects:
            print(f"为 {len(projects)} 个现有项目创建默认报告信息...")
            for project_id, project_name in projects:
                cursor.execute(
                    """
                    INSERT INTO project_report_info (project_id, product_name)
                    VALUES (?, ?)
                """,
                    (project_id, project_name),
                )
            conn.commit()
            print(f"✓ 成功为 {len(projects)} 个项目创建默认记录")

    except sqlite3.Error as e:
        print(f"✗ 数据库迁移失败: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

    print("数据库迁移完成！")


if __name__ == "__main__":

    basedir = os.path.abspath(os.path.dirname(__file__))
    db_path = os.path.join(basedir, "instance", "lca_website.db")

    if not os.path.exists(db_path):
        print(f"错误: 数据库文件不存在: {db_path}")
        print("请先运行主应用创建数据库")
        exit(1)

    migrate_database(db_path)
