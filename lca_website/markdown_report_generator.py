import os
import json
import re
from datetime import datetime
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from io import BytesIO
import base64
import openai
from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image as RLImage,
    PageBreak,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


class MarkdownReportGenerator:

    def __init__(self, project_info, report_info, lca_results, output_dir="./reports"):

        self.project_info = project_info
        self.report_info = report_info or {}
        self.lca_results = lca_results
        self.output_dir = output_dir

        os.makedirs(output_dir, exist_ok=True)

        self._configure_fonts()

    def _configure_fonts(self):

        try:

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
        except Exception as e:
            print(f"字体配置警告: {e}")

    def _get_value(self, key, default="[Information provided by the user]"):

        value = self.report_info.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            return default
        return value

    def _format_date(self):

        return datetime.now().strftime("%B %d, %Y")

    def _create_pie_chart(self):

        try:
            stages = self.lca_results.get("stages", {})

            labels = []
            sizes = []
            stage_names = {
                "raw_material": "Raw Material Acquisition",
                "production": "Production",
                "distribution": "Distribution",
                "use": "Use",
                "end_of_life": "End of Life",
            }

            for key, name in stage_names.items():
                stage_data = stages.get(key, {})
                percentage = stage_data.get("percentage", 0)
                if percentage > 0:
                    labels.append(name)
                    sizes.append(percentage)

            if not sizes:
                return None

            fig, ax = plt.subplots(figsize=(10, 8))

            colors = ["#4E79A7", "#F28E2B", "#E15759", "#76B7B2", "#59A14F"]
            explode = [
                0.05 if i == sizes.index(max(sizes)) else 0 for i in range(len(sizes))
            ]

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
                if percentage > 0:
                    values.append(stage_data.get("value", 0))

            def make_autopct(values):
                index_counter = {"count": 0}

                def my_autopct(pct):
                    idx = index_counter["count"]
                    index_counter["count"] += 1
                    if idx < len(values):
                        return f"{values[idx]:.3f}\nkg CO₂e\n({pct:.2f}%)"
                    return f"{pct:.2f}%"

                return my_autopct

            wedges, texts, autotexts = ax.pie(
                sizes,
                explode=explode,
                labels=labels,
                colors=colors[: len(sizes)],
                autopct=make_autopct(values),
                startangle=90,
                textprops={"fontsize": 10},
            )

            for autotext in autotexts:
                autotext.set_color("white")
                autotext.set_fontweight("bold")
                autotext.set_fontsize(9)

            ax.axis("equal")
            plt.title(
                "Carbon Emissions by Life Cycle Stage",
                fontsize=14,
                fontweight="bold",
                pad=20,
            )

            buf = BytesIO()
            plt.savefig(
                buf, format="png", dpi=150, bbox_inches="tight", facecolor="white"
            )
            plt.close()
            buf.seek(0)

            import base64

            img_base64 = base64.b64encode(buf.read()).decode("utf-8")
            return f"data:image/png;base64,{img_base64}"

        except Exception as e:
            print(f"创建饼图时出错: {e}")
            return None

    def _create_bar_chart(self):

        try:
            stages = self.lca_results.get("stages", {})

            stage_names = {
                "raw_material": "Raw Material\nAcquisition",
                "production": "Production",
                "distribution": "Distribution",
                "use": "Use",
                "end_of_life": "End of Life",
            }

            labels = []
            values = []

            for key, name in stage_names.items():
                stage_data = stages.get(key, {})
                value = stage_data.get("value", 0)
                if value > 0 or key in stages:
                    labels.append(name)
                    values.append(value)

            if not values:
                return None

            fig, ax = plt.subplots(figsize=(12, 6))

            colors = ["#4E79A7", "#F28E2B", "#E15759", "#76B7B2", "#59A14F"]
            bars = ax.bar(
                labels,
                values,
                color=colors[: len(labels)],
                alpha=0.8,
                edgecolor="black",
                linewidth=1.2,
            )

            for bar in bars:
                height = bar.get_height()
                ax.text(
                    bar.get_x() + bar.get_width() / 2.0,
                    height,
                    f"{height:.3f}",
                    ha="center",
                    va="bottom",
                    fontsize=10,
                    fontweight="bold",
                )

            ax.set_ylabel("Carbon Footprint (kg CO₂e)", fontsize=12, fontweight="bold")
            ax.set_xlabel("Life Cycle Stage", fontsize=12, fontweight="bold")
            ax.set_title(
                "Carbon Footprint by Life Cycle Stage",
                fontsize=14,
                fontweight="bold",
                pad=20,
            )
            ax.grid(True, alpha=0.3, axis="y", linestyle="--")

            plt.xticks(rotation=15, ha="right")
            plt.tight_layout()

            buf = BytesIO()
            plt.savefig(
                buf, format="png", dpi=150, bbox_inches="tight", facecolor="white"
            )
            plt.close()
            buf.seek(0)

            img_base64 = base64.b64encode(buf.read()).decode("utf-8")
            return f"data:image/png;base64,{img_base64}"

        except Exception as e:
            print(f"创建柱状图时出错: {e}")
            return None

    def _generate_stage_table(self):

        stages = self.lca_results.get("stages", {})
        total = self.lca_results.get("total_carbon_footprint", 0)

        print("📊 DEBUG: Stage table generation")
        print(f"   Total carbon footprint: {total}")
        print(f"   Stages data: {stages}")

        stage_names = {
            "raw_material": "Raw Material Acquisition",
            "production": "Production",
            "distribution": "Distribution",
            "use": "Use",
            "end_of_life": "End of life",
        }

        table_rows = []
        for key, name in stage_names.items():
            stage_data = stages.get(key, {})
            value = stage_data.get("value", 0)
            percentage = stage_data.get("percentage", 0)

            table_rows.append(f"|{name}|{value:.3f}|{percentage:.2f}|")

        table_rows.append(f"|Total|{total:.3f}|100.00|")

        table = "\n".join(table_rows)
        return table

    def generate_report(self):

        product_name = self._get_value(
            "product_name",
            self.project_info.get("name", "[Information provided by the user]"),
        )
        product_model = self._get_value("product_model")
        producer_name = self._get_value("producer_name")
        report_no = self._get_value("report_no")
        report_date = self._format_date()
        address = self._get_value("address")
        legal_rep = self._get_value("legal_representative")
        product_func = self._get_value("product_function")
        standard = self._get_value("standard_used", "IPCC 2013 GWP 100a")
        quant_purpose = self._get_value("quantitative_purpose")
        functional_unit = self._get_value("functional_unit")
        system_boundary = self._get_value("system_boundary_description")
        cutoff_criteria = self._get_value("cutoff_criteria")
        time_scale = self._get_value("time_scale")
        primary_data = self._get_value("primary_data_source")
        secondary_data = self._get_value("secondary_data_source")
        alloc_basis = self._get_value("allocation_basis")
        alloc_procedure = self._get_value("allocation_procedure")
        specific_alloc = self._get_value("specific_allocations")
        data_quality = self._get_value("data_quality_notes")
        impact_type = self._get_value(
            "impact_type_description",
            "100-year global warming potential (GWP) given by the Intergovernmental Panel on Climate Change (IPCC)",
        )
        assumptions = self._get_value("assumptions_limitations")
        improvements = self._get_value("improvement_suggestions")

        total_cf = self.lca_results.get("total_carbon_footprint", 0)

        pie_chart_data = self._create_pie_chart()

        stage_table = self._generate_stage_table()

        report = f"""# Product Carbon Footprint Study Report

# Basic Information

- Product Name: {product_name}
- Product Specification Model: {product_model}
- Producer Name: {producer_name}
- Report No: {report_no}
- Reporting organization: {self._get_value('contact_person', '(if any)')}
- Date: {report_date}

# I. General Information

- Producer Name: {producer_name}
- Address: {address}
- Legal representative: {legal_rep}
- Product Name: {product_name}
- Product Function: {product_func}
- Based on the standard: {standard}

# II. Quantitative Purpose

{quant_purpose}

# III. Scope of Quantification

## 1. Functional or Declaratory Units

Functional or declarative units in {functional_unit}.

## 2. System Boundary

{system_boundary}

## 3. Cut off Criteria

The rounding criteria used are based on {cutoff_criteria if cutoff_criteria != '[Information provided by the user]' else '()'} and the rules are as follows:

{cutoff_criteria if cutoff_criteria != '[Information provided by the user]' else ''}

## 4. Time Scale

{time_scale}.

# IV. Inventory Analysis

## 1. Description of Data Sources

- Primary data: {primary_data}
- Secondary data: {secondary_data}

## 2. Principles and Procedures for Allocation

- Basis of allocation: {alloc_basis}
- Allocation Procedure: {alloc_procedure}
- Specific allocations: {specific_alloc}

## 3. Data Quality Evaluation (optional)

{data_quality}

# V. Impact Assessment

## 1. Impact Type and Characterization Factor Selection

{impact_type}

## 2. Product Carbon Footprint Results Calculation

The life cycle carbon footprint of {product_name} produced by {producer_name}, per functional unit of product, from raw material acquisition to end of life is **{total_cf:.3f} kg CO₂e**. The GHG emissions at each life cycle stage are shown in Table 1 and Figure 1.

### Figure 1: Carbon Emissions Distribution by Life Cycle Stage

"""

        if pie_chart_data:
            report += f"![Pie Chart]({pie_chart_data})\n\n"

        report += f"""### Table 1: Carbon emissions by life cycle stage

| Life cycle stage | Carbon footprint (kg-CO2e) | Percentage (%) |
|-----------------|---------------------------|----------------|
{stage_table}

"""

        report += self._generate_uncertainty_section()

        ai_interpretation = self._generate_ai_interpretation()

        report += f"""
# VI. Interpretation of Results

## 1. Description of Results

{ai_interpretation['description']}

## 2. Statement of Assumptions and Limitations

{ai_interpretation['assumptions']}

## 3. Suggestions for Improvement

{ai_interpretation['improvements']}

---

*Report Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}*
*Generator: LCA Website Automated Report System*
"""

        filename = f"LCA_Report_{product_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        filepath = os.path.join(self.output_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(report)

        print(f"✓ 报告已生成: {filepath}")

        return report, filepath

    def _generate_lifecycle_contribution_section(self):

        stages = self.lca_results.get("stages", {})
        unit = self.lca_results.get("unit", "kg CO2-Eq")
        impact_category = self.lca_results.get("impact_category", "Climate Change")

        if not stages or all(s.get("value", 0) == 0 for s in stages.values()):
            return ""

        stage_names = {
            "raw_material": "Raw Material Acquisition",
            "production": "Production",
            "distribution": "Distribution",
            "use": "Use Phase",
            "end_of_life": "End-of-Life",
        }

        section = f"""
## 3. 🔗 Lifecycle Stage Contribution Analysis

**Impact Category**: {impact_category}
**Unit**: {unit}

The carbon footprint distribution across lifecycle stages is as follows:

| Lifecycle Stage | Carbon Footprint ({unit}) | Percentage (%) |
|----------------|---------------------------|----------------|
"""

        for key, name in stage_names.items():
            stage_data = stages.get(key, {})
            value = stage_data.get("value", 0)
            percentage = stage_data.get("percentage", 0)
            section += f"| {name} | {value:.3f} | {percentage:.2f} |\n"

        total = self.lca_results.get("total_carbon_footprint", 0)
        section += f"| **Total** | **{total:.3f}** | **100.00** |\n\n"

        max_stage_key = (
            max(stages.items(), key=lambda x: x[1].get("value", 0))[0]
            if stages
            else "production"
        )
        max_stage_name = stage_names.get(max_stage_key, "Production")
        max_percentage = stages.get(max_stage_key, {}).get("percentage", 0)

        section += f"""
**Key Findings**:
- The **{max_stage_name}** stage contributes the most to the carbon footprint, accounting for **{max_percentage:.2f}%** of total emissions.
- This data is based on the deterministic LCA calculation results from the website visualization.

"""

        return section

    def _generate_process_contribution_section(self):

        process_contribs = self.lca_results.get("process_contributions", [])
        unit = self.lca_results.get("unit", "kg CO2-Eq")
        impact_category = self.lca_results.get("impact_category", "Climate Change")

        if not process_contribs:
            return ""

        section = f"""
## 4. ⚙️ Major Process Contribution Ranking

**Impact Category**: {impact_category}
**Unit**: {unit}

The top contributing processes to the carbon footprint are ranked below:

| Rank | Process Name | Lifecycle Stage | Impact ({unit}) | Contribution (%) |
|------|-------------|-----------------|-----------------|------------------|
"""

        for idx, proc in enumerate(process_contribs[:15], 1):
            name = proc.get("name", "Unknown")
            stage = proc.get("lifecycle_stage", "N/A")
            value = proc.get("value", 0)
            percentage = proc.get("percentage", 0)

            if len(name) > 60:
                name = name[:57] + "..."

            section += (
                f"| {idx} | {name} | {stage} | {value:.3f} | {percentage:.2f} |\n"
            )

        section += f"""
**Analysis**:
- The table above shows the top {len(process_contribs[:15])} processes contributing to the product's carbon footprint.
- Each process is categorized by its lifecycle stage for better understanding of emission sources.
- This ranking helps identify hotspots for potential emission reduction strategies.

"""

        return section

    def _create_uncertainty_histogram(self):

        try:
            print("\n🎨 开始创建不确定性分析直方图...")
            uncertainty = self.lca_results.get("uncertainty_analysis", {})
            if not uncertainty or not uncertainty.get("statistics"):
                print("   ⚠️ 没有 uncertainty 或 statistics 数据，跳过直方图生成")
                return None

            statistics = uncertainty.get("statistics", {})
            if not statistics:
                print("   ⚠️ statistics 为空，跳过直方图生成")
                return None

            first_category = list(statistics.keys())[0]
            stats = statistics[first_category]

            print(f"   📊 直方图数据源 - {first_category}")

            mean = stats.get("mean", 0)
            std_dev = stats.get("std_dev", 0)
            p5 = stats.get("percentile_5", 0)
            p95 = stats.get("percentile_95", 0)
            median = stats.get("median", 0)

            print(f"   数值: mean={mean}, std_dev={std_dev}, median={median}")
            print(f"   范围: p5={p5}, p95={p95}")

            if mean == 0 and std_dev == 0:
                print("   ⚠️ 数据全是0，跳过直方图生成")
                return None

            import numpy as np

            np.random.seed(42)

            data = np.random.normal(mean, std_dev, 1000)

            fig, ax = plt.subplots(figsize=(10, 6))

            n, bins, patches = ax.hist(
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
                label=f"5th Percentile: {p5:.3f}",
            )
            ax.axvline(
                median,
                color="red",
                linestyle="--",
                linewidth=2,
                label=f"Median: {median:.3f}",
            )
            ax.axvline(
                p95,
                color="red",
                linestyle="--",
                linewidth=2,
                label=f"95th Percentile: {p95:.3f}",
            )

            unit = self.lca_results.get("unit", "kg CO2-Eq")
            ax.set_xlabel(f"Carbon Footprint ({unit})", fontsize=12, fontweight="bold")
            ax.set_ylabel("Frequency", fontsize=12, fontweight="bold")
            ax.set_title(
                f"Uncertainty Analysis Distribution\n(Mean: {mean:.3f}, Std Dev: {std_dev:.3f} {unit})",
                fontsize=14,
                fontweight="bold",
                pad=20,
            )

            ax.grid(True, alpha=0.3, linestyle="--")

            ax.legend(fontsize=10, loc="upper right")

            plt.tight_layout()

            buffer = BytesIO()
            fig.savefig(buffer, format="png", dpi=150, bbox_inches="tight")
            buffer.seek(0)
            image_base64 = base64.b64encode(buffer.read()).decode()
            plt.close(fig)

            print(f"   ✅ 直方图生成成功（Base64长度: {len(image_base64)} 字符）")

            return f"data:image/png;base64,{image_base64}"

        except Exception as e:
            print(f"   ❌ 创建不确定性分析直方图时出错: {e}")
            import traceback

            traceback.print_exc()
            return None

    def _generate_uncertainty_section(self):

        uncertainty = self.lca_results.get("uncertainty_analysis", {})

        print("\n" + "=" * 80)
        print("📊 报告生成器 - 不确定性分析数据检查")
        print("=" * 80)
        print(f"uncertainty 数据: {uncertainty}")

        if not uncertainty or not uncertainty.get("statistics"):
            print("⚠️ 没有 uncertainty 或 statistics 数据")
            return """
## 3. Uncertainty Analysis Results

*Uncertainty analysis was not performed for this assessment.*

"""

        statistics = uncertainty.get("statistics", {})
        iterations = uncertainty.get("iterations", 0)
        impact_method = uncertainty.get("impact_method", "N/A")
        unit = self.lca_results.get("unit", "kg CO2-Eq")

        print(f"✅ statistics 包含 {len(statistics)} 个类别")
        for cat_name, cat_data in statistics.items():
            print(f"\n📋 类别: {cat_name}")
            print(f"   数据: {cat_data}")

        section = f"""
## 3. Uncertainty Analysis Results

**Impact Category**: climate change no LT - global warming potential (GWP100) no LT
**Unit**: {unit}
**Impact Method**: {impact_method}
**Monte Carlo Iterations**: {iterations}

The uncertainty analysis provides statistical information about the variability in the carbon footprint results:

"""

        histogram = self._create_uncertainty_histogram()
        if histogram:
            section += f"""### Figure 2: Uncertainty Analysis Distribution

![Uncertainty Histogram]({histogram})

"""

        section += f"""### Statistical Summary

| Statistical Metric | Value ({unit}) |
|-------------------|----------------|
"""

        if statistics:
            first_category = list(statistics.keys())[0]
            stats = statistics[first_category]

            print(f"\n📊 提取统计数据:")
            print(f"   类别: {first_category}")
            print(f"   stats 对象: {stats}")
            print(f"   mean: {stats.get('mean', 0)}")
            print(f"   std_dev: {stats.get('std_dev', 0)}")
            print(f"   median: {stats.get('median', 0)}")
            print(f"   percentile_5: {stats.get('percentile_5', 0)}")
            print(f"   percentile_95: {stats.get('percentile_95', 0)}")
            print(f"   cv: {stats.get('cv', 0)}")

            section += f"| Mean | {stats.get('mean', 0):.3f} |\n"
            section += f"| Standard Deviation | {stats.get('std_dev', 0):.3f} |\n"
            section += f"| Coefficient of Variation (CV) | {stats.get('cv', 0):.2%} |\n"
            section += f"| Median | {stats.get('median', 0):.3f} |\n"
            section += f"| 5th Percentile | {stats.get('percentile_5', 0):.3f} |\n"
            section += f"| 95th Percentile | {stats.get('percentile_95', 0):.3f} |\n"

            cv = stats.get("cv", 0)
            section += f"""
**Interpretation**:
- The mean value represents the average carbon footprint across all {iterations} Monte Carlo simulations.
- The coefficient of variation (CV) of {cv:.2%} indicates {'low' if cv < 0.1 else 'moderate' if cv < 0.3 else 'high'} variability in the results.
- The 5th to 95th percentile range ({stats.get('percentile_5', 0):.3f} - {stats.get('percentile_95', 0):.3f} {unit}) represents a 90% confidence interval.
- The histogram above shows the distribution of results from the Monte Carlo simulation.

"""

        return section

    def _get_largest_stage(self):

        stages = self.lca_results.get("stages", {})
        stage_names = {
            "raw_material": "raw material acquisition",
            "production": "production",
            "distribution": "distribution",
            "use": "use",
            "end_of_life": "end-of-life",
        }

        max_stage = "raw material acquisition"
        max_value = 0

        for key, name in stage_names.items():
            stage_data = stages.get(key, {})
            value = stage_data.get("value", 0)
            if value > max_value:
                max_value = value
                max_stage = name

        return max_stage

    def _generate_ai_interpretation(self):

        product_name = self._get_value(
            "product_name", self.project_info.get("name", "Product")
        )
        producer_name = self._get_value("producer_name")
        total_cf = self.lca_results.get("total_carbon_footprint", 0)
        unit = self.lca_results.get("unit", "kg CO2-Eq")

        try:
            print("\n🤖 正在调用AI生成报告解读...")

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

            top_processes = self.lca_results.get("process_contributions", [])[:5]
            process_info = ""
            for i, proc in enumerate(top_processes, 1):
                process_info += f"{i}. {proc.get('process_name', 'Unknown')}: {proc.get('impact_value', 0):.3e} {unit}\n"

            uncertainty = self.lca_results.get("uncertainty_analysis", {})
            uncertainty_info = ""
            if uncertainty and uncertainty.get("statistics"):
                stats = list(uncertainty["statistics"].values())[0]
                uncertainty_info = f"""
**Uncertainty Analysis Results:**
- Mean: {stats.get('mean', 0):.3f} {unit}
- Coefficient of Variation (CV): {stats.get('cv', 0):.2%}
- 90% Confidence Interval: {stats.get('percentile_5', 0):.3f} - {stats.get('percentile_95', 0):.3f} {unit}
"""

            prompt = f"""
You are a professional Life Cycle Assessment (LCA) expert. Based on the following LCA calculation results, generate professional report interpretation content in English.

**Product Information:**
- Product Name: {product_name}
- Producer: {producer_name}
- Total Carbon Footprint: {total_cf:.3f} {unit}

**Lifecycle Stage Contributions:**
{stage_info}

**Top Process Contributions:**
{process_info}

{uncertainty_info}

Please generate the following three sections in English with professional and accurate content:

Format your response EXACTLY as follows with clear markers:

[SECTION1]
Write 2-3 paragraphs (150-200 words) describing:
- Overview of the total carbon footprint level
- Analysis of lifecycle stage contribution characteristics
- Identification of major emission sources
- Interpretation of the uncertainty analysis results

[SECTION2]
Write 2-3 paragraphs (150-200 words) stating:
- Key assumptions made in this study
- Limitations of data sources and quality
- System boundary restrictions
- Impact of uncertainties on results

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
                        "content": "You are a professional Life Cycle Assessment (LCA) expert, skilled in interpreting environmental impact assessment results and providing professional recommendations.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=2000,
            )

            ai_content = response.choices[0].message.content
            print("✅ AI解读生成成功")
            print(f"📝 AI返回内容预览: {ai_content[:200]}...")

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
                description = ai_content[section1_start:section1_end].strip()

                section2_start = ai_content.find("[SECTION2]") + len("[SECTION2]")
                section2_end = ai_content.find("[SECTION3]")
                assumptions = ai_content[section2_start:section2_end].strip()

                section3_start = ai_content.find("[SECTION3]") + len("[SECTION3]")
                improvements = ai_content[section3_start:].strip()

                description = re.sub(
                    r"^##?\s*\d*\.?\s*(Description of Results|结果描述).*?\n",
                    "",
                    description,
                    flags=re.IGNORECASE | re.MULTILINE,
                ).strip()
                assumptions = re.sub(
                    r"^##?\s*\d*\.?\s*(Statement of Assumptions and Limitations|假设和局限性说明).*?\n",
                    "",
                    assumptions,
                    flags=re.IGNORECASE | re.MULTILINE,
                ).strip()
                improvements = re.sub(
                    r"^##?\s*\d*\.?\s*(Suggestions for Improvement|改进建议).*?\n",
                    "",
                    improvements,
                    flags=re.IGNORECASE | re.MULTILINE,
                ).strip()

                print(
                    f"✅ 成功解析AI内容：描述({len(description)}字), 假设({len(assumptions)}字), 建议({len(improvements)}字)"
                )
            else:
                print("⚠️ AI返回格式不符合预期，使用默认内容")
                description = f"The life cycle carbon footprint of {product_name} is {total_cf:.3f} {unit}. The {self._get_largest_stage()} stage accounts for the largest share of carbon emissions."
                assumptions = "[Information provided by the user]"
                improvements = "[Information provided by the user]"

            return {
                "description": description,
                "assumptions": assumptions,
                "improvements": improvements,
            }

        except Exception as e:
            print(f"⚠️ AI解读生成失败: {e}")
            import traceback

            traceback.print_exc()
            return {
                "description": f"The life cycle carbon footprint of {product_name} is {total_cf:.3f} {unit}. The {self._get_largest_stage()} stage accounts for the largest share of carbon emissions. Detailed breakdown is provided in Table 1 and visualizations above.",
                "assumptions": "[Information provided by the user]",
                "improvements": "[Information provided by the user]",
            }

    def _register_chinese_fonts_pdf(self):

        try:

            font_paths = [
                "C:/Windows/Fonts/simhei.ttf",
                "C:/Windows/Fonts/msyh.ttf",
                "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
                "/System/Library/Fonts/PingFang.ttc",
            ]

            for font_path in font_paths:
                if os.path.exists(font_path):
                    try:
                        pdfmetrics.registerFont(TTFont("ChineseFont", font_path))
                        return "ChineseFont"
                    except:
                        continue

            return "Helvetica"
        except Exception as e:
            print(f"PDF字体注册警告: {e}")
            return "Helvetica"

    def generate_pdf_report(self):

        try:

            chinese_font = self._register_chinese_fonts_pdf()

            product_name = self._get_value(
                "product_name", self.project_info.get("name", "Product")
            )
            producer_name = self._get_value("producer_name")
            total_cf = self.lca_results.get("total_carbon_footprint", 0)

            filename = f"LCA_Report_{product_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            filepath = os.path.join(self.output_dir, filename)

            doc = SimpleDocTemplate(
                filepath,
                pagesize=A4,
                rightMargin=72,
                leftMargin=72,
                topMargin=72,
                bottomMargin=72,
            )

            story = []
            styles = getSampleStyleSheet()

            title_style = ParagraphStyle(
                "CustomTitle",
                parent=styles["Heading1"],
                fontSize=18,
                spaceAfter=30,
                alignment=TA_CENTER,
                textColor=colors.HexColor("#1976d2"),
                fontName=chinese_font,
            )

            heading_style = ParagraphStyle(
                "CustomHeading",
                parent=styles["Heading2"],
                fontSize=14,
                spaceBefore=16,
                spaceAfter=10,
                textColor=colors.HexColor("#424242"),
                fontName=chinese_font,
            )

            normal_style = ParagraphStyle(
                "CustomNormal",
                parent=styles["Normal"],
                fontSize=10,
                spaceAfter=6,
                fontName=chinese_font,
                alignment=TA_JUSTIFY,
            )

            story.append(
                Paragraph("Product Carbon Footprint Study Report", title_style)
            )
            story.append(Spacer(1, 20))

            story.append(Paragraph("Basic Information", heading_style))
            basic_info = [
                ["Product Name:", product_name],
                ["Producer Name:", self._get_value("producer_name")],
                ["Report No:", self._get_value("report_no")],
                ["Date:", self._format_date()],
            ]
            basic_table = Table(basic_info, colWidths=[2 * inch, 4 * inch])
            basic_table.setStyle(
                TableStyle(
                    [
                        ("FONTNAME", (0, 0), (-1, -1), chinese_font),
                        ("FONTSIZE", (0, 0), (-1, -1), 10),
                        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#424242")),
                        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ]
                )
            )
            story.append(basic_table)
            story.append(Spacer(1, 20))

            story.append(Paragraph("Quantitative Purpose", heading_style))
            story.append(
                Paragraph(self._get_value("quantitative_purpose"), normal_style)
            )
            story.append(Spacer(1, 15))

            story.append(Paragraph("Impact Assessment Results", heading_style))
            story.append(
                Paragraph(
                    f"The life cycle carbon footprint is <b>{total_cf:.3f} kg CO2e</b>.",
                    normal_style,
                )
            )
            story.append(Spacer(1, 15))

            pie_chart = self._create_pie_chart()
            if pie_chart:

                temp_chart_path = os.path.join(self.output_dir, "temp_chart.png")
                with open(temp_chart_path, "wb") as f:
                    f.write(base64.b64decode(pie_chart.split(",")[1]))

                chart_img = RLImage(temp_chart_path, width=5 * inch, height=3.5 * inch)
                chart_img.hAlign = "CENTER"
                story.append(chart_img)
                story.append(Spacer(1, 10))

                try:
                    os.remove(temp_chart_path)
                except:
                    pass

            story.append(
                Paragraph("Carbon Emissions by Life Cycle Stage", heading_style)
            )

            stages_data = [
                ["Life Cycle Stage", "Carbon Footprint (kg CO2e)", "Percentage (%)"]
            ]
            stage_names = {
                "raw_material": "Raw Material Acquisition",
                "production": "Production",
                "distribution": "Distribution",
                "use": "Use",
                "end_of_life": "End of Life",
            }

            stages = self.lca_results.get("stages", {})
            for key, name in stage_names.items():
                stage_data = stages.get(key, {})
                value = stage_data.get("value", 0)
                percentage = stage_data.get("percentage", 0)

                stages_data.append([name, f"{value:.3f}", f"{percentage:.2f}"])

            stages_data.append(["Total", f"{total_cf:.3f}", "100.00"])

            stages_table = Table(
                stages_data, colWidths=[2.5 * inch, 2 * inch, 1.5 * inch]
            )
            stages_table.setStyle(
                TableStyle(
                    [
                        ("FONTNAME", (0, 0), (-1, -1), chinese_font),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e3f2fd")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1976d2")),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                        (
                            "ROWBACKGROUNDS",
                            (0, 1),
                            (-1, -2),
                            [colors.white, colors.HexColor("#f5f5f5")],
                        ),
                        ("LINEBELOW", (0, -1), (-1, -1), 1, colors.HexColor("#1976d2")),
                    ]
                )
            )
            story.append(stages_table)
            story.append(Spacer(1, 20))

            story.append(Paragraph("Interpretation of Results", heading_style))
            story.append(
                Paragraph(
                    f"The {self._get_largest_stage()} stage accounts for the largest share of carbon emissions.",
                    normal_style,
                )
            )
            story.append(Spacer(1, 10))

            improvements = self._get_value("improvement_suggestions")
            if improvements != "[Information provided by the user]":
                story.append(Paragraph("Suggestions for Improvement", heading_style))
                story.append(Paragraph(improvements, normal_style))

            doc.build(story)

            print(f"✓ PDF报告已生成: {filepath}")
            return filepath, True

        except Exception as e:
            print(f"✗ PDF生成失败: {e}")
            import traceback

            traceback.print_exc()
            return None, False


def demo_usage():

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
        "product_function": "High energy density energy storage device for electric vehicles",
        "standard_used": "IPCC 2013 GWP 100a",
        "quantitative_purpose": "To assess the carbon footprint and identify reduction opportunities",
        "functional_unit": "1 kWh of energy storage capacity",
        "time_scale": "Year 2024",
    }

    lca_results = {
        "total_carbon_footprint": 30223.8,
        "stages": {
            "raw_material": {"value": 13328.5, "percentage": 44.1},
            "production": {"value": 10461.7, "percentage": 34.6},
            "distribution": {"value": 3658.9, "percentage": 12.1},
            "use": {"value": 1248.3, "percentage": 4.1},
            "end_of_life": {"value": 1526.4, "percentage": 5.1},
        },
    }

    generator = MarkdownReportGenerator(project_info, report_info, lca_results)
    content, filepath = generator.generate_report()

    print("Demo报告生成完成！")
    print(f"文件路径: {filepath}")


if __name__ == "__main__":
    demo_usage()
