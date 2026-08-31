import olca_ipc as ipc
import olca_schema as o
import os
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import numpy as np
from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image,
    PageBreak,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import io
import traceback


class LCAReportService:

    COLOR_SCHEMES = {
        "default": [
            "#36A2EB",
            "#FF6384",
            "#4BC0C0",
            "#9966FF",
            "#FF9F40",
            "#FFCD56",
            "#C9CBCF",
            "#4BC0C0",
            "#FF6384",
            "#36A2EB",
        ],
        "green": [
            "#2ECC71",
            "#E74C3C",
            "#3498DB",
            "#9B59B6",
            "#F39C12",
            "#1ABC9C",
            "#34495E",
            "#E67E22",
            "#95A5A6",
            "#16A085",
        ],
        "blue": [
            "#3498DB",
            "#E74C3C",
            "#2ECC71",
            "#9B59B6",
            "#F39C12",
            "#1ABC9C",
            "#34495E",
            "#E67E22",
            "#95A5A6",
            "#16A085",
        ],
        "rainbow": [
            "#FF6B6B",
            "#4ECDC4",
            "#45B7D1",
            "#96CEB4",
            "#FFEAA7",
            "#DDA0DD",
            "#98D8C8",
            "#F7DC6F",
            "#BB8FCE",
            "#85C1E9",
        ],
    }

    def __init__(self):

        self._configure_matplotlib_fonts()
        self.chinese_font = self._register_reportlab_fonts()

    def _configure_matplotlib_fonts(self):

        chinese_fonts = [
            "SimHei",
            "Microsoft YaHei",
            "Noto Sans CJK SC",
            "Source Han Sans SC",
            "WenQuanYi Micro Hei",
            "Arial Unicode MS",
        ]

        available_fonts = [f.name for f in fm.fontManager.ttflist]
        valid_fonts = [font for font in chinese_fonts if font in available_fonts]

        if valid_fonts:
            plt.rcParams["font.sans-serif"] = valid_fonts + ["Arial", "DejaVu Sans"]
        else:
            plt.rcParams["font.sans-serif"] = ["Arial", "DejaVu Sans"]

        plt.rcParams["axes.unicode_minus"] = False
        plt.rcParams["font.size"] = 10

    def _register_reportlab_fonts(self):

        try:
            font_paths = [
                "C:/Windows/Fonts/simhei.ttf",
                "C:/Windows/Fonts/msyh.ttf",
                "C:/Windows/Fonts/simsun.ttc",
                "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
                "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
                "/System/Library/Fonts/PingFang.ttc",
                "/System/Library/Fonts/STHeiti Light.ttc",
            ]

            font_priority = [
                ("simhei", "SimHei"),
                ("msyh", "MicrosoftYaHei"),
                ("simsun", "SimSun"),
                ("noto", "NotoSansCJK"),
                ("pingfang", "PingFang"),
                ("wqy", "WenQuanYi"),
            ]

            for font_path in font_paths:
                if os.path.exists(font_path):
                    try:
                        for keyword, register_name in font_priority:
                            if keyword.lower() in font_path.lower():
                                pdfmetrics.registerFont(
                                    TTFont(register_name, font_path)
                                )
                                print(f"✅ 成功注册字体: {register_name}")
                                return register_name
                    except Exception as e:
                        continue

            print("⚠️ 未找到中文字体，使用默认字体")
            return "Helvetica"

        except Exception as e:
            print(f"❌ 字体注册失败: {e}")
            return "Helvetica"

    def get_lca_data_from_openlca(self, port=8080, project_name=None, max_variants=10):

        try:
            client = ipc.Client(port)
            print(f"✅ 成功连接到OpenLCA IPC服务器 (端口: {port})")

            if project_name:
                possible_project_names = [project_name]
            else:
                all_projects = client.get_all(o.Project)
                if not all_projects:
                    print("❌ 未找到任何项目")
                    return None
                possible_project_names = [proj.name for proj in all_projects]

            project_ref = None
            selected_project_name = None
            for proj_name in possible_project_names:
                project_ref = client.find(o.Project, proj_name)
                if project_ref:
                    selected_project_name = proj_name
                    print(f"✅ 找到项目: {proj_name}")
                    break

            if not project_ref:
                print(f"❌ 未找到项目")
                return None

            project = client.get(o.Project, project_ref.id)

            variants = []
            for variant in project.variants:
                if variant.product_system:
                    variants.append(
                        {
                            "name": variant.name,
                            "product_system": variant.product_system,
                            "amount": variant.amount,
                            "unit": variant.unit,
                        }
                    )

            if len(variants) < 2:
                print("❌ 项目需要至少2个变体进行对比")
                return None

            if len(variants) > max_variants:
                variants = variants[:max_variants]

            print(f"✅ 发现 {len(variants)} 个变体: {[v['name'] for v in variants]}")

            impact_method = project.impact_method
            if not impact_method:
                print("❌ 项目未配置影响评估方法")
                return None

            print("🔄 正在计算所有产品系统...")
            calculation_results = []

            for i, variant in enumerate(variants):
                print(f"   计算变体 {i+1}/{len(variants)}: {variant['name']}")
                setup = o.CalculationSetup(
                    target=variant["product_system"], impact_method=impact_method
                )
                result = client.calculate(setup)
                try:
                    result.wait_until_ready()
                    impacts = result.get_total_impacts()
                    calculation_results.append(
                        {
                            "variant_name": variant["name"],
                            "impacts": impacts,
                            "result": result,
                        }
                    )
                except Exception as e:
                    print(f"   ⚠️ {variant['name']} 计算出错: {e}")
                    calculation_results.append(
                        {
                            "variant_name": variant["name"],
                            "impacts": [],
                            "result": result,
                        }
                    )

            lca_data = {
                "project_name": project.name,
                "impact_method": impact_method.name,
                "calculation_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "variants": [],
                "comparison_data": [],
            }

            for calc_result in calculation_results:
                variant_data = {"name": calc_result["variant_name"], "impacts": []}

                for impact in calc_result["impacts"]:
                    if impact.impact_category:
                        variant_data["impacts"].append(
                            {
                                "category": impact.impact_category.name,
                                "amount": impact.amount,
                                "unit": impact.impact_category.ref_unit,
                            }
                        )

                lca_data["variants"].append(variant_data)

            if len(lca_data["variants"]) >= 2:
                all_categories = set()
                for variant in lca_data["variants"]:
                    for impact in variant["impacts"]:
                        all_categories.add(impact["category"])

                for category in all_categories:
                    category_data = {"category": category, "values": {}, "units": {}}

                    for variant in lca_data["variants"]:
                        variant_impact = next(
                            (
                                imp
                                for imp in variant["impacts"]
                                if imp["category"] == category
                            ),
                            None,
                        )
                        if variant_impact:
                            category_data["values"][variant["name"]] = abs(
                                variant_impact["amount"]
                            )
                            category_data["units"][variant["name"]] = variant_impact[
                                "unit"
                            ]
                        else:
                            category_data["values"][variant["name"]] = 0.0
                            category_data["units"][variant["name"]] = ""

                    max_val = (
                        max(category_data["values"].values())
                        if category_data["values"].values()
                        else 0
                    )
                    if max_val > 0:
                        category_data["relative_values"] = {
                            name: (val / max_val) * 100
                            for name, val in category_data["values"].items()
                        }
                    else:
                        category_data["relative_values"] = {
                            name: 0 for name in category_data["values"].keys()
                        }

                    lca_data["comparison_data"].append(category_data)

            for calc_result in calculation_results:
                if calc_result["result"]:
                    calc_result["result"].dispose()

            print(
                f"✅ 成功获取LCA数据，包含 {len(lca_data['variants'])} 个变体，{len(lca_data['comparison_data'])} 个影响类别"
            )
            return lca_data

        except Exception as e:
            print(f"❌ 获取LCA数据时出错: {e}")
            traceback.print_exc()
            return None

    def create_comparison_chart(self, lca_data, color_scheme="default"):

        try:
            if not lca_data or not lca_data.get("comparison_data"):
                print("❌ 没有对比数据，无法生成图表")
                return None

            variant_names = [v["name"] for v in lca_data["variants"]]
            colors_list = self.COLOR_SCHEMES.get(
                color_scheme, self.COLOR_SCHEMES["default"]
            )

            max_categories = 15
            comparison_data = lca_data["comparison_data"][:max_categories]

            categories = []
            for item in comparison_data:
                category_name = item["category"]
                if len(category_name) > 20:
                    category_name = category_name[:17] + "..."
                categories.append(category_name)

            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 14))
            fig.suptitle(
                f'{lca_data["project_name"]} - 环境影响对比分析',
                fontsize=16,
                fontweight="bold",
                y=0.95,
            )

            x_pos = np.arange(len(categories))
            width = 0.8 / len(variant_names)

            bars_list = []
            for i, variant_name in enumerate(variant_names):
                values = []
                for item in comparison_data:
                    values.append(item["values"].get(variant_name, 0))

                color = colors_list[i % len(colors_list)]
                bars = ax1.bar(
                    x_pos + i * width - width * (len(variant_names) - 1) / 2,
                    values,
                    width,
                    label=variant_name,
                    color=color,
                    alpha=0.8,
                )
                bars_list.append(bars)

            ax1.set_xlabel("环境影响类别", fontsize=12)
            ax1.set_ylabel("环境影响值", fontsize=12)
            ax1.set_title("绝对数值对比", fontsize=14, fontweight="bold")
            ax1.set_xticks(x_pos)
            ax1.set_xticklabels(categories, rotation=45, ha="right", fontsize=10)
            ax1.legend(bbox_to_anchor=(1.05, 1), loc="upper left")
            ax1.grid(True, alpha=0.3, axis="y")

            bars_list2 = []
            for i, variant_name in enumerate(variant_names):
                relative_values = []
                for item in comparison_data:
                    relative_values.append(item["relative_values"].get(variant_name, 0))

                color = colors_list[i % len(colors_list)]
                bars = ax2.bar(
                    x_pos + i * width - width * (len(variant_names) - 1) / 2,
                    relative_values,
                    width,
                    label=f"{variant_name} (%)",
                    color=color,
                    alpha=0.8,
                )
                bars_list2.append(bars)

            ax2.set_xlabel("环境影响类别", fontsize=12)
            ax2.set_ylabel("相对表现 (%)", fontsize=12)
            ax2.set_title("相对表现对比 (%)", fontsize=14, fontweight="bold")
            ax2.set_xticks(x_pos)
            ax2.set_xticklabels(categories, rotation=45, ha="right", fontsize=10)
            ax2.set_ylim(0, 105)
            ax2.legend(bbox_to_anchor=(1.05, 1), loc="upper left")
            ax2.grid(True, alpha=0.3, axis="y")

            plt.tight_layout()
            plt.subplots_adjust(top=0.92, right=0.85)

            img_buffer = io.BytesIO()
            plt.savefig(
                img_buffer,
                format="png",
                dpi=300,
                bbox_inches="tight",
                facecolor="white",
                edgecolor="none",
            )
            img_buffer.seek(0)
            plt.close()

            return img_buffer

        except Exception as e:
            print(f"❌ 创建图表时出错: {e}")
            traceback.print_exc()
            return None

    def _blank_line(self, length=16):

        try:
            length = int(length)
        except Exception:
            length = 16
        return "_" * max(6, min(40, length))

    def _fmt_or_blank(self, value, blank_len=16):

        if value is None:
            return self._blank_line(blank_len)
        if isinstance(value, str):
            v = value.strip()
            return v if v else self._blank_line(blank_len)
        try:
            return str(value)
        except Exception:
            return self._blank_line(blank_len)

    def create_pdf_report(
        self, lca_data, output_path, template_type="gb24067", color_scheme="default"
    ):

        if not lca_data:
            print("❌ 没有LCA数据，无法生成报告")
            return False

        try:

            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            doc = SimpleDocTemplate(
                output_path,
                pagesize=A4,
                rightMargin=72,
                leftMargin=72,
                topMargin=72,
                bottomMargin=72,
            )

            styles = getSampleStyleSheet()
            story = []

            title_style = ParagraphStyle(
                "Title",
                parent=styles["Heading1"],
                fontSize=20,
                spaceAfter=30,
                alignment=TA_CENTER,
                textColor=colors.black,
                fontName=self.chinese_font,
                leading=24,
            )

            story.append(Paragraph("LCA环境影响评估报告", title_style))
            story.append(Spacer(1, 40))

            normal_style = ParagraphStyle(
                "Normal",
                parent=styles["Normal"],
                fontSize=11,
                spaceAfter=6,
                fontName=self.chinese_font,
                leading=13,
            )

            project_info = [
                ["项目名称:", self._fmt_or_blank(lca_data.get("project_name"), 30)],
                [
                    "影响评估方法:",
                    self._fmt_or_blank(lca_data.get("impact_method"), 30),
                ],
                ["计算时间:", self._fmt_or_blank(lca_data.get("calculation_time"), 30)],
                [
                    "变体数量:",
                    self._fmt_or_blank(str(len(lca_data.get("variants", []))), 30),
                ],
            ]

            project_table = Table(project_info, colWidths=[1.5 * inch, 4.0 * inch])
            project_table.setStyle(
                TableStyle(
                    [
                        ("FONTNAME", (0, 0), (-1, -1), self.chinese_font),
                        ("FONTSIZE", (0, 0), (-1, -1), 11),
                        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 8),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                        ("TOPPADDING", (0, 0), (-1, -1), 8),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ]
                )
            )
            story.append(project_table)
            story.append(PageBreak())

            chart_buffer = self.create_comparison_chart(lca_data, color_scheme)
            if chart_buffer:
                try:
                    chart_img = Image(chart_buffer, width=6 * inch, height=4.5 * inch)
                    chart_img.hAlign = "CENTER"
                    story.append(Spacer(1, 20))

                    heading_style = ParagraphStyle(
                        "Heading",
                        parent=styles["Heading2"],
                        fontSize=14,
                        spaceBefore=16,
                        spaceAfter=10,
                        textColor=colors.black,
                        fontName=self.chinese_font,
                    )
                    story.append(Paragraph("环境影响对比图表", heading_style))
                    story.append(chart_img)
                    story.append(Spacer(1, 20))
                except Exception as e:
                    print(f"⚠️ 添加图表到PDF时出错: {e}")

            doc.build(story)

            print(f"✅ PDF报告生成成功: {output_path}")
            return True

        except Exception as e:
            print(f"❌ 生成PDF报告时出错: {e}")
            traceback.print_exc()
            return False

    def generate_report(
        self,
        project_name=None,
        output_path=None,
        port=8080,
        template_type="gb24067",
        color_scheme="default",
    ):

        try:

            lca_data = self.get_lca_data_from_openlca(
                port=port, project_name=project_name
            )

            if not lca_data:
                return {
                    "success": False,
                    "error": "无法获取LCA数据，请确保OpenLCA正在运行且项目存在",
                }

            if not output_path:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_path = f"LCA报告_{timestamp}.pdf"

            success = self.create_pdf_report(
                lca_data,
                output_path,
                template_type=template_type,
                color_scheme=color_scheme,
            )

            if success:
                return {
                    "success": True,
                    "message": "报告生成成功",
                    "file_path": output_path,
                }
            else:
                return {"success": False, "error": "报告生成失败"}

        except Exception as e:
            return {"success": False, "error": f"报告生成过程中出错: {str(e)}"}


report_service = LCAReportService()
