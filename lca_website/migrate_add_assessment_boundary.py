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

                    -- 生命周期模型类型
                    lifecycle_model VARCHAR(50) DEFAULT 'cradle_to_gate',
                    -- cradle_to_gate: 摇篮到大门
                    -- cradle_to_grave: 摇篮到坟墓
                    -- gate_to_gate: 大门到大门
                    -- cradle_to_cradle: 摇篮到摇篮

                    -- 生命周期环节（JSON数组）
                    lifecycle_stages TEXT,
                    -- 示例: ["raw_material", "production", "transport", "use", "disposal"]

                    -- 各环节详细配置（JSON对象）
                    stages_config TEXT,
                    -- 示例: {"raw_material": {"enabled": true, "description": "原材料获取"}, ...}

                    -- 系统边界描述
                    boundary_description TEXT,

                    -- 功能单位
                    functional_unit VARCHAR(100),

                    -- 参考流
                    reference_flow VARCHAR(100),

                    -- 截断规则
                    cutoff_criteria TEXT,
                    cutoff_threshold FLOAT DEFAULT 1.0,
                    -- 默认1% 截断阈值

                    -- 工艺流程图
                    process_flow_diagram VARCHAR(500),
                    -- 存储工艺流程图文件路径

                    -- 地理边界
                    geographical_boundary VARCHAR(200),

                    -- 时间边界
                    temporal_boundary VARCHAR(200),

                    -- 技术边界
                    technological_boundary TEXT,

                    -- 分配方法
                    allocation_method VARCHAR(50) DEFAULT 'mass',
                    -- mass: 质量分配
                    -- economic: 经济价值分配
                    -- physical: 物理因果关系分配

                    -- 分配说明
                    allocation_description TEXT,

                    -- 元数据
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
