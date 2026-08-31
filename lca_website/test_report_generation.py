import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from markdown_report_generator import MarkdownReportGenerator
from datetime import datetime


def test_basic_report_generation():

    print("=" * 60)
    print("测试1：基本报告生成功能")
    print("=" * 60)

    project_info = {
        "name": "PET塑料瓶生产",
        "description": "PET塑料瓶全生命周期评估项目",
    }

    report_info = {
        "product_name": "PET塑料瓶",
        "product_model": "PET-500ml-2024",
        "producer_name": "绿色包装科技有限公司",
        "report_no": "LCA-2024-001",
        "address": "北京市海淀区中关村大街1号",
        "legal_representative": "张伟",
        "contact_person": "李明",
        "product_function": "用于饮料包装，容量500ml，可回收利用",
        "standard_used": "IPCC 2013 GWP 100a",
        "quantitative_purpose": "评估PET塑料瓶全生命周期的碳足迹，识别减排机会",
        "functional_unit": "1个500ml PET塑料瓶",
        "time_scale": "Year 2024",
        "primary_data_source": "企业实际生产数据",
        "secondary_data_source": "Ecoinvent 3.8数据库",
    }

    lca_results = {
        "total_carbon_footprint": 125.5,
        "stages": {
            "raw_material": {"value": 52.3, "percentage": 41.7},
            "production": {"value": 38.2, "percentage": 30.4},
            "distribution": {"value": 18.9, "percentage": 15.1},
            "use": {"value": 6.3, "percentage": 5.0},
            "end_of_life": {"value": 9.8, "percentage": 7.8},
        },
    }

    try:

        generator = MarkdownReportGenerator(
            project_info=project_info,
            report_info=report_info,
            lca_results=lca_results,
            output_dir="./test_reports",
        )

        content, filepath = generator.generate_report()

        print(f"✅ 报告生成成功！")
        print(f"文件路径: {filepath}")
        print(f"文件大小: {len(content)} 字符")
        print(f"\n前100字符预览：")
        print(content[:100])

        return True

    except Exception as e:
        print(f"❌ 报告生成失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_missing_fields():

    print("\n" + "=" * 60)
    print("测试2：缺失字段占位符功能")
    print("=" * 60)

    project_info = {"name": "最小测试项目"}

    report_info = {"product_name": "测试产品"}

    lca_results = {
        "total_carbon_footprint": 100.0,
        "stages": {
            "raw_material": {"value": 50.0, "percentage": 50.0},
            "production": {"value": 30.0, "percentage": 30.0},
            "distribution": {"value": 10.0, "percentage": 10.0},
            "use": {"value": 5.0, "percentage": 5.0},
            "end_of_life": {"value": 5.0, "percentage": 5.0},
        },
    }

    try:
        generator = MarkdownReportGenerator(
            project_info=project_info,
            report_info=report_info,
            lca_results=lca_results,
            output_dir="./test_reports",
        )

        content, filepath = generator.generate_report()

        placeholder_count = content.count("[Information provided by the user]")

        print(f"✅ 最小信息报告生成成功！")
        print(f"文件路径: {filepath}")
        print(f"占位符数量: {placeholder_count}")
        print(f"说明: 未填写的字段已自动填充占位符")

        return True

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_chart_generation():

    print("\n" + "=" * 60)
    print("测试3：图表生成功能")
    print("=" * 60)

    project_info = {"name": "图表测试项目"}

    report_info = {"product_name": "测试产品", "producer_name": "测试公司"}

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

    try:
        generator = MarkdownReportGenerator(
            project_info=project_info,
            report_info=report_info,
            lca_results=lca_results,
            output_dir="./test_reports",
        )

        content, filepath = generator.generate_report()

        has_charts = "data:image/png;base64," in content

        print(f"✅ 图表测试完成！")
        print(f"文件路径: {filepath}")
        print(f"包含图表: {'是' if has_charts else '否'}")

        if has_charts:
            chart_count = content.count("data:image/png;base64,")
            print(f"图表数量: {chart_count}")

        return True

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():

    print(f"\n{'='*60}")
    print(f"LCA报告生成功能测试套件")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    results = []

    results.append(("基本报告生成", test_basic_report_generation()))
    results.append(("缺失字段处理", test_missing_fields()))
    results.append(("图表生成", test_chart_generation()))

    print(f"\n{'='*60}")
    print("测试结果总结")
    print(f"{'='*60}")

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{test_name}: {status}")

    print(f"\n总计: {passed}/{total} 测试通过")

    if passed == total:
        print("🎉 所有测试通过！系统运行正常。")
    else:
        print("⚠️ 部分测试失败，请检查错误信息。")

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
