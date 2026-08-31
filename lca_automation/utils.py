import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional
import pandas as pd


def setup_logger(
    name: str = "lca_automation",
    log_file: Optional[str] = None,
    level: int = logging.INFO,
) -> logging.Logger:

    logger = logging.getLogger(name)
    logger.setLevel(level)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_format = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(console_format)
        logger.addHandler(file_handler)

    return logger


def export_results_to_json(
    results: Dict[str, Any], output_path: str, indent: int = 2
) -> bool:

    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=indent, ensure_ascii=False, default=str)

        print(f"✅ 结果已导出到JSON: {output_path}")
        return True

    except Exception as e:
        print(f"❌ JSON导出失败: {e}")
        return False


def export_results_to_excel(results: Dict[str, Any], output_path: str) -> bool:

    try:
        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:

            if "lca_results" in results and results["lca_results"]:
                lca_res = results["lca_results"]

                if "impact_analysis" in lca_res:
                    impact = lca_res["impact_analysis"]
                    impact_results = impact.get("impact_results", [])

                    if impact_results:
                        df_impact = pd.DataFrame(impact_results)
                        df_impact.to_excel(writer, sheet_name="影响评价", index=False)

                if (
                    "contribution_analysis" in lca_res
                    and lca_res["contribution_analysis"]
                ):
                    contrib = lca_res["contribution_analysis"]

                    if "process_contributions" in contrib:
                        proc_contrib = contrib["process_contributions"]
                        if proc_contrib:
                            df_proc = pd.DataFrame(proc_contrib)
                            df_proc.to_excel(writer, sheet_name="过程贡献", index=False)

                if (
                    "uncertainty_analysis" in lca_res
                    and lca_res["uncertainty_analysis"]
                ):
                    unc = lca_res["uncertainty_analysis"]

                    if "impact_categories" in unc:
                        impact_cats = unc["impact_categories"]
                        if impact_cats:
                            df_unc = pd.DataFrame(impact_cats)
                            df_unc.to_excel(
                                writer, sheet_name="不确定性分析", index=False
                            )

            summary_data = {
                "项目": [
                    (
                        results.get("lca_case", {}).get("case_name", "N/A")
                        if results.get("lca_case")
                        else "N/A"
                    )
                ],
                "Flows数量": [len(results.get("flow_refs", {}))],
                "Processes数量": [len(results.get("process_refs", {}))],
                "系统UUID": [results.get("system_uuid", "N/A")],
                "完成时间": [datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
            }
            df_summary = pd.DataFrame(summary_data)
            df_summary.to_excel(writer, sheet_name="摘要", index=False)

        print(f"✅ 结果已导出到Excel: {output_path}")
        return True

    except Exception as e:
        print(f"❌ Excel导出失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def export_results_to_html(results: Dict[str, Any], output_path: str) -> bool:

    try:
        html_content = generate_html_report(results)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        print(f"✅ 结果已导出到HTML: {output_path}")
        return True

    except Exception as e:
        print(f"❌ HTML导出失败: {e}")
        return False


def generate_html_report(results: Dict[str, Any]) -> str:

    html = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>LCA分析报告</title>
        <style>
            body {{
                font-family: 'Microsoft YaHei', Arial, sans-serif;
                max-width: 1200px;
                margin: 0 auto;
                padding: 20px;
                background-color: #f5f5f5;
            }}
            .header {{
                background-color: #2c3e50;
                color: white;
                padding: 30px;
                border-radius: 10px;
                margin-bottom: 20px;
            }}
            .section {{
                background-color: white;
                padding: 20px;
                margin-bottom: 20px;
                border-radius: 10px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            h1 {{
                margin: 0;
                font-size: 2em;
            }}
            h2 {{
                color: #2c3e50;
                border-bottom: 2px solid #3498db;
                padding-bottom: 10px;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin-top: 10px;
            }}
            th, td {{
                padding: 12px;
                text-align: left;
                border-bottom: 1px solid #ddd;
            }}
            th {{
                background-color: #3498db;
                color: white;
            }}
            tr:hover {{
                background-color: #f5f5f5;
            }}
            .metric {{
                display: inline-block;
                margin: 10px;
                padding: 15px;
                background-color: #ecf0f1;
                border-radius: 5px;
                min-width: 200px;
            }}
            .metric-label {{
                font-size: 0.9em;
                color: #7f8c8d;
            }}
            .metric-value {{
                font-size: 1.5em;
                font-weight: bold;
                color: #2c3e50;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🌍 LCA分析报告</h1>
            <p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
    """

    html += """
        <div class="section">
            <h2>📊 工作流摘要</h2>
    """

    lca_case = results.get("lca_case")
    if lca_case:
        html += f"""
            <div class="metric">
                <div class="metric-label">项目名称</div>
                <div class="metric-value">{lca_case.case_name if hasattr(lca_case, 'case_name') else 'N/A'}</div>
            </div>
        """

    html += f"""
            <div class="metric">
                <div class="metric-label">Flows数量</div>
                <div class="metric-value">{len(results.get('flow_refs', {}))}</div>
            </div>
            <div class="metric">
                <div class="metric-label">Processes数量</div>
                <div class="metric-value">{len(results.get('process_refs', {}))}</div>
            </div>
        </div>
    """

    if "lca_results" in results and results["lca_results"]:
        lca_res = results["lca_results"]

        if "impact_analysis" in lca_res:
            impact = lca_res["impact_analysis"]
            impact_results = impact.get("impact_results", [])

            if impact_results:
                html += """
                <div class="section">
                    <h2>🌍 影响评价结果</h2>
                    <table>
                        <tr>
                            <th>影响类别</th>
                            <th>数值</th>
                            <th>单位</th>
                        </tr>
                """

                for imp in impact_results[:10]:
                    cat_name = imp.get("category", "Unknown")
                    value = imp.get("value", 0)
                    unit = imp.get("unit", "")
                    html += f"""
                        <tr>
                            <td>{cat_name}</td>
                            <td>{value:.6e}</td>
                            <td>{unit}</td>
                        </tr>
                    """

                html += """
                    </table>
                </div>
                """

    html += """
    </body>
    </html>
    """

    return html


def validate_excel_file(excel_path: str) -> bool:

    if not os.path.exists(excel_path):
        print(f"❌ Excel文件不存在: {excel_path}")
        return False

    if not excel_path.endswith((".xlsx", ".xls")):
        print(f"❌ 文件格式不正确: {excel_path}")
        return False

    try:

        pd.read_excel(excel_path, nrows=1)
        return True
    except Exception as e:
        print(f"❌ Excel文件读取失败: {e}")
        return False


def get_config_from_file(config_path: str) -> Dict[str, Any]:

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        return config
    except Exception as e:
        print(f"⚠️ 配置文件读取失败: {e}")
        return {}


if __name__ == "__main__":

    print("Utils模块 - 提供日志、导出等工具函数")

    logger = setup_logger()
    logger.info("测试日志功能")

    test_results = {
        "success": True,
        "system_uuid": "test-uuid-12345",
        "flow_refs": {"flow1": {}, "flow2": {}},
        "process_refs": {"process1": {}},
    }

    export_results_to_json(test_results, "test_output.json")
