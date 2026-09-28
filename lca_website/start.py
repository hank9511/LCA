import subprocess
import sys
import os


def run_command(command, description, cwd=None):

    print(f"\n{description}...")
    print(f"Running command: {command}")
    if cwd:
        print(f"Working directory: {cwd}")

    try:
        result = subprocess.run(
            command, shell=True, check=True, capture_output=True, text=True, cwd=cwd
        )
        print("✓ Success")
        if result.stdout:
            print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed: {e}")
        if e.stderr:
            print(f"Error details: {e.stderr}")
        return False


def main():

    print("🚀 Starting LCA service website")
    print("=" * 50)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    print(f"Script directory: {script_dir}")

    app_file = os.path.join(script_dir, "app.py")
    if not os.path.exists(app_file):
        print(f"❌ Error: app.py not found")
        print(f"Expected path: {app_file}")
        return False

    print(f"✅ Found app.py: {app_file}")

    print(f"Python version: {sys.version}")

    print("\n📦 Installing Python dependencies...")
    dependencies = [
        "flask",
        "flask-sqlalchemy",
        "flask-login",
        "werkzeug",
        "pandas",
        "openpyxl",
        "openai",
    ]

    for dep in dependencies:
        if not run_command(f"pip install {dep}", f"Installing {dep}"):
            print(f"❌ Failed to install {dep}, check network or install manually")
            return False

    print("\n✅ All dependencies installed!")

    print("\n🌐 Starting website...")
    if not run_command("python app.py", "Starting Flask app", cwd=script_dir):
        print("❌ Failed to start application")
        return False

    return True


if __name__ == "__main__":
    try:
        success = main()
        if success:
            print("\n🎉 Website started successfully!")
        else:
            print("\n💥 Problems encountered during startup")
    except KeyboardInterrupt:
        print("\n\n⏹️  Interrupted by user")
    except Exception as e:
        print(f"\n❌ An error occurred: {e}")

    input("\nPress Enter to exit...")
