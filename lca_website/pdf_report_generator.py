"""Professional Bilingual PDF LCA Report Generator"""

import os
import io
import base64
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import numpy as np

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch, cm, mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image,
    PageBreak,
    KeepTogether,
    ListFlowable,
    ListItem,
    HRFlowable,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus.flowables import Flowable

import openai

REPORT_TRANSLATIONS = {
    "title": {
        "zh": "产品碳足迹研究报告",
        "en": "Product Carbon Footprint Study Report",
    },
    "basic_info": {"zh": "基本信息", "en": "Basic Information"},
    "product_name": {"zh": "产品名称", "en": "Product Name"},
    "product_model": {"zh": "产品规格型号", "en": "Product Specification Model"},
    "producer_name": {"zh": "生产商名称", "en": "Producer Name"},
    "report_no": {"zh": "报告编号", "en": "Report No"},
    "date": {"zh": "日期", "en": "Date"},
    "reporting_org": {"zh": "报告机构", "en": "Reporting Organization"},
    "section_1_title": {"zh": "一、一般信息", "en": "I. General Information"},
    "address": {"zh": "地址", "en": "Address"},
    "legal_rep": {"zh": "法定代表人", "en": "Legal Representative"},
    "product_function": {"zh": "产品功能", "en": "Product Function"},
    "standard_used": {"zh": "所依据标准", "en": "Based on the Standard"},
    "section_2_title": {"zh": "二、量化目的", "en": "II. Quantitative Purpose"},
    "section_3_title": {"zh": "三、量化范围", "en": "III. Scope of Quantification"},
    "functional_unit_title": {
        "zh": "1. 功能单位或声明单位",
        "en": "1. Functional or Declaratory Units",
    },
    "functional_unit_desc": {
        "zh": "功能单位或声明单位为",
        "en": "Functional or declarative units in",
    },
    "system_boundary_title": {"zh": "2. 系统边界", "en": "2. System Boundary"},
    "cutoff_title": {"zh": "3. 截断准则", "en": "3. Cut-off Criteria"},
    "cutoff_desc": {
        "zh": "所采用的截断准则基于",
        "en": "The cut-off criteria used are based on",
    },
    "time_scale_title": {"zh": "4. 时间尺度", "en": "4. Time Scale"},
    "section_4_title": {"zh": "四、清单分析", "en": "IV. Inventory Analysis"},
    "data_source_title": {
        "zh": "1. 数据来源描述",
        "en": "1. Description of Data Sources",
    },
    "primary_data": {"zh": "一次数据", "en": "Primary Data"},
    "secondary_data": {"zh": "二次数据", "en": "Secondary Data"},
    "allocation_title": {
        "zh": "2. 分配原则与程序",
        "en": "2. Principles and Procedures for Allocation",
    },
    "allocation_basis": {"zh": "分配基础", "en": "Basis of Allocation"},
    "allocation_procedure": {"zh": "分配程序", "en": "Allocation Procedure"},
    "specific_allocation": {"zh": "具体分配", "en": "Specific Allocations"},
    "data_quality_title": {
        "zh": "3. 数据质量评估（可选）",
        "en": "3. Data Quality Evaluation (Optional)",
    },
    "section_5_title": {"zh": "五、影响评估", "en": "V. Impact Assessment"},
    "impact_type_title": {
        "zh": "1. 影响类型与特征因子选择",
        "en": "1. Impact Type and Characterization Factor Selection",
    },
    "results_title": {
        "zh": "2. 产品碳足迹结果计算",
        "en": "2. Product Carbon Footprint Results Calculation",
    },
    "results_desc": {
        "zh": "由{producer}生产的{product}，每功能单位产品从原材料获取到生命末期的生命周期碳足迹为",
        "en": "The life cycle carbon footprint of {product} produced by {producer}, per functional unit of product, from raw material acquisition to end of life is",
    },
    "figure_1_title": {
        "zh": "图1：生命周期阶段碳排放分布",
        "en": "Figure 1: Carbon Emissions Distribution by Life Cycle Stage",
    },
    "table_1_title": {
        "zh": "表1：生命周期阶段碳排放",
        "en": "Table 1: Carbon Emissions by Life Cycle Stage",
    },
    "table_header_stage": {"zh": "生命周期阶段", "en": "Life Cycle Stage"},
    "table_header_cf": {
        "zh": "碳足迹 (kg CO2-Eq)",
        "en": "Carbon Footprint (kg CO2-Eq)",
    },
    "table_header_percent": {"zh": "百分比 (%)", "en": "Percentage (%)"},
    "stage_raw_material": {"zh": "原材料获取", "en": "Raw Material Acquisition"},
    "stage_production": {"zh": "生产制造", "en": "Production"},
    "stage_distribution": {"zh": "运输配送", "en": "Distribution"},
    "stage_use": {"zh": "使用阶段", "en": "Use"},
    "stage_end_of_life": {"zh": "废弃处理", "en": "End of Life"},
    "stage_total": {"zh": "合计", "en": "Total"},
    "uncertainty_title": {
        "zh": "3. 不确定性分析结果",
        "en": "3. Uncertainty Analysis Results",
    },
    "uncertainty_none": {
        "zh": "本次评估未进行不确定性分析。",
        "en": "Uncertainty analysis was not performed for this assessment.",
    },
    "uncertainty_impact_category": {"zh": "影响类别", "en": "Impact Category"},
    "uncertainty_unit": {"zh": "单位", "en": "Unit"},
    "uncertainty_method": {"zh": "影响方法", "en": "Impact Method"},
    "uncertainty_iterations": {
        "zh": "蒙特卡洛迭代次数",
        "en": "Monte Carlo Iterations",
    },
    "figure_2_title": {
        "zh": "图2：不确定性分析分布",
        "en": "Figure 2: Uncertainty Analysis Distribution",
    },
    "stat_metric": {"zh": "统计指标", "en": "Statistical Metric"},
    "stat_value": {"zh": "数值", "en": "Value"},
    "stat_mean": {"zh": "平均值", "en": "Mean"},
    "stat_std": {"zh": "标准差", "en": "Standard Deviation"},
    "stat_cv": {"zh": "变异系数 (CV)", "en": "Coefficient of Variation (CV)"},
    "stat_median": {"zh": "中位数", "en": "Median"},
    "stat_p5": {"zh": "第5百分位", "en": "5th Percentile"},
    "stat_p95": {"zh": "第95百分位", "en": "95th Percentile"},
    "section_6_title": {"zh": "六、结果解释", "en": "VI. Interpretation of Results"},
    "description_title": {"zh": "1. 结果描述", "en": "1. Description of Results"},
    "assumptions_title": {
        "zh": "2. 假设与局限性说明",
        "en": "2. Statement of Assumptions and Limitations",
    },
    "improvements_title": {"zh": "3. 改进建议", "en": "3. Suggestions for Improvement"},
    "report_generated": {"zh": "报告生成时间", "en": "Report Generated"},
    "generator": {"zh": "生成器", "en": "Generator"},
    "generator_name": {
        "zh": "LCA网站自动报告系统",
        "en": "LCA Website Automated Report System",
    },
    "default_placeholder": {
        "zh": "[由用户提供的信息]",
        "en": "[Information provided by the user]",
    },
    "chart_cf_unit": {"zh": "碳足迹 (kg CO2-Eq)", "en": "Carbon Footprint (kg CO2-Eq)"},
    "chart_frequency": {"zh": "频率", "en": "Frequency"},
    "chart_percentile_5": {"zh": "第5百分位", "en": "5th Percentile"},
    "chart_median": {"zh": "中位数", "en": "Median"},
    "chart_percentile_95": {"zh": "第95百分位", "en": "95th Percentile"},
}


