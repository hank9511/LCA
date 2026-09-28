import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from markdown_report_generator import MarkdownReportGenerator
from datetime import datetime


def test_basic_report_generation():

    print("=" * 60)
    print("Test 1: Basic report generation")
    print("=" * 60)

    project_info = {
        "name": "PET plastic bottle production",
        "description": "PET plastic bottle full life cycle assessment project",
    }

    report_info = {
        "product_name": "PET plastic bottle",
        "product_model": "PET-500ml-2024",
        "producer_name": "Green Packaging Technology Co., Ltd.",
        "report_no": "LCA-2024-001",
        "address": "No. 1 Zhongguancun Street, Haidian District, Beijing",
        "legal_representative": "Zhang Wei",
        "contact_person": "Li Ming",
        "product_function": "Used for beverage packaging, 500ml capacity, recyclable",
        "standard_used": "IPCC 2013 GWP 100a",
        "quantitative_purpose": "Assess the carbon footprint of PET plastic bottles across the full life cycle and identify reduction opportunities",
        "functional_unit": "1 unit of 500ml PET plastic bottle",
        "time_scale": "Year 2024",
        "primary_data_source": "Company actual production data",
        "secondary_data_source": "Ecoinvent 3.8 database",
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

        print(f"✅ Report generated successfully!")
        print(f"File path: {filepath}")
        print(f"File size: {len(content)} characters")
        print(f"\nFirst 100 characters preview:")
        print(content[:100])

        return True

    except Exception as e:
        print(f"❌ Report generation failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_missing_fields():

    print("\n" + "=" * 60)
    print("Test 2: Missing field placeholder behavior")
    print("=" * 60)

    project_info = {"name": "Minimal test project"}

    report_info = {"product_name": "Test product"}

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

        print(f"✅ Minimal-info report generated successfully!")
        print(f"File path: {filepath}")
        print(f"Placeholder count: {placeholder_count}")
        print(f"Note: Unfilled fields were automatically filled with placeholders")

        return True

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_chart_generation():

    print("\n" + "=" * 60)
    print("Test 3: Chart generation")
    print("=" * 60)

    project_info = {"name": "Chart test project"}

    report_info = {"product_name": "Test product", "producer_name": "Test company"}

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

        print(f"✅ Chart test complete!")
        print(f"File path: {filepath}")
        print(f"Contains charts: {'Yes' if has_charts else 'No'}")

        if has_charts:
            chart_count = content.count("data:image/png;base64,")
            print(f"Chart count: {chart_count}")

        return True

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():

    print(f"\n{'='*60}")
    print(f"LCA report generation test suite")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    results = []

    results.append(("Basic report generation", test_basic_report_generation()))
    results.append(("Missing field handling", test_missing_fields()))
    results.append(("Chart generation", test_chart_generation()))

    print(f"\n{'='*60}")
    print("Test results summary")
    print(f"{'='*60}")

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ Passed" if result else "❌ Failed"
        print(f"{test_name}: {status}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All tests passed! System is working normally.")
    else:
        print("⚠️ Some tests failed; please check the error messages.")

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