class CenteredImage(Flowable):
    """Custom flowable for centered images in PDF."""

    def __init__(self, image_path_or_buffer, width, height):
        Flowable.__init__(self)
        self.image = Image(image_path_or_buffer, width=width, height=height)
        self.width = width
        self.height = height

    def draw(self):
        self.canv.saveState()
        x = (A4[0] - self.width) / 2 - 72
        self.image.drawOn(self.canv, x, 0)
        self.canv.restoreState()

    def wrap(self, availWidth, availHeight):
        return (availWidth, self.height)


class ProfessionalPDFReportGenerator:
    """Professional bilingual PDF report generator for LCA results."""

    COLORS = {
        "primary": colors.HexColor("#1565C0"),
        "secondary": colors.HexColor("#424242"),
        "accent": colors.HexColor("#2196F3"),
        "light_bg": colors.HexColor("#E3F2FD"),
        "table_header": colors.HexColor("#1976D2"),
        "table_alt": colors.HexColor("#F5F5F5"),
        "border": colors.HexColor("#BDBDBD"),
    }

    CHART_COLORS = ["#4E79A7", "#F28E2B", "#E15759", "#76B7B2", "#59A14F"]

    def __init__(
        self,
        project_info: Dict,
        report_info: Dict,
        lca_results: Dict,
        output_dir: str = "./reports",
    ):
        """Initialize the PDF report generator."""
        self.project_info = project_info
        self.report_info = report_info or {}
        self.lca_results = lca_results
        self.output_dir = output_dir

        os.makedirs(output_dir, exist_ok=True)

        self._configure_matplotlib_fonts()
        self.font_zh = self._register_chinese_font()
        self.font_en = "Helvetica"

        self._pie_chart_buffer = None
        self._histogram_buffer = None

    def _configure_matplotlib_fonts(self):
        """Configure matplotlib for Chinese font support (prefer Song/Serif fonts)."""

        chinese_fonts = [
            "SimSun",
            "STSong",
            "Songti SC",
            "STKaiti",
            "Kaiti SC",
            "SimHei",
            "Microsoft YaHei",
            "Noto Sans CJK SC",
            "Source Han Sans SC",
            "WenQuanYi Micro Hei",
            "Arial Unicode MS",
            "PingFang SC",
            "STHeiti",
        ]
        available_fonts = [f.name for f in fm.fontManager.ttflist]
        valid_fonts = [font for font in chinese_fonts if font in available_fonts]

        if valid_fonts:
            plt.rcParams["font.sans-serif"] = valid_fonts + ["Arial", "DejaVu Sans"]

            plt.rcParams["font.serif"] = valid_fonts + [
                "Times New Roman",
                "DejaVu Serif",
            ]
        else:
            plt.rcParams["font.sans-serif"] = ["Arial", "DejaVu Sans"]

        plt.rcParams["axes.unicode_minus"] = False
        plt.rcParams["font.size"] = 10

    def _register_chinese_font(self) -> str:

        font_paths = [
            "/System/Library/Fonts/Supplemental/Songti.ttc",
            "/System/Library/Fonts/STSong.ttf",
            "/Library/Fonts/Songti.ttc",
            "C:/Windows/Fonts/simsun.ttc",
            "C:/Windows/Fonts/SIMSUN.TTC",
            "/usr/share/fonts/truetype/arphic/uming.ttc",
            "/System/Library/Fonts/STKaiti.ttf",
            "/Library/Fonts/Kaiti.ttc",
            "C:/Windows/Fonts/simkai.ttf",
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Light.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
            "C:/Windows/Fonts/msyh.ttf",
            "C:/Windows/Fonts/simhei.ttf",
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        ]

        for font_path in font_paths:
            if os.path.exists(font_path):
                try:
                    font_name = os.path.splitext(os.path.basename(font_path))[0]
                    pdfmetrics.registerFont(TTFont(font_name, font_path))
                    print(f"✅ Registered PDF font: {font_name}")
                    return font_name
                except Exception as e:
                    print(f"⚠️ Failed to register font {font_path}: {e}")
                    continue

        print("⚠️ No Chinese font found, using Helvetica")
        return "Helvetica"

    def _t(self, key: str, lang: str) -> str:
        """Get translation for a key."""
        return REPORT_TRANSLATIONS.get(key, {}).get(lang, f"[{key}]")

    def _get_value(self, key: str, lang: str = "en") -> str:
        """Safely get a value from report_info with placeholder fallback."""
        value = self.report_info.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            return self._t("default_placeholder", lang)

        return self._translate_text(value, lang)

    def _detect_language(self, text: str) -> str:
        """Detect if text is primarily Chinese or English."""
        if not text or not isinstance(text, str):
            return "en"

        chinese_count = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
        total_chars = len(text.replace(" ", "").replace("\n", ""))

        if total_chars == 0:
            return "en"

        if chinese_count / total_chars > 0.2:
            return "zh"
        return "en"

    def _translate_text(self, text: str, target_lang: str) -> str:
        """Translate text to target language if needed."""
        if not text or not isinstance(text, str) or len(text.strip()) < 3:
            return text

        source_lang = self._detect_language(text)

        if source_lang == target_lang:
            return text

        if (
            len(text.strip()) < 5
            or text.strip().replace(".", "").replace("-", "").isdigit()
        ):
            return text

        try:

            if target_lang == "zh":
                prompt = f"Translate the following English text to Chinese. Only return the translation, nothing else:\n\n{text}"
            else:
                prompt = f"Translate the following Chinese text to English. Only return the translation, nothing else:\n\n{text}"

            api_key = os.environ.get("GROK_API_KEY", "")
            base_url = os.environ.get("GROK_BASE_URL", "https://openrouter.ai/api/v1")
            model_name = os.environ.get("GROK_MODEL", "x-ai/grok-3-mini")

            if not api_key:
                return text

            client = openai.OpenAI(api_key=api_key, base_url=base_url)

            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a professional translator. Translate accurately and naturally.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=1000,
            )

            translated = response.choices[0].message.content.strip()
            return translated if translated else text

        except Exception as e:
            print(f"⚠️ Translation failed: {e}")
            return text

    def _sanitize_unit(self, unit: str) -> str:
        """Sanitize unit string to remove problematic subscript characters."""
        if not unit:
            return "kg CO2-Eq"

        replacements = {
            "₂": "2",
            "₃": "3",
            "₄": "4",
            "CO₂": "CO2",
            "CO2e": "CO2-Eq",
            "CO2-e": "CO2-Eq",
            "CO₂e": "CO2-Eq",
            "CO₂-e": "CO2-Eq",
        }

        result = unit
        for old, new in replacements.items():
            result = result.replace(old, new)

        return result

    def _format_date(self, lang: str) -> str:
        """Format current date based on language."""
        now = datetime.now()
        if lang == "zh":
            return now.strftime("%Y年%m月%d日")
        return now.strftime("%B %d, %Y")

    def _get_styles(self, lang: str) -> Dict[str, ParagraphStyle]:
        """Create paragraph styles for the given language."""
        font = self.font_zh if lang == "zh" else self.font_en
        base_styles = getSampleStyleSheet()

        styles = {
            "title": ParagraphStyle(
                "CustomTitle",
                parent=base_styles["Heading1"],
                fontName=font,
                fontSize=24,
                textColor=self.COLORS["primary"],
                alignment=TA_CENTER,
                spaceAfter=30,
                spaceBefore=50,
                leading=30,
                wordWrap="CJK",
            ),
            "section_title": ParagraphStyle(
                "SectionTitle",
                parent=base_styles["Heading1"],
                fontName=font,
                fontSize=16,
                textColor=self.COLORS["primary"],
                spaceBefore=20,
                spaceAfter=12,
                leading=20,
                wordWrap="CJK",
            ),
            "subsection_title": ParagraphStyle(
                "SubsectionTitle",
                parent=base_styles["Heading2"],
                fontName=font,
                fontSize=13,
                textColor=self.COLORS["secondary"],
                spaceBefore=14,
                spaceAfter=8,
                leading=16,
                wordWrap="CJK",
            ),
            "normal": ParagraphStyle(
                "CustomNormal",
                parent=base_styles["Normal"],
                fontName=font,
                fontSize=10,
                textColor=colors.black,
                spaceAfter=8,
                leading=14,
                alignment=TA_JUSTIFY,
                wordWrap="CJK",
            ),
            "centered": ParagraphStyle(
                "Centered",
                parent=base_styles["Normal"],
                fontName=font,
                fontSize=10,
                alignment=TA_CENTER,
                spaceAfter=8,
                leading=14,
                wordWrap="CJK",
            ),
            "caption": ParagraphStyle(
                "Caption",
                parent=base_styles["Normal"],
                fontName=font,
                fontSize=9,
                alignment=TA_CENTER,
                textColor=self.COLORS["secondary"],
                spaceBefore=6,
                spaceAfter=12,
                leading=12,
                wordWrap="CJK",
            ),
            "footer": ParagraphStyle(
                "Footer",
                parent=base_styles["Normal"],
                fontName=font,
                fontSize=8,
                alignment=TA_CENTER,
                textColor=colors.grey,
                spaceBefore=20,
                wordWrap="CJK",
            ),
            "label": ParagraphStyle(
                "Label",
                parent=base_styles["Normal"],
                fontName=font,
                fontSize=10,
                textColor=self.COLORS["secondary"],
                wordWrap="CJK",
            ),
            "value": ParagraphStyle(
                "Value",
                parent=base_styles["Normal"],
                fontName=font,
                fontSize=10,
                textColor=colors.black,
                wordWrap="CJK",
            ),
        }

        return styles

    def _create_pie_chart(self, lang: str) -> Optional[io.BytesIO]:
        """Create pie chart for lifecycle stage emissions."""
        try:
            stages = self.lca_results.get("stages", {})

            stage_names = {
                "raw_material": self._t("stage_raw_material", lang),
                "production": self._t("stage_production", lang),
                "distribution": self._t("stage_distribution", lang),
                "use": self._t("stage_use", lang),
                "end_of_life": self._t("stage_end_of_life", lang),
            }

            labels = []
            sizes = []
            values = []

            for key in [
                "raw_material",
                "production",
                "distribution",
                "use",
                "end_of_life",
            ]:
                stage_data = stages.get(key, {})
                percentage = stage_data.get("percentage", 0)
                value = stage_data.get("value", 0)
                if percentage > 0:
                    labels.append(stage_names.get(key, key))
                    sizes.append(percentage)
                    values.append(value)

            if not sizes:
                return None

            fig, ax = plt.subplots(figsize=(10, 8))

            explode = [
                0.05 if i == sizes.index(max(sizes)) else 0 for i in range(len(sizes))
            ]

            def make_autopct(vals):
                idx_counter = {"count": 0}

                def autopct_func(pct):
                    idx = idx_counter["count"]
                    idx_counter["count"] += 1
                    if idx < len(vals):
                        return f"{vals[idx]:.3f}\nkg CO2-Eq\n({pct:.1f}%)"
                    return f"{pct:.1f}%"

                return autopct_func

            wedges, texts, autotexts = ax.pie(
                sizes,
                explode=explode,
                labels=labels,
                colors=self.CHART_COLORS[: len(sizes)],
                autopct=make_autopct(values),
                startangle=90,
                textprops={"fontsize": 10},
            )

            for autotext in autotexts:
                autotext.set_color("white")
                autotext.set_fontweight("bold")
                autotext.set_fontsize(9)

            ax.axis("equal")
            title = (
                self._t("figure_1_title", lang)
                .replace("Figure 1: ", "")
                .replace("图1：", "")
            )
            plt.title(title, fontsize=14, fontweight="bold", pad=20)

            buf = io.BytesIO()
            plt.savefig(
                buf, format="png", dpi=150, bbox_inches="tight", facecolor="white"
            )
            plt.close(fig)
            buf.seek(0)

            return buf

        except Exception as e:
            print(f"❌ Error creating pie chart: {e}")
            return None

    def _create_uncertainty_histogram(self, lang: str) -> Optional[io.BytesIO]:
        """Create histogram for uncertainty analysis."""
        try:
            uncertainty = self.lca_results.get("uncertainty_analysis", {})
            if not uncertainty or not uncertainty.get("statistics"):
                return None

            statistics = uncertainty.get("statistics", {})
            if not statistics:
                return None

            first_category = list(statistics.keys())[0]
            stats = statistics[first_category]

            mean = stats.get("mean", 0)
            std_dev = stats.get("std_dev", 0)
            p5 = stats.get("percentile_5", 0)
            p95 = stats.get("percentile_95", 0)
            median = stats.get("median", 0)

            if mean == 0 and std_dev == 0:
                return None

            np.random.seed(42)
            data = np.random.normal(mean, std_dev, 1000)

            fig, ax = plt.subplots(figsize=(10, 6))

            ax.hist(
                data,
                bins=30,
                color="#808080",
                alpha=0.7,
                edgecolor="black",
                linewidth=0.8,
            )

            ax.axvline(
                p5,
                color="red",
                linestyle="--",
                linewidth=2,
                label=f'{self._t("chart_percentile_5", lang)}: {p5:.3f}',
            )
            ax.axvline(
                median,
                color="blue",
                linestyle="--",
                linewidth=2,
                label=f'{self._t("chart_median", lang)}: {median:.3f}',
            )
            ax.axvline(
                p95,
                color="red",
                linestyle="--",
                linewidth=2,
                label=f'{self._t("chart_percentile_95", lang)}: {p95:.3f}',
            )

            unit = self._sanitize_unit(self.lca_results.get("unit", "kg CO2-Eq"))
            ax.set_xlabel(
                self._t("chart_cf_unit", lang), fontsize=12, fontweight="bold"
            )
            ax.set_ylabel(
                self._t("chart_frequency", lang), fontsize=12, fontweight="bold"
            )

            title = (
                self._t("figure_2_title", lang)
                .replace("Figure 2: ", "")
                .replace("图2：", "")
            )
            ax.set_title(
                f"{title}\n(Mean: {mean:.3f}, Std Dev: {std_dev:.3f} {unit})",
                fontsize=14,
                fontweight="bold",
                pad=20,
            )

            ax.grid(True, alpha=0.3, linestyle="--")
            ax.legend(fontsize=10, loc="upper right")

            plt.tight_layout()

            buf = io.BytesIO()
            fig.savefig(
                buf, format="png", dpi=150, bbox_inches="tight", facecolor="white"
            )
            plt.close(fig)
            buf.seek(0)

            return buf

        except Exception as e:
            print(f"❌ Error creating uncertainty histogram: {e}")
            return None

    def _create_stage_table(self, lang: str, styles: Dict) -> Table:
        """Create the lifecycle stage emission table."""
        stages = self.lca_results.get("stages", {})
        total = self.lca_results.get("total_carbon_footprint", 0)

        stage_keys = [
            "raw_material",
            "production",
            "distribution",
            "use",
            "end_of_life",
        ]

        data = [
            [
                Paragraph(self._t("table_header_stage", lang), styles["label"]),
                Paragraph(self._t("table_header_cf", lang), styles["label"]),
                Paragraph(self._t("table_header_percent", lang), styles["label"]),
            ]
        ]

        for key in stage_keys:
            stage_data = stages.get(key, {})
            value = stage_data.get("value", 0)
            percentage = stage_data.get("percentage", 0)

            data.append(
                [
                    Paragraph(self._t(f"stage_{key}", lang), styles["value"]),
                    Paragraph(f"{value:.3f}", styles["value"]),
                    Paragraph(f"{percentage:.2f}", styles["value"]),
                ]
            )

        data.append(
            [
                Paragraph(f"<b>{self._t('stage_total', lang)}</b>", styles["value"]),
                Paragraph(f"<b>{total:.3f}</b>", styles["value"]),
                Paragraph("<b>100.00</b>", styles["value"]),
            ]
        )

        table = Table(data, colWidths=[2.5 * inch, 2 * inch, 1.5 * inch])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), self.COLORS["table_header"]),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    (
                        "FONTNAME",
                        (0, 0),
                        (-1, 0),
                        self.font_zh if lang == "zh" else self.font_en,
                    ),
                    ("FONTSIZE", (0, 0), (-1, 0), 10),
                    (
                        "FONTNAME",
                        (0, 1),
                        (-1, -1),
                        self.font_zh if lang == "zh" else self.font_en,
                    ),
                    ("FONTSIZE", (0, 1), (-1, -1), 10),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("GRID", (0, 0), (-1, -1), 0.5, self.COLORS["border"]),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -2),
                        [colors.white, self.COLORS["table_alt"]],
                    ),
                    ("BACKGROUND", (0, -1), (-1, -1), self.COLORS["light_bg"]),
                    ("LINEABOVE", (0, -1), (-1, -1), 1, self.COLORS["primary"]),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )

        return table

    def _create_uncertainty_table(self, lang: str, styles: Dict) -> Optional[Table]:
        """Create the uncertainty analysis statistics table."""
        uncertainty = self.lca_results.get("uncertainty_analysis", {})
        if not uncertainty or not uncertainty.get("statistics"):
            return None

        statistics = uncertainty.get("statistics", {})
        if not statistics:
            return None

        first_category = list(statistics.keys())[0]
        stats = statistics[first_category]
        unit = self._sanitize_unit(self.lca_results.get("unit", "kg CO2-Eq"))

        data = [
            [
                Paragraph(self._t("stat_metric", lang), styles["label"]),
                Paragraph(f"{self._t('stat_value', lang)} ({unit})", styles["label"]),
            ],
            [
                Paragraph(self._t("stat_mean", lang), styles["value"]),
                Paragraph(f"{stats.get('mean', 0):.3f}", styles["value"]),
            ],
            [
                Paragraph(self._t("stat_std", lang), styles["value"]),
                Paragraph(f"{stats.get('std_dev', 0):.3f}", styles["value"]),
            ],
            [
                Paragraph(self._t("stat_cv", lang), styles["value"]),
                Paragraph(f"{stats.get('cv', 0):.2%}", styles["value"]),
            ],
            [
                Paragraph(self._t("stat_median", lang), styles["value"]),
                Paragraph(f"{stats.get('median', 0):.3f}", styles["value"]),
            ],
            [
                Paragraph(self._t("stat_p5", lang), styles["value"]),
                Paragraph(f"{stats.get('percentile_5', 0):.3f}", styles["value"]),
            ],
            [
                Paragraph(self._t("stat_p95", lang), styles["value"]),
                Paragraph(f"{stats.get('percentile_95', 0):.3f}", styles["value"]),
            ],
        ]

        table = Table(data, colWidths=[3 * inch, 2.5 * inch])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), self.COLORS["table_header"]),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    (
                        "FONTNAME",
                        (0, 0),
                        (-1, -1),
                        self.font_zh if lang == "zh" else self.font_en,
                    ),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("GRID", (0, 0), (-1, -1), 0.5, self.COLORS["border"]),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, self.COLORS["table_alt"]],
                    ),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )

        return table

    def _generate_ai_interpretation(self, lang: str) -> Dict[str, str]:
        """Generate AI-powered interpretation of results."""
        product_name = self._get_value("product_name", lang)
        if product_name == self._t("default_placeholder", lang):

            fallback_name = self.project_info.get("name", "Product")
            product_name = self._translate_text(fallback_name, lang)

        producer_name = self._get_value("producer_name", lang)
        total_cf = self.lca_results.get("total_carbon_footprint", 0)
        unit = self._sanitize_unit(self.lca_results.get("unit", "kg CO2-Eq"))

        try:
            stages = self.lca_results.get("stages", {})
            stage_info = ""
            for stage_name, stage_data in stages.items():
                if isinstance(stage_data, dict):
                    value = stage_data.get("value", 0)
                    percentage = stage_data.get("percentage", 0)
                else:
                    value = stage_data
                    percentage = (value / total_cf * 100) if total_cf > 0 else 0
                stage_info += (
                    f"- {stage_name}: {value:.3f} {unit} ({percentage:.1f}%)\n"
                )

            output_lang = "Chinese" if lang == "zh" else "English"

            prompt = f"""
You are a professional Life Cycle Assessment (LCA) expert. Based on the following LCA calculation results, generate professional report interpretation content in {output_lang}.

**Product Information:**
- Product Name: {product_name}
- Producer: {producer_name}
- Total Carbon Footprint: {total_cf:.3f} {unit}

**Lifecycle Stage Contributions:**
{stage_info}

Please generate the following three sections in {output_lang} with professional and accurate content:

Format your response EXACTLY as follows with clear markers:

[SECTION1]
Write 2-3 paragraphs (150-200 words) describing:
- Overview of the total carbon footprint level
- Analysis of lifecycle stage contribution characteristics
- Identification of major emission sources

[SECTION2]
Write 2-3 paragraphs (150-200 words) stating:
- Key assumptions made in this study
- Limitations of data sources and quality
- System boundary restrictions

[SECTION3]
Provide 3-5 specific, actionable suggestions (bullet points) for:
- Concrete improvement measures targeting major emission stages
- Feasible emission reduction pathways
- Data quality improvement recommendations

Use the markers [SECTION1], [SECTION2], [SECTION3] to clearly separate each section.
"""

            api_key = os.environ.get("GROK_API_KEY", "")
            base_url = os.environ.get("GROK_BASE_URL", "https://openrouter.ai/api/v1")
            model_name = os.environ.get("GROK_MODEL", "x-ai/grok-3-mini")

            if not api_key:
                raise ValueError(
                    "GROK_API_KEY environment variable not set, cannot call LLM for report interpretation"
                )

            print(f"🤖 AI解读: 使用模型 {model_name}, base_url={base_url}")

            client = openai.OpenAI(api_key=api_key, base_url=base_url)

            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "system",
                        "content": f"You are a professional LCA expert. Respond in {output_lang}.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=2000,
            )

            ai_content = response.choices[0].message.content

            description = ""
            assumptions = ""
            improvements = ""

            if (
                "[SECTION1]" in ai_content
                and "[SECTION2]" in ai_content
                and "[SECTION3]" in ai_content
            ):
                section1_start = ai_content.find("[SECTION1]") + len("[SECTION1]")
                section1_end = ai_content.find("[SECTION2]")
                description = self._clean_ai_text(
                    ai_content[section1_start:section1_end].strip()
                )

                section2_start = ai_content.find("[SECTION2]") + len("[SECTION2]")
                section2_end = ai_content.find("[SECTION3]")
                assumptions = self._clean_ai_text(
                    ai_content[section2_start:section2_end].strip()
                )

                section3_start = ai_content.find("[SECTION3]") + len("[SECTION3]")
                raw_improvements = ai_content[section3_start:].strip()
                improvements = self._clean_ai_text(raw_improvements, is_list=True)
            else:

                print(f"⚠️ AI返回格式不符合预期，使用默认内容")
                print(f"   AI返回内容预览: {ai_content[:300]}...")
                largest_stage = self._get_largest_stage(lang)
                if lang == "zh":
                    description = f"{product_name}的生命周期碳足迹为{total_cf:.3f} {unit}。{largest_stage}贡献了最大的碳排放份额。"
                else:
                    description = f"The life cycle carbon footprint of {product_name} is {total_cf:.3f} {unit}. The {largest_stage} stage contributes the largest share of carbon emissions."
                assumptions = self._t("default_placeholder", lang)
                improvements = self._t("default_placeholder", lang)

            return {
                "description": description,
                "assumptions": assumptions,
                "improvements": improvements,
            }

        except Exception as e:
            print(f"⚠️ AI interpretation failed: {e}")
            import traceback

            traceback.print_exc()
            largest_stage = self._get_largest_stage(lang)

            if lang == "zh":
                return {
                    "description": f"{product_name}的生命周期碳足迹为{total_cf:.3f} {unit}。{largest_stage}贡献了最大的碳排放份额。",
                    "assumptions": self._t("default_placeholder", lang),
                    "improvements": self._t("default_placeholder", lang),
                }
            else:
                return {
                    "description": f"The life cycle carbon footprint of {product_name} is {total_cf:.3f} {unit}. The {largest_stage} stage contributes the largest share of carbon emissions.",
                    "assumptions": self._t("default_placeholder", lang),
                    "improvements": self._t("default_placeholder", lang),
                }

    def _clean_ai_text(self, text: str, is_list: bool = False) -> str:
        """Clean AI-generated text by removing extra spaces and formatting properly."""
        if not text:
            return text

        import re

        cleaned = text.replace("\t", " ")

        cleaned = cleaned.replace("\r", "")

        cleaned = re.sub(r" +", " ", cleaned)

        lines = cleaned.split("\n")
        cleaned_lines = [line.strip() for line in lines]
        cleaned = "\n".join(cleaned_lines)

        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

        if is_list:

            lines = cleaned.split("\n")
            non_empty_lines = [line.strip() for line in lines if line.strip()]

            has_list_markers = any(
                line.startswith(("-", "•", "*"))
                or re.match(r"^\d+\.\s+", line)
                or re.match(r"^[一二三四五六七八九十]+[、.]\s+", line)
                for line in non_empty_lines
            )

            list_items = []

            if has_list_markers:

                for line in non_empty_lines:

                    if (
                        line.startswith("-")
                        or line.startswith("•")
                        or line.startswith("*")
                    ):
                        line = line[1:].strip()

                    line = re.sub(r"^\d+\.\s*", "", line)

                    line = re.sub(r"^[一二三四五六七八九十]+[、.]\s*", "", line)

                    if line:
                        list_items.append(line)
            else:

                if len(non_empty_lines) > 1:

                    list_items = non_empty_lines
                else:

                    paragraphs = re.split(r"\n\n+", cleaned)
                    for para in paragraphs:
                        para = para.strip()

                        para = re.sub(r"\n+", " ", para)
                        if para:
                            list_items.append(para)

            if list_items:
                return "||LIST||" + "||ITEM||".join(list_items)
            else:

                return cleaned
        else:

            paragraphs = re.split(r"\n\n+", cleaned)

            processed_paragraphs = []
            for para in paragraphs:
                para = para.strip()
                if para:

                    para = re.sub(r"\n", " ", para)

                    para = re.sub(r" +", " ", para)
                    processed_paragraphs.append(para)

            cleaned = "\n\n".join(processed_paragraphs)

        return cleaned.strip()

    def _add_text_content(self, story: List, content: str, styles: Dict, lang: str):
        """Add text content to story, handling both paragraphs and lists."""
        if not content:
            return

        if content.startswith("||LIST||"):

            items_str = content.replace("||LIST||", "")
            items = items_str.split("||ITEM||")

            font = self.font_zh if lang == "zh" else self.font_en

            bullet_style = ParagraphStyle(
                "BulletStyle",
                parent=styles["normal"],
                fontName=font,
                fontSize=10,
                leftIndent=0,
                spaceAfter=6,
                leading=14,
                alignment=TA_JUSTIFY,
            )

            list_items = []
            for item in items:
                item = item.strip()
                if item:
                    list_items.append(Paragraph(item, bullet_style))

            if list_items:

                bullet_list = ListFlowable(
                    list_items,
                    bulletType="bullet",
                    leftIndent=20,
                    bulletFontName=font,
                    bulletFontSize=10,
                    bulletDedent=10,
                )
                story.append(bullet_list)
        else:

            paragraphs = content.split("\n\n")

            for i, para in enumerate(paragraphs):
                para = para.strip()
                if para:
                    story.append(Paragraph(para, styles["normal"]))

                    if i < len(paragraphs) - 1:
                        story.append(Spacer(1, 0.1 * inch))

    def _get_largest_stage(self, lang: str) -> str:
        """Get the name of the stage with highest emissions."""
        stages = self.lca_results.get("stages", {})
        stage_translations = {
            "raw_material": self._t("stage_raw_material", lang),
            "production": self._t("stage_production", lang),
            "distribution": self._t("stage_distribution", lang),
            "use": self._t("stage_use", lang),
            "end_of_life": self._t("stage_end_of_life", lang),
        }

        max_stage = "production"
        max_value = 0

        for key, data in stages.items():
            value = data.get("value", 0) if isinstance(data, dict) else data
            if value > max_value:
                max_value = value
                max_stage = key

        return stage_translations.get(max_stage, max_stage)

    def _build_pdf_content(self, lang: str) -> List:
        """Build the complete PDF content for a given language."""
        styles = self._get_styles(lang)
        story = []

        story.append(Spacer(1, 2 * inch))
        story.append(Paragraph(self._t("title", lang), styles["title"]))
        story.append(Spacer(1, 0.5 * inch))

        story.append(
            HRFlowable(
                width="60%",
                thickness=2,
                color=self.COLORS["primary"],
                spaceBefore=10,
                spaceAfter=30,
                hAlign="CENTER",
            )
        )

        product_name = self._get_value("product_name", lang)
        if product_name == self._t("default_placeholder", lang):

            fallback_name = self.project_info.get("name", "Product")
            product_name = self._translate_text(fallback_name, lang)

        title_info = [
            [self._t("product_name", lang) + ":", product_name],
            [
                self._t("producer_name", lang) + ":",
                self._get_value("producer_name", lang),
            ],
            [self._t("report_no", lang) + ":", self._get_value("report_no", lang)],
            [self._t("date", lang) + ":", self._format_date(lang)],
        ]

        title_table = Table(title_info, colWidths=[2 * inch, 4 * inch])
        title_table.setStyle(
            TableStyle(
                [
                    (
                        "FONTNAME",
                        (0, 0),
                        (-1, -1),
                        self.font_zh if lang == "zh" else self.font_en,
                    ),
                    ("FONTSIZE", (0, 0), (-1, -1), 12),
                    ("ALIGN", (0, 0), (0, -1), "RIGHT"),
                    ("ALIGN", (1, 0), (1, -1), "LEFT"),
                    ("TEXTCOLOR", (0, 0), (0, -1), self.COLORS["secondary"]),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
                ]
            )
        )
        story.append(title_table)

        story.append(PageBreak())

        story.append(
            Paragraph(self._t("section_1_title", lang), styles["section_title"])
        )

        info_items = [
            (self._t("producer_name", lang), self._get_value("producer_name", lang)),
            (self._t("address", lang), self._get_value("address", lang)),
            (self._t("legal_rep", lang), self._get_value("legal_representative", lang)),
            (self._t("product_name", lang), product_name),
            (
                self._t("product_function", lang),
                self._get_value("product_function", lang),
            ),
            (self._t("standard_used", lang), self._get_value("standard_used", lang)),
        ]

        for label, value in info_items:
            story.append(Paragraph(f"<b>{label}:</b> {value}", styles["normal"]))

        story.append(
            Paragraph(self._t("section_2_title", lang), styles["section_title"])
        )
        story.append(
            Paragraph(self._get_value("quantitative_purpose", lang), styles["normal"])
        )

        story.append(
            Paragraph(self._t("section_3_title", lang), styles["section_title"])
        )

        story.append(
            Paragraph(
                self._t("functional_unit_title", lang), styles["subsection_title"]
            )
        )
        fu = self._get_value("functional_unit", lang)
        story.append(
            Paragraph(
                f"{self._t('functional_unit_desc', lang)} {fu}.", styles["normal"]
            )
        )

        story.append(
            Paragraph(
                self._t("system_boundary_title", lang), styles["subsection_title"]
            )
        )
        story.append(
            Paragraph(
                self._get_value("system_boundary_description", lang), styles["normal"]
            )
        )

        story.append(
            Paragraph(self._t("cutoff_title", lang), styles["subsection_title"])
        )
        cutoff = self._get_value("cutoff_criteria", lang)
        if cutoff != self._t("default_placeholder", lang):
            story.append(
                Paragraph(f"{self._t('cutoff_desc', lang)} {cutoff}.", styles["normal"])
            )
        else:
            story.append(Paragraph(cutoff, styles["normal"]))

        story.append(
            Paragraph(self._t("time_scale_title", lang), styles["subsection_title"])
        )
        story.append(Paragraph(self._get_value("time_scale", lang), styles["normal"]))

        story.append(
            Paragraph(self._t("section_4_title", lang), styles["section_title"])
        )

        story.append(
            Paragraph(self._t("data_source_title", lang), styles["subsection_title"])
        )
        story.append(
            Paragraph(
                f"<b>{self._t('primary_data', lang)}:</b> {self._get_value('primary_data_source', lang)}",
                styles["normal"],
            )
        )
        story.append(
            Paragraph(
                f"<b>{self._t('secondary_data', lang)}:</b> {self._get_value('secondary_data_source', lang)}",
                styles["normal"],
            )
        )

        story.append(
            Paragraph(self._t("allocation_title", lang), styles["subsection_title"])
        )
        story.append(
            Paragraph(
                f"<b>{self._t('allocation_basis', lang)}:</b> {self._get_value('allocation_basis', lang)}",
                styles["normal"],
            )
        )
        story.append(
            Paragraph(
                f"<b>{self._t('allocation_procedure', lang)}:</b> {self._get_value('allocation_procedure', lang)}",
                styles["normal"],
            )
        )
        story.append(
            Paragraph(
                f"<b>{self._t('specific_allocation', lang)}:</b> {self._get_value('specific_allocations', lang)}",
                styles["normal"],
            )
        )

        story.append(
            Paragraph(self._t("data_quality_title", lang), styles["subsection_title"])
        )
        story.append(
            Paragraph(self._get_value("data_quality_notes", lang), styles["normal"])
        )

        story.append(PageBreak())
        story.append(
            Paragraph(self._t("section_5_title", lang), styles["section_title"])
        )

        story.append(
            Paragraph(self._t("impact_type_title", lang), styles["subsection_title"])
        )
        impact_desc = self._get_value("impact_type_description", lang)
        if impact_desc == self._t("default_placeholder", lang):
            if lang == "zh":
                impact_desc = (
                    "政府间气候变化专门委员会(IPCC)给出的100年全球变暖潜能值(GWP)"
                )
            else:
                impact_desc = "100-year global warming potential (GWP) given by the Intergovernmental Panel on Climate Change (IPCC)"
        story.append(Paragraph(impact_desc, styles["normal"]))

        story.append(
            Paragraph(self._t("results_title", lang), styles["subsection_title"])
        )

        total_cf = self.lca_results.get("total_carbon_footprint", 0)
        producer = self._get_value("producer_name", lang)

        results_text = self._t("results_desc", lang).format(
            producer=producer, product=product_name
        )
        story.append(
            Paragraph(
                f"{results_text} <b>{total_cf:.3f} kg CO2-Eq</b>.", styles["normal"]
            )
        )

        story.append(Spacer(1, 0.3 * inch))
        story.append(Paragraph(self._t("figure_1_title", lang), styles["caption"]))

        pie_chart = self._create_pie_chart(lang)
        if pie_chart:
            img = Image(pie_chart, width=5 * inch, height=4 * inch)
            img.hAlign = "CENTER"
            story.append(img)

        story.append(Spacer(1, 0.3 * inch))

        story.append(Paragraph(self._t("table_1_title", lang), styles["caption"]))
        stage_table = self._create_stage_table(lang, styles)
        stage_table.hAlign = "CENTER"
        story.append(stage_table)

        story.append(Spacer(1, 0.3 * inch))
        story.append(
            Paragraph(self._t("uncertainty_title", lang), styles["subsection_title"])
        )

        uncertainty = self.lca_results.get("uncertainty_analysis", {})
        if uncertainty and uncertainty.get("statistics"):
            unit = self._sanitize_unit(self.lca_results.get("unit", "kg CO2-Eq"))
            iterations = uncertainty.get("iterations", 0)

            story.append(
                Paragraph(
                    f"<b>{self._t('uncertainty_iterations', lang)}:</b> {iterations}",
                    styles["normal"],
                )
            )

            histogram = self._create_uncertainty_histogram(lang)
            if histogram:
                story.append(Spacer(1, 0.2 * inch))
                story.append(
                    Paragraph(self._t("figure_2_title", lang), styles["caption"])
                )
                hist_img = Image(histogram, width=5 * inch, height=3.5 * inch)
                hist_img.hAlign = "CENTER"
                story.append(hist_img)

            story.append(Spacer(1, 0.2 * inch))
            uncertainty_table = self._create_uncertainty_table(lang, styles)
            if uncertainty_table:
                uncertainty_table.hAlign = "CENTER"
                story.append(uncertainty_table)
        else:
            story.append(
                Paragraph(
                    f"<i>{self._t('uncertainty_none', lang)}</i>", styles["normal"]
                )
            )

        story.append(PageBreak())
        story.append(
            Paragraph(self._t("section_6_title", lang), styles["section_title"])
        )

        interpretation = self._generate_ai_interpretation(lang)

        story.append(
            Paragraph(self._t("description_title", lang), styles["subsection_title"])
        )
        self._add_text_content(story, interpretation["description"], styles, lang)

        story.append(
            Paragraph(self._t("assumptions_title", lang), styles["subsection_title"])
        )
        self._add_text_content(story, interpretation["assumptions"], styles, lang)

        story.append(
            Paragraph(self._t("improvements_title", lang), styles["subsection_title"])
        )
        self._add_text_content(story, interpretation["improvements"], styles, lang)

        story.append(Spacer(1, 0.5 * inch))
        story.append(
            HRFlowable(
                width="100%",
                thickness=1,
                color=colors.grey,
                spaceBefore=20,
                spaceAfter=10,
            )
        )

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        story.append(
            Paragraph(
                f"<i>{self._t('report_generated', lang)}: {timestamp}</i><br/>"
                f"<i>{self._t('generator', lang)}: {self._t('generator_name', lang)}</i>",
                styles["footer"],
            )
        )

        return story

    def generate_pdf_report(self, lang: str = "en") -> Tuple[Optional[str], bool]:
        """Generate a single PDF report in the specified language."""
        try:
            product_name = self._get_value("product_name", lang)
            if product_name == self._t("default_placeholder", lang):
                product_name = self.project_info.get("name", "Product")

            safe_name = product_name.replace(" ", "_").replace("/", "_")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            lang_suffix = "CN" if lang == "zh" else "EN"

            filename = f"LCA_Report_{safe_name}_{lang_suffix}_{timestamp}.pdf"
            filepath = os.path.join(self.output_dir, filename)

            doc = SimpleDocTemplate(
                filepath,
                pagesize=A4,
                rightMargin=72,
                leftMargin=72,
                topMargin=72,
                bottomMargin=72,
            )

            story = self._build_pdf_content(lang)

            doc.build(story)

            print(f"✅ PDF report generated: {filepath}")
            return filepath, True

        except Exception as e:
            print(f"❌ PDF generation failed: {e}")
            import traceback

            traceback.print_exc()
            return None, False

    def generate_bilingual_reports(self) -> Dict[str, Any]:
        """Generate both Chinese and English PDF reports."""
        results = {"success": True, "files": {}, "errors": []}

        print("\n📝 Generating Chinese PDF report...")
        zh_path, zh_success = self.generate_pdf_report("zh")
        if zh_success and zh_path:
            results["files"]["zh"] = {
                "path": zh_path,
                "filename": os.path.basename(zh_path),
            }
        else:
            results["errors"].append("Chinese PDF generation failed")

        print("\n📝 Generating English PDF report...")
        en_path, en_success = self.generate_pdf_report("en")
        if en_success and en_path:
            results["files"]["en"] = {
                "path": en_path,
                "filename": os.path.basename(en_path),
            }
        else:
            results["errors"].append("English PDF generation failed")

        results["success"] = len(results["errors"]) == 0

        return results


def demo_usage():
    """Demo usage of the PDF report generator."""
    project_info = {
        "name": "Lithium Sulfur Battery",
        "description": "High energy density battery project",
    }

    report_info = {
        "product_name": "Lithium Sulfur Battery",
        "product_model": "LSB-2024-V1",
        "producer_name": "GreenTech Battery Co.",
        "report_no": "RPT-2024-001",
        "address": "123 Innovation Drive, Tech City",
        "legal_representative": "Dr. Zhang Wei",
        "product_function": "High energy density energy storage device",
        "standard_used": "IPCC 2013 GWP 100a",
        "quantitative_purpose": "To assess the carbon footprint and identify reduction opportunities",
        "functional_unit": "1 kWh of energy storage capacity",
        "time_scale": "Year 2024",
    }

    lca_results = {
        "total_carbon_footprint": 30.2238,
        "unit": "kg CO2-Eq",
        "stages": {
            "raw_material": {"value": 13.3285, "percentage": 44.1},
            "production": {"value": 10.4617, "percentage": 34.6},
            "distribution": {"value": 3.6589, "percentage": 12.1},
            "use": {"value": 1.2483, "percentage": 4.1},
            "end_of_life": {"value": 1.5264, "percentage": 5.1},
        },
    }

    generator = ProfessionalPDFReportGenerator(
        project_info, report_info, lca_results, output_dir="./test_reports"
    )

    results = generator.generate_bilingual_reports()

    print("\n" + "=" * 50)
    print("Demo completed!")
    print(f"Success: {results['success']}")
    for lang, file_info in results["files"].items():
        print(f"  {lang.upper()}: {file_info['filename']}")
    if results["errors"]:
        print(f"Errors: {results['errors']}")


if __name__ == "__main__":
    demo_usage()
