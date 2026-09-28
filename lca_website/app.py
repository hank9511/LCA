from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    jsonify,
    send_file,
    g,
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    login_required,
    logout_user,
    current_user,
)
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime, timedelta

try:
    from dotenv import load_dotenv
    import pathlib

    _env_path = pathlib.Path(__file__).parent.parent / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
        print(f"✅ Loaded .env from {_env_path}")
    else:
        _env_path_local = pathlib.Path(__file__).parent / ".env"
        if _env_path_local.exists():
            load_dotenv(_env_path_local)
            print(f"✅ Loaded .env from {_env_path_local}")
except ImportError:
    print("⚠️ python-dotenv not installed, env vars must be set manually")

import pandas as pd
import openai
import time
import json
import uuid
import random
import string
import traceback

from lca_service import lca_service
from async_lca_service import AsyncLCAService
from report_service import report_service
from markdown_report_generator import MarkdownReportGenerator
from pdf_report_generator import ProfessionalPDFReportGenerator

from translations import get_translation, get_all_translations

basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config["SECRET_KEY"] = "your-secret-key-here"

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(
    basedir, "instance", "lca_website.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = "uploads"

try:
    os.makedirs(os.path.join(basedir, "instance"))
except OSError:
    pass

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"


def _parse_ipc_ports(raw_ports: str):
    """Parse comma/semicolon separated IPC ports with dedup."""
    ports = []
    if not raw_ports:
        return ports
    normalized = raw_ports.replace("，", ",").replace(";", ",")
    for part in normalized.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            port = int(part)
            if port not in ports:
                ports.append(port)
        except ValueError:
            print(f"⚠️ Ignore invalid IPC port: {part}")
    return ports


_ipc_ports_raw = (
    os.environ.get("LCA_IPC_PORTS")
    or os.environ.get("OPENLCA_IPC_PORTS")
    or os.environ.get("LCA_IPC_PORT")
    or os.environ.get("OPENLCA_IPC_PORT")
    or "8080"
)
_ipc_ports = _parse_ipc_ports(_ipc_ports_raw) or [8080]

_max_concurrent_tasks_raw = os.environ.get("LCA_MAX_CONCURRENT_TASKS")
if _max_concurrent_tasks_raw is None:
    _max_concurrent_tasks = len(_ipc_ports)
else:
    try:
        _max_concurrent_tasks = max(1, int(_max_concurrent_tasks_raw))
    except ValueError:
        _max_concurrent_tasks = len(_ipc_ports)
        print(
            f"⚠️ Invalid LCA_MAX_CONCURRENT_TASKS={_max_concurrent_tasks_raw}, "
            f"fallback to {len(_ipc_ports)}"
        )

print(
    f"ℹ️ Async LCA scheduler config: max_concurrent={_max_concurrent_tasks}, "
    f"ipc_ports={_ipc_ports}"
)
async_lca_service = AsyncLCAService(
    app,
    lca_service,
    max_concurrent_tasks=_max_concurrent_tasks,
    ipc_ports=_ipc_ports,
)

user_project_association = db.Table(
    "user_project_association",
    db.Column("user_id", db.Integer, db.ForeignKey("user.id"), primary_key=True),
    db.Column(
        "project_id", db.String(8), db.ForeignKey("project.id"), primary_key=True
    ),
)


@app.template_filter("localtime")
def localtime_filter(dt):

    if dt is None:
        return None

    return dt


def generate_short_id():

    chars = string.ascii_uppercase.replace("O", "").replace(
        "I", ""
    ) + string.digits.replace("0", "").replace("1", "")
    return "".join(random.choice(chars) for _ in range(8))


class User(UserMixin, db.Model):

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    projects = db.relationship("Project", backref="owner", lazy=True)


class Project(db.Model):

    id = db.Column(db.String(8), primary_key=True, default=generate_short_id)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(20), default="active")
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    lca_data = db.relationship("LCAData", backref="project", lazy=True)
    excel_files = db.relationship("ExcelFile", backref="project", lazy=True)
    assessment_boundary = db.relationship(
        "AssessmentBoundary",
        backref="project",
        uselist=False,
        cascade="all, delete-orphan",
    )
    report_info = db.relationship(
        "ProjectReportInfo",
        backref="project",
        uselist=False,
        cascade="all, delete-orphan",
    )


class LCAData(db.Model):

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.String(8), db.ForeignKey("project.id"), nullable=False)
    data_type = db.Column(db.String(50), nullable=False)
    value = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)


class ExcelFile(db.Model):

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.String(8), db.ForeignKey("project.id"), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    upload_time = db.Column(db.DateTime, default=datetime.now)
    llm_analysis = db.Column(db.Text)
    llm_suggestions = db.Column(db.Text)
    analysis_time = db.Column(db.DateTime)
    is_deleted = db.Column(db.Boolean, default=False)
    deleted_time = db.Column(db.DateTime)
    lca_results = db.relationship("LCAResult", backref="excel_file", lazy=True)


class ProcessLifecycleStage(db.Model):

    __tablename__ = "process_lifecycle_stage"

    id = db.Column(db.Integer, primary_key=True)
    excel_file_id = db.Column(
        db.Integer, db.ForeignKey("excel_file.id", ondelete="CASCADE"), nullable=False
    )
    process_name = db.Column(db.String(500), nullable=False)
    lifecycle_stage = db.Column(db.String(100), nullable=False)
    is_auto_matched = db.Column(db.Boolean, default=True)
    confidence_score = db.Column(db.Float)
    llm_reasoning = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    excel_file = db.relationship(
        "ExcelFile",
        backref=db.backref(
            "process_lifecycle_stages", lazy=True, cascade="all, delete-orphan"
        ),
    )


class LCAResult(db.Model):

    id = db.Column(db.Integer, primary_key=True)
    excel_file_id = db.Column(
        db.Integer, db.ForeignKey("excel_file.id"), nullable=False
    )
    analysis_status = db.Column(db.String(20), default="pending")
    start_time = db.Column(db.DateTime, default=datetime.now)
    end_time = db.Column(db.DateTime)
    duration_seconds = db.Column(db.Float)
    flows_count = db.Column(db.Integer)
    processes_count = db.Column(db.Integer)
    product_systems_count = db.Column(db.Integer)
    openLCA_connected = db.Column(db.Boolean, default=False)
    error_message = db.Column(db.Text)
    analysis_details = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now)


class ProjectReportInfo(db.Model):

    __tablename__ = "project_report_info"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(
        db.String(8), db.ForeignKey("project.id"), nullable=False, unique=True
    )

    product_name = db.Column(db.Text)
    product_model = db.Column(db.Text)
    producer_name = db.Column(db.Text)
    report_no = db.Column(db.Text)
    address = db.Column(db.Text)
    legal_representative = db.Column(db.Text)
    contact_person = db.Column(db.Text)
    contact_phone = db.Column(db.Text)
    contact_email = db.Column(db.Text)

    product_function = db.Column(db.Text)
    standard_used = db.Column(db.Text, default="ecoinvent - EF v3.1")

    quantitative_purpose = db.Column(db.Text)
    functional_unit = db.Column(db.Text)
    system_boundary_description = db.Column(db.Text)
    system_boundary_stages = db.Column(db.Text)
    cutoff_criteria = db.Column(db.Text)
    time_scale = db.Column(db.Text)

    primary_data_source = db.Column(db.Text)
    secondary_data_source = db.Column(db.Text)

    allocation_basis = db.Column(db.Text)
    allocation_procedure = db.Column(db.Text)
    specific_allocations = db.Column(db.Text)

    data_quality_notes = db.Column(db.Text)

    impact_type_description = db.Column(
        db.Text, default="100-year global warming potential (GWP) given by IPCC"
    )

    assumptions_limitations = db.Column(db.Text)
    improvement_suggestions = db.Column(db.Text)

    enable_ai_suggestions = db.Column(db.Boolean, default=True)
    report_language = db.Column(db.String(10), default="en")

    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)


class AssessmentBoundary(db.Model):

    __tablename__ = "assessment_boundary"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.String(8), db.ForeignKey("project.id"), nullable=False)

    lifecycle_model = db.Column(db.String(50), default="cradle_to_gate")

    lifecycle_stages = db.Column(db.Text)

    stages_config = db.Column(db.Text)

    boundary_description = db.Column(db.Text)

    functional_unit = db.Column(db.String(100))

    reference_flow = db.Column(db.String(100))

    cutoff_criteria = db.Column(db.Text)
    cutoff_threshold = db.Column(db.Float, default=1.0)

    process_flow_diagram = db.Column(db.String(500))

    geographical_boundary = db.Column(db.String(200))

    temporal_boundary = db.Column(db.String(200))

    technological_boundary = db.Column(db.Text)

    allocation_method = db.Column(db.String(50), default="mass")
    allocation_description = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.before_request
def before_request():
    """Sets language before each request and ensures the async service"""
    async_lca_service.app = app

    g.language = request.args.get("lang") or session.get("language", "zh")

    session["language"] = g.language


@app.context_processor
def inject_translations():
    """Make translation functions available to all templates"""
    return {
        "t": lambda category, key: get_translation(
            category, key, g.get("language", "zh")
        ),
        "get_lang": lambda: g.get("language", "zh"),
    }


def format_excel_for_llm(df):

    try:

        total_rows = len(df)
        total_cols = len(df.columns)

        headers = list(df.columns)
        header_str = " | ".join([f"Column {i+1}: {col}" for i, col in enumerate(headers)])

        data_rows = []
        for i in range(min(10, total_rows)):
            row_data = []
            for j, col in enumerate(headers):
                value = str(df.iloc[i, j]) if pd.notna(df.iloc[i, j]) else "null"

                if len(value) > 50:
                    value = value[:47] + "..."
                row_data.append(f"{value}")
            data_rows.append(f"Row {i+1}: {' | '.join(row_data)}")

        formatted_data = f"""
Excel file structure analysis:
Total rows: {total_rows}
Total columns: {total_cols}

Column names:
{header_str}

Data sample (first {min(10, total_rows)} rows):
{chr(10).join(data_rows)}

Data type information:
"""

        for i, col in enumerate(headers):
            dtype = str(df[col].dtype)
            non_null_count = df[col].count()
            null_count = total_rows - non_null_count
            formatted_data += f"Column {i+1} ({col}): {dtype}, non-null: {non_null_count}, null: {null_count}\n"

        formatted_data += f"\nData quality assessment:\n"
        formatted_data += (
            f"- Data completeness: {non_null_count}/{total_rows * total_cols} cells have data\n"
        )
        formatted_data += (
            f"- Null ratio: {null_count/(total_rows * total_cols)*100:.1f}%\n"
        )

        return formatted_data

    except Exception as e:

        return f"Excel data formatting failed: {str(e)}\n\nRaw data:\n{df.to_string()}"


def call_grok_llm(excel_data, project_name):

    try:
        client = openai.OpenAI(
            api_key=os.environ.get("GROK_API_KEY", ""),
            base_url=os.environ.get("GROK_BASE_URL", "https://openrouter.ai/api/v1"),
        )

        prompt = f"""
        You are a professional LCA (Life Cycle Assessment) expert. Please analyze the following Excel data and assess whether it is suitable for LCA analysis.

        Project name: {project_name}

        Excel data content:
        {excel_data}

        Please provide a professional analysis covering the following aspects:

        1. **Data Completeness Assessment**
           - Whether the data fully covers all stages required for LCA
           - Whether necessary environmental impact factors are included
           - Analysis of missing data

        2. **Data Quality Check**
           - Whether data types are appropriate
           - Whether value ranges are reasonable
           - Whether units are consistent and standardized

        3. **LCA Standards Compliance**
           - Whether it complies with ISO 14040/14044 standards
           - Whether data classification is clear
           - Whether boundary setting is reasonable

        4. **Specific Improvement Suggestions**
           - Suggestions for optimizing data structure
           - Suggestions for supplementing missing data
           - Standardization suggestions

        5. **Excel File Structure Suggestions**
           - Whether column names are clear and explicit
           - Whether new columns need to be added
           - Whether the data organization approach is reasonable

        Please answer in English and provide professional, specific analysis and recommendations. If issues are found, clearly identify them and propose solutions.
        """

        response = client.chat.completions.create(
            model="x-ai/grok-3-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a professional LCA expert. Please provide professional and accurate analysis and recommendations.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=8000,
            stream=False,
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        return f"LLM analysis failed: {str(e)}"


@app.route("/")
def index():

    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            flash("Login successful!", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Incorrect username or password!", "error")

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = request.form["password"]

        if User.query.filter_by(username=username).first():
            flash("Username already exists!", "error")
            return render_template("register.html")

        if User.query.filter_by(email=email).first():
            flash("Email is already registered!", "error")
            return render_template("register.html")

        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
        )
        db.session.add(user)
        db.session.commit()

        flash("Registration successful! Please log in", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/logout")
@login_required
def logout():

    logout_user()
    flash("Logged out successfully!", "success")
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required
def dashboard():

    projects = Project.query.filter_by(user_id=current_user.id).all()
    return render_template("dashboard.html", projects=projects)


@app.route("/project/new", methods=["GET", "POST"])
@login_required
def new_project():

    if request.method == "POST":
        name = request.form["name"]
        description = request.form["description"]

        project = Project(name=name, description=description, user_id=current_user.id)
        db.session.add(project)
        db.session.commit()

        flash("Project created successfully!", "success")
        return redirect(url_for("dashboard"))

    return render_template("new_project.html")


@app.route("/project/<string:project_id>")
@login_required
def project_detail(project_id):

    project = Project.query.get_or_404(project_id)
    if project.user_id != current_user.id:
        flash("You do not have permission to access this project!", "error")
        return redirect(url_for("dashboard"))

    return render_template("project_detail.html", project=project)


@app.route("/project/<string:project_id>/edit", methods=["GET", "POST"])
@login_required
def edit_project(project_id):

    project = Project.query.get_or_404(project_id)
    if project.user_id != current_user.id:
        flash("You do not have permission to edit this project!", "error")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        project.name = request.form["name"]
        project.description = request.form["description"]
        project.status = request.form["status"]
        db.session.commit()

        flash("Project updated successfully!", "success")
        return redirect(url_for("project_detail", project_id=project.id))

    return render_template("edit_project.html", project=project)


@app.route("/project/<string:project_id>/wizard")
@login_required
def lca_wizard(project_id):

    project = Project.query.get_or_404(project_id)
    if project.user_id != current_user.id:
        flash("You do not have permission to access this project!", "error")
        return redirect(url_for("dashboard"))

    return render_template("lca_wizard.html", project=project)


def sync_metadata_to_report_info(excel_file, project_id):

    try:
        if not excel_file.metadata_json:
            print("⚠️ Excel file has no metadata, skipping report info sync")
            return False

        metadata = excel_file.metadata_json

        report_info = ProjectReportInfo.query.filter_by(project_id=project_id).first()
        if not report_info:
            report_info = ProjectReportInfo(project_id=project_id)
            db.session.add(report_info)
            print(f"📝 Creating new report info record")
        else:
            print(f"📝 Updating existing report info record")

        if metadata.get("product_info", {}).get("product_name"):
            report_info.product_name = metadata["product_info"]["product_name"]
            print(f"  - Product name: {report_info.product_name}")

        if metadata.get("product_info", {}).get("product_model"):
            report_info.product_model = metadata["product_info"]["product_model"]
            print(f"  - Product model: {report_info.product_model}")

        if metadata.get("product_info", {}).get("product_function"):
            report_info.product_function = metadata["product_info"]["product_function"]
            print(f"  - Product function set")

        if metadata.get("producer_info", {}).get("producer_name"):
            report_info.producer_name = metadata["producer_info"]["producer_name"]
            print(f"  - Producer name: {report_info.producer_name}")

        if metadata.get("producer_info", {}).get("address"):
            report_info.address = metadata["producer_info"]["address"]
            print(f"  - Address set")

        if metadata.get("producer_info", {}).get("legal_representative"):
            report_info.legal_representative = metadata["producer_info"][
                "legal_representative"
            ]
            print(f"  - Legal representative: {report_info.legal_representative}")

        if metadata.get("producer_info", {}).get("contact_person"):
            report_info.contact_person = metadata["producer_info"]["contact_person"]
            print(f"  - Contact person: {report_info.contact_person}")

        if metadata.get("producer_info", {}).get("contact_phone"):
            report_info.contact_phone = metadata["producer_info"]["contact_phone"]
            print(f"  - Contact phone: {report_info.contact_phone}")

        if metadata.get("producer_info", {}).get("report_number"):
            report_info.report_no = metadata["producer_info"]["report_number"]
            print(f"  - Report No.: {report_info.report_no}")

        quantification_method_data = metadata.get("quantification_method", {})
        if quantification_method_data.get("quantitative_method"):
            report_info.standard_used = quantification_method_data[
                "quantitative_method"
            ]
            print(f"  - Quantification method (LCIA): {report_info.standard_used}")
        elif quantification_method_data.get("standard"):
            report_info.standard_used = quantification_method_data["standard"]
            print(f"  - Based on standard: {report_info.standard_used}")

        if metadata.get("quantification_purpose"):
            report_info.quantitative_purpose = metadata["quantification_purpose"]
            print(f"  - Quantitative purpose set")

        if metadata.get("quantification_scope", {}).get("functional_unit"):
            report_info.functional_unit = metadata["quantification_scope"][
                "functional_unit"
            ]
            print(f"  - Functional unit: {report_info.functional_unit}")

        if metadata.get("quantification_scope", {}).get("system_boundary"):
            report_info.system_boundary_description = metadata["quantification_scope"][
                "system_boundary"
            ]
            print(f"  - System boundary description set")

        if metadata.get("quantification_scope", {}).get("cutoff_criteria"):
            report_info.cutoff_criteria = metadata["quantification_scope"][
                "cutoff_criteria"
            ]
            print(f"  - Cut-off criteria set")

        if metadata.get("quantification_scope", {}).get("time_scope"):
            report_info.time_scale = metadata["quantification_scope"]["time_scope"]
            print(f"  - Time scale: {report_info.time_scale}")

        if metadata.get("inventory_analysis", {}).get("primary_data_source"):
            report_info.primary_data_source = metadata["inventory_analysis"][
                "primary_data_source"
            ]
            print(f"  - Primary data source set")

        if metadata.get("inventory_analysis", {}).get("secondary_data_source"):
            report_info.secondary_data_source = metadata["inventory_analysis"][
                "secondary_data_source"
            ]
            print(f"  - Secondary data source set")

        if metadata.get("inventory_analysis", {}).get("allocation_basis"):
            report_info.allocation_basis = metadata["inventory_analysis"][
                "allocation_basis"
            ]
            print(f"  - Allocation basis: {report_info.allocation_basis}")

        if metadata.get("inventory_analysis", {}).get("allocation_procedure"):
            report_info.allocation_procedure = metadata["inventory_analysis"][
                "allocation_procedure"
            ]
            print(f"  - Allocation procedure set")

        report_info.updated_at = datetime.now()
        db.session.commit()

        print(f"✅ Successfully synced Excel metadata to LCA report info")
        return True

    except Exception as e:
        print(f"❌ Failed to sync metadata to report info: {e}")
        import traceback

        traceback.print_exc()
        return False


def sync_metadata_to_assessment_boundary(excel_file, project_id):

    try:
        if not excel_file.metadata_json:
            print("⚠️ Excel file has no metadata, skipping sync")
            return False

        metadata = excel_file.metadata_json

        boundary = AssessmentBoundary.query.filter_by(project_id=project_id).first()
        if not boundary:
            boundary = AssessmentBoundary(project_id=project_id)
            db.session.add(boundary)
            print(f"📝 Creating new assessment boundary settings")
        else:
            print(f"📝 Updating existing assessment boundary settings")

        if metadata.get("quantification_scope", {}).get("functional_unit"):
            boundary.functional_unit = metadata["quantification_scope"][
                "functional_unit"
            ]
            print(f"  - Functional unit: {boundary.functional_unit}")

        if metadata.get("quantification_scope", {}).get("system_boundary"):
            boundary.boundary_description = metadata["quantification_scope"][
                "system_boundary"
            ]
            print(f"  - System boundary description set")

        if metadata.get("quantification_scope", {}).get("time_scope"):
            boundary.temporal_boundary = metadata["quantification_scope"]["time_scope"]
            print(f"  - Temporal boundary: {boundary.temporal_boundary}")

        if metadata.get("quantification_scope", {}).get("cutoff_criteria"):
            boundary.cutoff_criteria = metadata["quantification_scope"][
                "cutoff_criteria"
            ]
            print(f"  - Cut-off rules set")

        allocation_basis = (
            metadata.get("inventory_analysis", {}).get("allocation_basis", "").lower()
        )
        if allocation_basis:

            if "mass" in allocation_basis:
                boundary.allocation_method = "mass"
            elif "economic" in allocation_basis:
                boundary.allocation_method = "economic"
            elif "energy" in allocation_basis:
                boundary.allocation_method = "energy"
            elif "physical" in allocation_basis:
                boundary.allocation_method = "physical"
            elif "none" in allocation_basis:
                boundary.allocation_method = "none"
            print(f"  - Allocation method: {boundary.allocation_method}")

        if metadata.get("inventory_analysis", {}).get("allocation_procedure"):
            boundary.allocation_description = metadata["inventory_analysis"][
                "allocation_procedure"
            ]
            print(f"  - Allocation description set")

        standard = metadata.get("quantification_method", {}).get("standard", "").lower()
        system_boundary = (
            metadata.get("quantification_scope", {}).get("system_boundary", "").lower()
        )

        if any(
            keyword in system_boundary
            for keyword in [
                "cradle-to-grave",
                "cradle to grave",
                "disposal",
                "end-of-life",
            ]
        ):
            boundary.lifecycle_model = "cradle_to_grave"
            print(f"  - Lifecycle model: cradle-to-grave")
        elif any(
            keyword in system_boundary
            for keyword in ["cradle-to-gate", "cradle to gate"]
        ):
            boundary.lifecycle_model = "cradle_to_gate"
            print(f"  - Lifecycle model: cradle-to-gate")
        elif any(
            keyword in system_boundary
            for keyword in ["gate-to-gate", "gate to gate"]
        ):
            boundary.lifecycle_model = "gate_to_gate"
            print(f"  - Lifecycle model: gate-to-gate")
        elif any(
            keyword in system_boundary
            for keyword in [
                "cradle-to-cradle",
                "cradle to cradle",
            ]
        ):
            boundary.lifecycle_model = "cradle_to_cradle"
            print(f"  - Lifecycle model: cradle-to-cradle")

        boundary.updated_at = datetime.now()
        db.session.commit()

        print(f"✅ Successfully synced Excel metadata to assessment boundary settings")
        return True

    except Exception as e:
        print(f"❌ Failed to sync metadata to assessment boundary: {e}")
        import traceback

        traceback.print_exc()
        return False


@app.route("/project/<string:project_id>/assessment_boundary", methods=["GET", "POST"])
@login_required
def assessment_boundary(project_id):

    project = Project.query.get_or_404(project_id)
    if project.user_id != current_user.id:
        flash("You do not have permission to access this project!", "error")
        return redirect(url_for("dashboard"))

    boundary = AssessmentBoundary.query.filter_by(project_id=project_id).first()

    if request.method == "POST":

        if not boundary:
            boundary = AssessmentBoundary(project_id=project_id)
            db.session.add(boundary)

        boundary.lifecycle_model = request.form.get("lifecycle_model", "cradle_to_gate")
        boundary.functional_unit = request.form.get("functional_unit", "")
        boundary.reference_flow = request.form.get("reference_flow", "")
        boundary.boundary_description = request.form.get("boundary_description", "")

        boundary.geographical_boundary = request.form.get("geographical_boundary", "")
        boundary.temporal_boundary = request.form.get("temporal_boundary", "")
        boundary.technological_boundary = request.form.get("technological_boundary", "")

        boundary.cutoff_criteria = request.form.get("cutoff_criteria", "")
        try:
            boundary.cutoff_threshold = float(request.form.get("cutoff_threshold", 1.0))
        except ValueError:
            boundary.cutoff_threshold = 1.0

        boundary.allocation_method = request.form.get("allocation_method", "mass")
        boundary.allocation_description = request.form.get("allocation_description", "")

        if "process_flow_diagram" in request.files:
            file = request.files["process_flow_diagram"]
            if file and file.filename:

                upload_dir = os.path.join(
                    app.root_path, "uploads", str(project_id), "diagrams"
                )
                os.makedirs(upload_dir, exist_ok=True)

                filename = f"diagram_{int(time.time())}_{file.filename}"
                file_path = os.path.join(upload_dir, filename)
                file.save(file_path)
                boundary.process_flow_diagram = filename

        boundary.updated_at = datetime.now()
        db.session.commit()

        flash("Assessment boundary settings saved!", "success")
        return redirect(url_for("project_detail", project_id=project_id))

    return render_template(
        "assessment_boundary.html", project=project, boundary=boundary
    )


@app.route("/project/<string:project_id>/upload_excel", methods=["GET", "POST"])
@login_required
def upload_excel(project_id):

    project = Project.query.get_or_404(project_id)
    if project.user_id != current_user.id:
        flash("You do not have permission to access this project!", "error")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        if "excel_file" not in request.files:
            flash("No file selected!", "error")
            return redirect(request.url)

        file = request.files["excel_file"]
        if file.filename == "":
            flash("No file selected!", "error")
            return redirect(request.url)

        if file and file.filename.endswith((".xlsx", ".xls")):

            upload_dir = os.path.join(app.root_path, "uploads", str(project_id))
            os.makedirs(upload_dir, exist_ok=True)

            filename = f"excel_{int(time.time())}_{file.filename}"
            file_path = os.path.join(upload_dir, filename)
            file.save(file_path)

            try:
                df = pd.read_excel(file_path)

                excel_data = format_excel_for_llm(df)

                excel_file = ExcelFile(
                    project_id=project_id,
                    filename=filename,
                    original_filename=file.filename,
                    file_path=file_path,
                    file_size=os.path.getsize(file_path),
                )

                try:
                    from lca_automation.excel_parser import ExcelLCAParser

                    parser = ExcelLCAParser(file_path)
                    metadata = parser.parse_excel_metadata()
                    excel_file.metadata_json = metadata
                    print(f"✅ Successfully parsed Excel metadata with {len(metadata)} sections")
                except Exception as metadata_error:
                    print(f"⚠️ Failed to parse Excel metadata: {str(metadata_error)}")

                    pass

                db.session.add(excel_file)
                db.session.commit()

                sync_messages = []
                try:
                    if excel_file.metadata_json:

                        boundary_success = sync_metadata_to_assessment_boundary(
                            excel_file, project_id
                        )
                        if boundary_success:
                            sync_messages.append("assessment boundary settings")

                        report_success = sync_metadata_to_report_info(
                            excel_file, project_id
                        )
                        if report_success:
                            sync_messages.append("LCA report info")

                        if sync_messages:
                            flash(
                                f'✅ Excel metadata auto-synced to: {", ".join(sync_messages)}',
                                "success",
                            )
                except Exception as sync_error:
                    print(f"⚠️ Failed to sync metadata: {str(sync_error)}")

                    pass

                flash("Excel file uploaded successfully! Analyzing...", "success")
                db.session.commit()

                try:
                    llm_result = call_grok_llm(excel_data, project.name)

                    excel_file.llm_analysis = llm_result
                    excel_file.analysis_time = datetime.now()
                    db.session.commit()

                    flash("LLM analysis complete!", "success")
                except Exception as e:
                    flash(f"LLM analysis failed: {str(e)}", "error")

                try:
                    from lca_automation.excel_parser import ExcelLCAParser
                    from lca_automation.lifecycle_stage_matcher import (
                        match_lifecycle_stage_with_llm,
                        fallback_rule_based_matching,
                    )

                    parser = ExcelLCAParser(file_path)
                    lca_case = parser.parse_excel_to_lca_case()

                    process_names = [proc.name for proc in lca_case.processes]

                    if process_names:

                        matches = None
                        try:
                            api_key = os.environ.get("GROK_API_KEY", "")
                            matches = match_lifecycle_stage_with_llm(
                                process_names, api_key
                            )
                            print(f"✓ LLM successfully matched life cycle stages for {len(matches)} processes")
                        except Exception as llm_error:
                            print(f"⚠️ LLM matching failed: {str(llm_error)}, using rule-based matching")

                            matches = fallback_rule_based_matching(process_names)
                            print(
                                f"✓ Rule-based matching successfully matched life cycle stages for {len(matches)} processes"
                            )

                        if matches:
                            for process_name, match_info in matches.items():
                                stage_record = ProcessLifecycleStage(
                                    excel_file_id=excel_file.id,
                                    process_name=process_name,
                                    lifecycle_stage=match_info["stage"],
                                    is_auto_matched=True,
                                    confidence_score=match_info.get("confidence", 0.5),
                                    llm_reasoning=match_info.get("reasoning", ""),
                                )
                                db.session.add(stage_record)

                            db.session.commit()
                            print(
                                f"✓ Successfully saved {len(matches)} life cycle stage mappings to database"
                            )

                except Exception as e:
                    print(f"⚠️ Process life cycle stage matching failed: {str(e)}")
                    import traceback

                    traceback.print_exc()

                return redirect(url_for("show_parsed_excel", file_id=excel_file.id))

            except Exception as e:
                flash(f"Excel file processing failed: {str(e)}", "error")
                return redirect(request.url)
        else:
            flash("Only Excel file formats are supported!", "error")
            return redirect(request.url)

    return render_template("upload_excel.html", project=project)


@app.route("/excel_file/<int:file_id>/parsed")
@login_required
def show_parsed_excel(file_id):

    excel_file = ExcelFile.query.get_or_404(file_id)
    project = Project.query.get(excel_file.project_id)

    if project.user_id != current_user.id:
        flash("You do not have permission to access this file!", "error")
        return redirect(url_for("dashboard"))

    stage_mappings = ProcessLifecycleStage.query.filter_by(excel_file_id=file_id).all()

    from lca_automation.lifecycle_stage_matcher import get_all_lifecycle_stages

    available_stages = get_all_lifecycle_stages()

    return render_template(
        "parsed_excel.html",
        project=project,
        excel_file=excel_file,
        stage_mappings=stage_mappings,
        available_stages=available_stages,
    )


@app.route("/excel_file/<int:file_id>/update_lifecycle_stage", methods=["POST"])
@login_required
def update_lifecycle_stage(file_id):

    excel_file = ExcelFile.query.get_or_404(file_id)
    project = Project.query.get(excel_file.project_id)

    if project.user_id != current_user.id:
        return jsonify({"success": False, "error": "You do not have permission to modify this file!"}), 403

    try:
        data = request.get_json()
        process_name = data.get("process_name")
        new_stage = data.get("lifecycle_stage")

        if not process_name or not new_stage:
            return jsonify({"success": False, "error": "Missing required parameters"}), 400

        stage_mapping = ProcessLifecycleStage.query.filter_by(
            excel_file_id=file_id, process_name=process_name
        ).first()

        if stage_mapping:

            stage_mapping.lifecycle_stage = new_stage
            stage_mapping.is_auto_matched = False
            stage_mapping.updated_at = datetime.now()
        else:

            stage_mapping = ProcessLifecycleStage(
                excel_file_id=file_id,
                process_name=process_name,
                lifecycle_stage=new_stage,
                is_auto_matched=False,
            )
            db.session.add(stage_mapping)

        db.session.commit()

        return jsonify({"success": True, "message": "Life cycle stage updated"})

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": f"Update failed: {str(e)}"}), 500


@app.route("/project/<string:project_id>/excel_files")
@login_required
def excel_files(project_id):

    project = Project.query.get_or_404(project_id)
    if project.user_id != current_user.id:
        flash("You do not have permission to access this project!", "error")
        return redirect(url_for("dashboard"))

    excel_files = (
        ExcelFile.query.filter_by(project_id=project_id)
        .order_by(ExcelFile.upload_time.desc())
        .all()
    )
    return render_template("excel_files.html", project=project, excel_files=excel_files)


@app.route("/excel_file/<int:file_id>/download")
@login_required
def download_excel(file_id):

    excel_file = ExcelFile.query.get_or_404(file_id)
    project = Project.query.get(excel_file.project_id)

    if project.user_id != current_user.id:
        flash("You do not have permission to download this file!", "error")
        return redirect(url_for("excel_files", project_id=excel_file.project_id))

    if os.path.exists(excel_file.file_path):
        return send_file(
            excel_file.file_path,
            as_attachment=True,
            download_name=excel_file.original_filename,
        )
    else:
        flash("File does not exist!", "error")
        return redirect(url_for("excel_files", project_id=excel_file.project_id))


@app.route("/excel_file/<int:file_id>/sync_to_boundary", methods=["POST"])
@login_required
def sync_excel_to_boundary(file_id):

    excel_file = ExcelFile.query.get_or_404(file_id)
    project = Project.query.get(excel_file.project_id)

    if project.user_id != current_user.id:
        return jsonify({"success": False, "error": "You do not have permission to perform this operation!"}), 403

    try:
        if not excel_file.metadata_json:
            return jsonify({"success": False, "error": "Excel file has no metadata!"}), 400

        success = sync_metadata_to_assessment_boundary(
            excel_file, excel_file.project_id
        )

        if success:
            return jsonify(
                {"success": True, "message": "✅ Successfully synced Excel metadata to assessment boundary settings!"}
            )
        else:
            return (
                jsonify({"success": False, "error": "Sync failed; please check server logs"}),
                500,
            )

    except Exception as e:
        return jsonify({"success": False, "error": f"Sync failed: {str(e)}"}), 500


@app.route("/excel_file/<int:file_id>/sync_to_report_info", methods=["POST"])
@login_required
def sync_excel_to_report_info(file_id):

    excel_file = ExcelFile.query.get_or_404(file_id)
    project = Project.query.get(excel_file.project_id)

    if project.user_id != current_user.id:
        return jsonify({"success": False, "error": "You do not have permission to perform this operation!"}), 403

    try:
        if not excel_file.metadata_json:
            return jsonify({"success": False, "error": "Excel file has no metadata!"}), 400

        success = sync_metadata_to_report_info(excel_file, excel_file.project_id)

        if success:
            return jsonify(
                {"success": True, "message": "✅ Successfully synced Excel metadata to LCA report info!"}
            )
        else:
            return (
                jsonify({"success": False, "error": "Sync failed; please check server logs"}),
                500,
            )

    except Exception as e:
        return jsonify({"success": False, "error": f"Sync failed: {str(e)}"}), 500


@app.route("/excel_file/<int:file_id>/metadata", methods=["GET"])
@login_required
def get_excel_metadata(file_id):

    excel_file = ExcelFile.query.get_or_404(file_id)
    project = Project.query.get(excel_file.project_id)

    if project.user_id != current_user.id:
        return jsonify({"success": False, "error": "You do not have permission to access this file!"}), 403

    return jsonify(
        {
            "success": True,
            "metadata": excel_file.metadata_json if excel_file.metadata_json else {},
        }
    )


@app.route("/excel_file/<int:file_id>/metadata", methods=["POST"])
@login_required
def update_excel_metadata(file_id):

    excel_file = ExcelFile.query.get_or_404(file_id)
    project = Project.query.get(excel_file.project_id)

    if project.user_id != current_user.id:
        return jsonify({"success": False, "error": "You do not have permission to modify this file!"}), 403

    try:

        metadata = request.get_json()

        if not metadata:
            return jsonify({"success": False, "error": "No metadata provided!"}), 400

        excel_file.metadata_json = metadata
        db.session.commit()

        return jsonify({"success": True, "message": "Metadata updated successfully!"})

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": f"Update failed: {str(e)}"}), 500


@app.route("/excel_file/<int:file_id>/delete", methods=["POST"])
@login_required
def delete_excel_file(file_id):

    excel_file = ExcelFile.query.get_or_404(file_id)
    project = Project.query.get(excel_file.project_id)

    if project.user_id != current_user.id:
        flash("You do not have permission to delete this file!", "error")
        return redirect(url_for("project_detail", project_id=excel_file.project_id))

    excel_file.is_deleted = True
    excel_file.deleted_time = datetime.utcnow()

    if os.path.exists(excel_file.file_path):
        try:
            os.remove(excel_file.file_path)
        except Exception as e:
            flash(f"File deletion failed: {str(e)}", "warning")

    db.session.commit()
    flash("File deleted; conversation history retained!", "success")
    return redirect(url_for("project_detail", project_id=excel_file.project_id))


@app.route("/excel_file/<int:file_id>/delete_and_all_related", methods=["POST"])
@login_required
def delete_excel_file_and_all_related(file_id):

    excel_file = ExcelFile.query.get_or_404(file_id)
    project = Project.query.get(excel_file.project_id)

    if project.user_id != current_user.id:
        flash("You do not have permission to delete this file!", "error")
        return redirect(url_for("project_detail", project_id=excel_file.project_id))

    if os.path.exists(excel_file.file_path):
        try:
            os.remove(excel_file.file_path)
        except Exception as e:
            flash(f"File deletion failed: {str(e)}", "warning")

    try:

        lca_results = LCAResult.query.filter_by(excel_file_id=file_id).all()
        print(f"🗑️ Found {len(lca_results)} related LCA analysis results, preparing to delete...")

        for lca_result in lca_results:
            db.session.delete(lca_result)

        lifecycle_stages = ProcessLifecycleStage.query.filter_by(
            excel_file_id=file_id
        ).all()
        print(f"🗑️ Found {len(lifecycle_stages)} related life cycle stage mappings, preparing to delete...")

        for stage in lifecycle_stages:
            db.session.delete(stage)

        db.session.delete(excel_file)
        db.session.commit()

        print(
            f"✅ Successfully deleted Excel file and {len(lca_results)} LCA results, {len(lifecycle_stages)} life cycle stage mappings"
        )

    except Exception as e:
        db.session.rollback()
        flash(f"Error during batch deletion: {str(e)}", "error")
        print(f"❌ Deletion failed: {str(e)}")
        import traceback

        traceback.print_exc()
        return redirect(url_for("project_detail", project_id=excel_file.project_id))

    flash("File and all related content fully deleted!", "success")
    return redirect(url_for("project_detail", project_id=excel_file.project_id))


@app.route("/project/<string:project_id>/delete_all_excel", methods=["POST"])
@login_required
def delete_all_excel_files(project_id):

    project = Project.query.get_or_404(project_id)

    if project.user_id != current_user.id:
        flash("You do not have permission to delete files for this project!", "error")
        return redirect(url_for("project_detail", project_id=project_id))

    excel_files = ExcelFile.query.filter_by(
        project_id=project_id, is_deleted=False
    ).all()

    if not excel_files:
        flash("This project has no Excel files to delete!", "info")
        return redirect(url_for("project_detail", project_id=project_id))

    deleted_count = 0
    for excel_file in excel_files:

        excel_file.is_deleted = True
        excel_file.deleted_time = datetime.utcnow()

        if os.path.exists(excel_file.file_path):
            try:
                os.remove(excel_file.file_path)
                deleted_count += 1
            except Exception as e:
                flash(
                    f"Failed to delete file {excel_file.original_filename}: {str(e)}", "warning"
                )

    db.session.commit()
    flash(f"Successfully deleted {deleted_count} Excel files; conversation history retained!", "success")
    return redirect(url_for("project_detail", project_id=project_id))


@app.route(
    "/project/<string:project_id>/delete_all_excel_and_history", methods=["POST"]
)
@login_required
def delete_all_excel_and_history(project_id):

    project = Project.query.get_or_404(project_id)

    if project.user_id != current_user.id:
        flash("You do not have permission to delete files for this project!", "error")
        return redirect(url_for("project_detail", project_id=project_id))

    excel_files = ExcelFile.query.filter_by(
        project_id=project_id, is_deleted=False
    ).all()

    if not excel_files:
        flash("This project has no Excel files to delete!", "info")
        return redirect(url_for("project_detail", project_id=project_id))

    deleted_count = 0
    total_lca_results_deleted = 0

    try:
        for excel_file in excel_files:

            if os.path.exists(excel_file.file_path):
                try:
                    os.remove(excel_file.file_path)
                except Exception as e:
                    flash(
                        f"Failed to delete file {excel_file.original_filename}: {str(e)}",
                        "warning",
                    )

            lca_results = LCAResult.query.filter_by(excel_file_id=excel_file.id).all()
            for lca_result in lca_results:
                db.session.delete(lca_result)
                total_lca_results_deleted += 1

            lifecycle_stages = ProcessLifecycleStage.query.filter_by(
                excel_file_id=excel_file.id
            ).all()
            for stage in lifecycle_stages:
                db.session.delete(stage)

            db.session.delete(excel_file)
            deleted_count += 1

        db.session.commit()
        print(
            f"✅ Batch deletion succeeded: {deleted_count} Excel files, {total_lca_results_deleted} LCA results"
        )

    except Exception as e:
        db.session.rollback()
        flash(f"Error during batch deletion: {str(e)}", "error")
        print(f"❌ Batch deletion failed: {str(e)}")
        return redirect(url_for("project_detail", project_id=project_id))
    flash(f"Successfully deleted {deleted_count} Excel files and all conversation history!", "success")
    return redirect(url_for("project_detail", project_id=project_id))


@app.route("/project/<string:project_id>/check_analysis_status")
@login_required
def check_analysis_status(project_id):

    project = Project.query.get_or_404(project_id)

    if project.user_id != current_user.id:
        return jsonify({"success": False, "error": "Access denied"})

    latest_file = (
        ExcelFile.query.filter_by(project_id=project_id)
        .order_by(ExcelFile.upload_time.desc())
        .first()
    )

    if latest_file and latest_file.llm_analysis:

        return jsonify(
            {
                "success": True,
                "has_completed_analysis": True,
                "analysis_time": (
                    latest_file.analysis_time.strftime("%Y-%m-%d %H:%M")
                    if latest_file.analysis_time
                    else None
                ),
            }
        )
    else:

        return jsonify({"success": True, "has_completed_analysis": False})


@app.route("/excel_file/<int:file_id>/full_analysis")
@login_required
def get_full_analysis(file_id):

    excel_file = ExcelFile.query.get_or_404(file_id)
    project = Project.query.get(excel_file.project_id)

    if project.user_id != current_user.id:
        return jsonify({"success": False, "error": "Access denied"})

    if excel_file.llm_analysis:
        return jsonify({"success": True, "analysis": excel_file.llm_analysis})
    else:
        return jsonify({"success": False, "error": "No analysis results yet"})


@app.route("/excel_file/<int:file_id>/preview")
@login_required
def preview_excel(file_id):

    excel_file = ExcelFile.query.get_or_404(file_id)
    project = Project.query.get(excel_file.project_id)

    if project.user_id != current_user.id:
        return jsonify({"success": False, "error": "Access denied"})

    try:
        if os.path.exists(excel_file.file_path):

            df = pd.read_excel(excel_file.file_path)

            preview_data = []
            for col in df.columns:
                col_data = {
                    "column_name": str(col),
                    "data_type": str(df[col].dtype),
                    "sample_data": str(df[col].iloc[0]) if len(df) > 0 else "N/A",
                }
                preview_data.append(col_data)

            return jsonify(
                {
                    "success": True,
                    "data": preview_data,
                    "total_rows": len(df),
                    "total_columns": len(df.columns),
                }
            )
        else:
            return jsonify({"success": False, "error": "File does not exist"})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/excel_file/<int:file_id>/download_analysis")
@login_required
def download_analysis(file_id):

    excel_file = ExcelFile.query.get_or_404(file_id)
    project = Project.query.get(excel_file.project_id)

    if project.user_id != current_user.id:
        flash("You do not have permission to download this analysis result!", "error")
        return redirect(url_for("project_detail", project_id=excel_file.project_id))

    if not excel_file.llm_analysis:
        flash("No analysis results available for download!", "error")
        return redirect(url_for("project_detail", project_id=excel_file.project_id))

    analysis_text = f"""LCA Excel File Analysis Report

File name: {excel_file.original_filename}
    Upload time: {excel_file.upload_time.strftime('%Y-%m-%d %H:%M:%S')}
    Analysis time: {excel_file.analysis_time.strftime('%Y-%m-%d %H:%M:%S') if excel_file.analysis_time else 'N/A'}

AI analysis results:
{excel_file.llm_analysis}

---
Generated by LCA service website
    Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

    from io import BytesIO

    output = BytesIO()
    output.write(analysis_text.encode("utf-8"))
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name=f"LCA_Analysis_Report_{excel_file.original_filename.replace('.xlsx', '').replace('.xls', '')}.txt",
        mimetype="text/plain",
    )


@app.route("/excel_file/<int:file_id>/run_lca_analysis_async", methods=["POST"])
@login_required
def run_lca_analysis_async(file_id):

    excel_file = ExcelFile.query.get_or_404(file_id)
    project = Project.query.get(excel_file.project_id)

    if project.user_id != current_user.id:
        return jsonify({"success": False, "error": "You do not have permission to run LCA analysis on this file!"})

    if not os.path.exists(excel_file.file_path):
        return jsonify({"success": False, "error": "File does not exist!"})

    try:

        request_data = request.get_json() or {}
        preferred_lcia_method = request_data.get("lcia_method")

        if preferred_lcia_method:
            print(f"[WEB ASYNC] User selected LCIA method: {preferred_lcia_method}")

        task_id = async_lca_service.start_lca_analysis(
            file_id,
            excel_file.file_path,
            excel_file.project_id,
            preferred_lcia_method=preferred_lcia_method,
        )

        task_status = async_lca_service.get_task_status(task_id)
        return jsonify(
            {
                "success": True,
                "task_id": task_id,
                "task_status": task_status.get("status"),
                "queue_position": task_status.get("queue_position"),
                "message": "Task submitted to scheduler; use task_id to query progress",
            }
        )

    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to start analysis: {str(e)}"})


@app.route("/lca/batch/run_async", methods=["POST"])
@login_required
def run_lca_batch_analysis_async():

    request_data = request.get_json() or {}
    file_ids = request_data.get("file_ids", [])
    preferred_lcia_method = request_data.get("lcia_method")

    if not isinstance(file_ids, list) or not file_ids:
        return (
            jsonify(
                {
                    "success": False,
                    "error": "file_ids must be a non-empty array",
                }
            ),
            400,
        )

    accepted_tasks = []
    rejected_tasks = []

    for raw_file_id in file_ids:
        try:
            file_id = int(raw_file_id)
        except (TypeError, ValueError):
            rejected_tasks.append(
                {
                    "file_id": raw_file_id,
                    "error": "Invalid file_id",
                }
            )
            continue

        excel_file = ExcelFile.query.get(file_id)
        if not excel_file:
            rejected_tasks.append(
                {
                    "file_id": file_id,
                    "error": "File does not exist",
                }
            )
            continue

        project = Project.query.get(excel_file.project_id)
        if not project or project.user_id != current_user.id:
            rejected_tasks.append(
                {
                    "file_id": file_id,
                    "error": "No permission to access the project for this file",
                }
            )
            continue

        if not os.path.exists(excel_file.file_path):
            rejected_tasks.append(
                {
                    "file_id": file_id,
                    "error": "File path does not exist",
                }
            )
            continue

        try:
            task_id = async_lca_service.start_lca_analysis(
                file_id,
                excel_file.file_path,
                excel_file.project_id,
                preferred_lcia_method=preferred_lcia_method,
            )
            task_status = async_lca_service.get_task_status(task_id)
            accepted_tasks.append(
                {
                    "file_id": file_id,
                    "project_id": excel_file.project_id,
                    "task_id": task_id,
                    "task_status": task_status.get("status"),
                    "queue_position": task_status.get("queue_position"),
                }
            )
        except Exception as exc:
            rejected_tasks.append(
                {
                    "file_id": file_id,
                    "error": f"Submission failed: {exc}",
                }
            )

    queue_stats = async_lca_service.get_queue_stats()
    return jsonify(
        {
            "success": len(accepted_tasks) > 0,
            "accepted_count": len(accepted_tasks),
            "rejected_count": len(rejected_tasks),
            "accepted_tasks": accepted_tasks,
            "rejected_tasks": rejected_tasks,
            "queue_stats": queue_stats,
        }
    )


@app.route("/lca_task/<task_id>/status")
@login_required
def get_lca_task_status(task_id):

    try:
        status = async_lca_service.get_task_status(task_id)
        return jsonify(status)
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to get status: {str(e)}"})


@app.route("/lca/queue/status")
@login_required
def get_lca_queue_status():

    force_check = str(request.args.get("force_check", "0")).lower() in (
        "1",
        "true",
        "yes",
    )
    return jsonify(async_lca_service.get_queue_stats(force_check=force_check))


@app.route("/debug/lca_tasks")
@login_required
def debug_lca_tasks():

    try:
        tasks = async_lca_service.running_tasks
        queue_stats = async_lca_service.get_queue_stats()
        return jsonify(
            {
                "success": True,
                "total_tasks": len(tasks),
                "queue_stats": queue_stats,
                "tasks": {
                    task_id: {
                        "status": task_info["status"],
                        "progress": task_info["progress"],
                        "start_time": (
                            task_info["start_time"].isoformat()
                            if task_info.get("start_time")
                            else None
                        ),
                        "file_id": task_info["file_id"],
                    }
                    for task_id, task_info in tasks.items()
                },
            }
        )
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to get task list: {str(e)}"})


@app.route("/excel_file/<int:file_id>/check_lca_completion")
@login_required
def check_lca_completion(file_id):

    try:
        excel_file = ExcelFile.query.get_or_404(file_id)
        project = Project.query.get(excel_file.project_id)

        if project.user_id != current_user.id:
            return jsonify({"success": False, "error": "Permission denied"})

        recent_result = (
            LCAResult.query.filter_by(excel_file_id=file_id)
            .order_by(LCAResult.created_at.desc())
            .first()
        )

        if recent_result:
            return jsonify(
                {
                    "success": True,
                    "has_results": True,
                    "latest_result": {
                        "id": recent_result.id,
                        "status": recent_result.analysis_status,
                        "start_time": (
                            recent_result.start_time.isoformat()
                            if recent_result.start_time
                            else None
                        ),
                        "end_time": (
                            recent_result.end_time.isoformat()
                            if recent_result.end_time
                            else None
                        ),
                        "duration": recent_result.duration_seconds,
                        "created_at": recent_result.created_at.isoformat(),
                    },
                }
            )
        else:
            return jsonify(
                {
                    "success": True,
                    "has_results": False,
                    "message": "No LCA analysis records found",
                }
            )

    except Exception as e:
        return jsonify({"success": False, "error": f"Check failed: {str(e)}"})


@app.route("/excel_file/<int:file_id>/create_manual_lca_result", methods=["POST"])
@login_required
def create_manual_lca_result(file_id):

    try:
        excel_file = ExcelFile.query.get_or_404(file_id)
        project = Project.query.get(excel_file.project_id)

        if project.user_id != current_user.id:
            return jsonify({"success": False, "error": "Permission denied"})

        lca_result = LCAResult(
            excel_file_id=file_id,
            analysis_status="completed",
            start_time=datetime.now() - timedelta(minutes=5),
            end_time=datetime.now(),
            duration_seconds=300,
            openLCA_connected=True,
            analysis_details=json.dumps(
                {
                    "manual_creation": True,
                    "message": "Manually created LCA completion record based on successful analysis shown in the terminal",
                },
                ensure_ascii=False,
            ),
        )

        db.session.add(lca_result)
        db.session.commit()

        return jsonify(
            {
                "success": True,
                "message": "LCA completion record created",
                "result_id": lca_result.id,
            }
        )

    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to create record: {str(e)}"})


@app.route("/excel_file/<int:file_id>/run_lca_analysis", methods=["POST"])
@login_required
def run_lca_analysis(file_id):

    excel_file = ExcelFile.query.get_or_404(file_id)
    project = Project.query.get(excel_file.project_id)

    if project.user_id != current_user.id:
        return jsonify({"success": False, "error": "You do not have permission to run LCA analysis on this file!"})

    if not os.path.exists(excel_file.file_path):
        return jsonify({"success": False, "error": "File does not exist!"})

    try:

        request_data = request.get_json() or {}
        preferred_lcia_method = request_data.get("lcia_method")

        if preferred_lcia_method:
            print(f"[WEB] User selected LCIA method: {preferred_lcia_method}")

        existing_analysis = LCAResult.query.filter_by(
            excel_file_id=file_id, analysis_status="running"
        ).first()

        if existing_analysis:
            return jsonify(
                {"success": False, "error": "An LCA analysis is already running for this file; please wait for it to finish!"}
            )

        lca_result = LCAResult(
            excel_file_id=file_id, analysis_status="running", start_time=datetime.now()
        )
        db.session.add(lca_result)
        db.session.commit()

        analysis_result = lca_service.run_lca_analysis_on_file(
            excel_file.file_path,
            excel_file.project_id,
            preferred_lcia_method=preferred_lcia_method,
        )

        lca_result.end_time = datetime.now()

        if analysis_result["success"]:
            lca_result.analysis_status = "completed"
            lca_result.openLCA_connected = True

            details = analysis_result.get("details", {})
            lca_result.duration_seconds = details.get("duration_seconds", 0)
            lca_result.analysis_details = json.dumps(
                analysis_result, ensure_ascii=False
            )

            basic_results = analysis_result.get("basic_results", {})
            if basic_results:
                lca_result.flows_count = len(basic_results.get("flows", []))
                lca_result.processes_count = len(basic_results.get("processes", []))
                lca_result.product_systems_count = len(
                    basic_results.get("product_systems", [])
                )
                print(
                    f"✅ Extracted stats from analysis results: flows={lca_result.flows_count}, processes={lca_result.processes_count}, systems={lca_result.product_systems_count}"
                )
            else:

                print("⚠️ basic_results unavailable, trying create_lca_case_preview method...")
                case_preview = lca_service.create_lca_case_preview(excel_file.file_path)
                if case_preview["success"]:
                    case_info = case_preview["lca_case_info"]
                    lca_result.flows_count = case_info["flows_count"]
                    lca_result.processes_count = case_info["processes_count"]
                    lca_result.product_systems_count = case_info[
                        "product_systems_count"
                    ]
                    print(
                        f"✅ Extracted stats from case preview: flows={lca_result.flows_count}, processes={lca_result.processes_count}, systems={lca_result.product_systems_count}"
                    )
                else:

                    lca_result.flows_count = 0
                    lca_result.processes_count = 0
                    lca_result.product_systems_count = 0
                    print("⚠️ Unable to get statistics, setting defaults to 0")

            db.session.commit()

            return jsonify(
                {
                    "success": True,
                    "message": "LCA analysis complete!",
                    "result": {
                        "id": lca_result.id,
                        "status": lca_result.analysis_status,
                        "duration": lca_result.duration_seconds,
                        "flows_count": lca_result.flows_count,
                        "processes_count": lca_result.processes_count,
                        "product_systems_count": lca_result.product_systems_count,
                    },
                }
            )
        else:
            lca_result.analysis_status = "failed"
            lca_result.error_message = analysis_result.get("error", "Unknown error")
            lca_result.analysis_details = json.dumps(
                analysis_result, ensure_ascii=False
            )
            db.session.commit()

            return jsonify(
                {
                    "success": False,
                    "error": f"LCA analysis failed: {analysis_result.get('error', 'Unknown error')}",
                    "details": analysis_result.get("details", ""),
                }
            )

    except Exception as e:

        if "lca_result" in locals():
            lca_result.analysis_status = "failed"
            lca_result.error_message = str(e)
            lca_result.end_time = datetime.now()
            db.session.commit()

        return jsonify({"success": False, "error": f"Error during analysis: {str(e)}"})


@app.route("/api/available_lcia_methods", methods=["GET"])
@login_required
def get_available_lcia_methods():

    try:
        result = lca_service.get_available_lcia_methods()

        if result["success"]:
            return jsonify(
                {
                    "success": True,
                    "methods": result["methods"],
                    "count": result["count"],
                }
            )
        else:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": result.get("error", "Failed to fetch LCIA methods"),
                        "methods": [],
                    }
                ),
                500,
            )

    except Exception as e:
        return (
            jsonify(
                {
                    "success": False,
                    "error": f"Error fetching LCIA methods: {str(e)}",
                    "methods": [],
                }
            ),
            500,
        )


@app.route("/excel_file/<int:file_id>/lca_results")
@login_required
def get_lca_results(file_id):

    excel_file = ExcelFile.query.get_or_404(file_id)
    project = Project.query.get(excel_file.project_id)

    if project.user_id != current_user.id:
        return jsonify({"success": False, "error": "You do not have permission to view this analysis result!"})

    lca_results = (
        LCAResult.query.filter_by(excel_file_id=file_id)
        .order_by(LCAResult.created_at.desc())
        .all()
    )

    results_data = []
    for result in lca_results:
        result_data = {
            "id": result.id,
            "status": result.analysis_status,
            "start_time": (
                result.start_time.strftime("%Y-%m-%d %H:%M:%S")
                if result.start_time
                else None
            ),
            "end_time": (
                result.end_time.strftime("%Y-%m-%d %H:%M:%S")
                if result.end_time
                else None
            ),
            "duration_seconds": result.duration_seconds,
            "flows_count": result.flows_count,
            "processes_count": result.processes_count,
            "product_systems_count": result.product_systems_count,
            "openLCA_connected": result.openLCA_connected,
            "error_message": result.error_message,
        }
        results_data.append(result_data)

    return jsonify({"success": True, "results": results_data})


@app.route("/lca_result/<int:result_id>/visualization")
@login_required
def lca_visualization(result_id):

    lca_result = LCAResult.query.get_or_404(result_id)
    excel_file = ExcelFile.query.get(lca_result.excel_file_id)
    project = Project.query.get(excel_file.project_id)

    if project.user_id != current_user.id:
        flash("You do not have permission to view this analysis result!", "error")
        return redirect(url_for("dashboard"))

    timing_display = None
    if lca_result.analysis_details:
        try:
            details = json.loads(lca_result.analysis_details)
            tb = details.get("timing_breakdown")
            if tb:

                def _fmt_seconds(s):
                    s = float(s or 0)
                    if s >= 60:
                        m = int(s // 60)
                        sec = s % 60
                        return f"{m}m {sec:.0f}s"
                    return f"{s:.1f}s"

                timing_display = {
                    "model_build": _fmt_seconds(tb.get("model_build_seconds", 0)),
                    "lca_calc": _fmt_seconds(tb.get("lca_calc_seconds", 0)),
                    "total": _fmt_seconds(tb.get("total_seconds", 0)),
                }
        except Exception:
            pass

    return render_template(
        "lca_visualization.html",
        result=lca_result,
        project=project,
        timing_display=timing_display,
    )


@app.route("/lca_result/<int:result_id>/details")
@login_required
def get_lca_result_details(result_id):

    lca_result = LCAResult.query.get_or_404(result_id)
    excel_file = ExcelFile.query.get(lca_result.excel_file_id)
    project = Project.query.get(excel_file.project_id)

    if project.user_id != current_user.id:
        return jsonify({"success": False, "error": "You do not have permission to view this analysis result!"})

    analysis_details = {}
    if lca_result.analysis_details:
        try:
            analysis_details = json.loads(lca_result.analysis_details)
        except:
            analysis_details = {"raw": lca_result.analysis_details}

    return jsonify(
        {
            "success": True,
            "result": {
                "id": lca_result.id,
                "status": lca_result.analysis_status,
                "start_time": (
                    lca_result.start_time.strftime("%Y-%m-%d %H:%M:%S")
                    if lca_result.start_time
                    else None
                ),
                "end_time": (
                    lca_result.end_time.strftime("%Y-%m-%d %H:%M:%S")
                    if lca_result.end_time
                    else None
                ),
                "duration_seconds": lca_result.duration_seconds,
                "flows_count": lca_result.flows_count,
                "processes_count": lca_result.processes_count,
                "product_systems_count": lca_result.product_systems_count,
                "openLCA_connected": lca_result.openLCA_connected,
                "error_message": lca_result.error_message,
                "analysis_details": analysis_details,
            },
        }
    )


@app.route("/lca_result/<int:result_id>/chart_data")
@login_required
def get_lca_chart_data(result_id):

    lca_result = LCAResult.query.get_or_404(result_id)
    excel_file = ExcelFile.query.get(lca_result.excel_file_id)
    project = Project.query.get(excel_file.project_id)

    if project.user_id != current_user.id:
        return jsonify({"success": False, "error": "You do not have permission to view this analysis result!"})

    chart_data = {
        "success": True,
        "impact_categories": [],
        "lifecycle_stages": [],
        "contribution_analysis": {},
        "process_contributions": [],
        "climate_categories": [],
        "all_available_categories": [],
        "uncertainty_analysis": {},
        "debug_info": {},
    }

    if not lca_result.analysis_details:
        chart_data["debug_info"]["message"] = "No analysis_details data"
        return jsonify(chart_data)

    try:
        details = json.loads(lca_result.analysis_details)
        chart_data["debug_info"]["has_details"] = True
        chart_data["debug_info"]["top_level_keys"] = list(details.keys())

        comprehensive = details.get("comprehensive_results", {})

        impact_analysis = comprehensive.get("impact_analysis", {})
        if impact_analysis:
            chart_data["debug_info"]["has_impact_analysis"] = True
            chart_data["debug_info"]["impact_keys"] = list(impact_analysis.keys())

            if "impact_results" in impact_analysis:
                impact_results = impact_analysis["impact_results"]
                chart_data["debug_info"]["impact_results_count"] = (
                    len(impact_results) if isinstance(impact_results, list) else 0
                )

                if isinstance(impact_results, list):
                    for impact in impact_results:
                        value = float(impact.get("value", 0))
                        category = impact.get("category", "Unknown")
                        unit = impact.get("unit", "")

                        chart_data["all_available_categories"].append(
                            {
                                "category": category,
                                "value": value,
                                "unit": unit,
                                "description": impact.get("description", ""),
                            }
                        )

                        if value != 0:
                            chart_data["impact_categories"].append(
                                {
                                    "category": category,
                                    "value": value,
                                    "unit": unit,
                                    "description": impact.get("description", ""),
                                }
                            )

                            if any(
                                keyword in category.lower()
                                for keyword in ["climate", "gwp", "warming"]
                            ):
                                chart_data["climate_categories"].append(
                                    {"category": category, "value": value, "unit": unit}
                                )

        inventory = comprehensive.get("inventory_results", {})
        if inventory:
            chart_data["debug_info"]["has_inventory"] = True

            if "flow_results" in inventory:
                flows = inventory["flow_results"]
                chart_data["debug_info"]["flow_count"] = (
                    len(flows) if isinstance(flows, list) else 0
                )

                if isinstance(flows, list) and len(flows) > 0:

                    sorted_flows = sorted(
                        flows, key=lambda x: abs(float(x.get("value", 0))), reverse=True
                    )
                    for flow in sorted_flows[:10]:
                        value = abs(float(flow.get("value", 0)))
                        if value != 0:
                            chart_data["lifecycle_stages"].append(
                                {
                                    "stage": flow.get("flow_name", "Unknown"),
                                    "value": value,
                                    "unit": flow.get("unit", ""),
                                    "is_input": flow.get("is_input", False),
                                }
                            )

        contribution = comprehensive.get("contribution_analysis", {})
        if contribution:
            chart_data["debug_info"]["has_contribution"] = True

            selected_impact_category = contribution.get("selected_impact_category")
            selected_impact_unit = contribution.get("selected_impact_unit")
            if selected_impact_category:
                chart_data["lifecycle_impact_category"] = selected_impact_category
                chart_data["lifecycle_impact_unit"] = selected_impact_unit
                print(
                    f"📊 Life cycle stage analysis using impact category: {selected_impact_category} ({selected_impact_unit})"
                )

            if "process_contributions" in contribution:
                process_contribs = contribution["process_contributions"]
                chart_data["debug_info"]["process_contributions_count"] = (
                    len(process_contribs) if isinstance(process_contribs, list) else 0
                )

                if isinstance(process_contribs, list) and len(process_contribs) > 0:

                    stage_mappings_db = ProcessLifecycleStage.query.filter_by(
                        excel_file_id=excel_file.id
                    ).all()
                    process_stage_map = {
                        mapping.process_name: mapping.lifecycle_stage
                        for mapping in stage_mappings_db
                    }

                    from lifecycle_classifier import classify_lifecycle_stage

                    stage_name_map = {
                        "overall": "Overall Stage",
                        "raw_material": "Raw Material Acquisition",
                        "production": "Production",
                        "transport": "Distribution",
                        "use": "Use",
                        "disposal": "End of Life",
                        "recycling": "Recycling",
                    }

                    sorted_contribs = sorted(
                        process_contribs,
                        key=lambda x: x.get("contribution_percent", 0),
                        reverse=True,
                    )

                    for proc in sorted_contribs[:15]:
                        process_name = proc.get("process_name", "Unknown")

                        stage_key = process_stage_map.get(process_name)
                        if not stage_key:

                            stage_key = classify_lifecycle_stage(process_name)

                        stage_name = stage_name_map.get(stage_key, "Unclassified")

                        chart_data["process_contributions"].append(
                            {
                                "name": process_name,
                                "value": proc.get("impact_value", 0),
                                "percentage": proc.get("contribution_percent", 0),
                                "unit": proc.get("unit", "kg CO2 eq"),
                                "lifecycle_stage": stage_name,
                                "lifecycle_stage_key": stage_key,
                            }
                        )

                    lifecycle_aggregated = {}

                    smart_classified_count = 0
                    db_matched_count = 0

                    for proc in sorted_contribs:
                        process_name = proc.get("process_name", "")
                        impact = proc.get("impact_value", 0)

                        stage_key = process_stage_map.get(process_name)

                        if stage_key:

                            db_matched_count += 1
                        else:

                            stage_key = classify_lifecycle_stage(process_name)
                            smart_classified_count += 1

                        stage_name = stage_name_map.get(stage_key, "Unclassified")

                        if stage_name not in lifecycle_aggregated:
                            lifecycle_aggregated[stage_name] = {
                                "impacts": [],
                                "processes": [],
                            }
                        lifecycle_aggregated[stage_name]["impacts"].append(impact)
                        lifecycle_aggregated[stage_name]["processes"].append(
                            process_name
                        )

                    print(f"✅ Life cycle stage aggregation complete:")
                    print(f"   - Database mapping: {db_matched_count} processes")
                    print(f"   - Smart classification: {smart_classified_count} processes")
                    print(f"   - Total stages: {len(lifecycle_aggregated)}")

                    for stage_name, stage_data in lifecycle_aggregated.items():
                        impacts = stage_data["impacts"]
                        if impacts:
                            total_impact = sum(impacts)
                            if total_impact > 1e-15:
                                chart_data["lifecycle_stages"].append(
                                    {
                                        "stage": stage_name,
                                        "value": total_impact,
                                        "unit": "kg CO2 eq",
                                        "process_count": len(impacts),
                                        "processes": stage_data["processes"][:5],
                                    }
                                )

                    has_overall_mapping = any(
                        m.lifecycle_stage == "overall" for m in stage_mappings_db
                    )
                    if has_overall_mapping:

                        total_all_stages = sum(
                            s["value"]
                            for s in chart_data["lifecycle_stages"]
                            if s["stage"] != "Overall Stage"
                        )

                        if total_all_stages > 1e-15:

                            chart_data["lifecycle_stages"].insert(
                                0,
                                {
                                    "stage": "Overall Stage",
                                    "value": total_all_stages,
                                    "unit": "kg CO2 eq",
                                    "process_count": sum(
                                        s["process_count"]
                                        for s in chart_data["lifecycle_stages"]
                                    ),
                                    "processes": [],
                                },
                            )
                            print(f"✅ Added 'Overall Stage' (sum of all sub-stages)")

                    print(
                        f"✅ Extracted {len(chart_data['process_contributions'])} process contributions"
                    )
                    print(
                        f"✅ Identified {len([s for s in chart_data['lifecycle_stages'] if s['value'] > 0])} life cycle stages"
                    )

            system_structure = contribution.get("system_structure", {})
            if system_structure:
                chart_data["contribution_analysis"] = {
                    "reference_process": system_structure.get("reference_process", ""),
                    "total_processes": system_structure.get("total_processes", 0),
                    "contribution_tree_available": contribution.get(
                        "contribution_tree_available", False
                    ),
                }

            if not chart_data["all_available_categories"]:
                all_category_contributions = contribution.get(
                    "all_category_contributions", {}
                )
                if all_category_contributions:
                    print(
                        f"\n📊 Extracting all impact categories from all_category_contributions (fallback)..."
                    )
                    for (
                        category_name,
                        process_list,
                    ) in all_category_contributions.items():
                        if isinstance(process_list, list) and len(process_list) > 0:

                            total_value = sum(
                                p.get("impact_value", 0) for p in process_list
                            )
                            unit = (
                                process_list[0].get("unit", "") if process_list else ""
                            )

                            chart_data["all_available_categories"].append(
                                {
                                    "category": category_name,
                                    "value": total_value,
                                    "unit": unit,
                                }
                            )

                            if any(
                                keyword in category_name.lower()
                                for keyword in ["climate", "gwp", "warming"]
                            ):
                                chart_data["climate_categories"].append(
                                    {
                                        "category": category_name,
                                        "value": total_value,
                                        "unit": unit,
                                    }
                                )

                    print(
                        f"✅ Extracted {len(chart_data['all_available_categories'])} impact categories (from all_category_contributions)"
                    )
                    print(
                        f"✅ Of which {len(chart_data['climate_categories'])} are Climate Change categories"
                    )
            else:
                print(
                    f"✅ Extracted {len(chart_data['all_available_categories'])} impact categories from impact_analysis"
                )
                print(
                    f"✅ Of which {len(chart_data['climate_categories'])} are Climate Change categories"
                )

        if not chart_data["process_contributions"]:
            process_results = comprehensive.get("process_results", {})
            if process_results:
                chart_data["debug_info"]["has_process_results"] = True
                chart_data["debug_info"]["using_fallback_process_results"] = True

                if "process_list" in process_results:
                    processes = process_results["process_list"]
                    chart_data["debug_info"]["process_count"] = (
                        len(processes) if isinstance(processes, list) else 0
                    )

                    if isinstance(processes, list):
                        for proc in processes[:10]:
                            chart_data["process_contributions"].append(
                                {
                                    "name": proc.get("name", "Unknown"),
                                    "category": proc.get("category", "Uncategorized"),
                                    "location": proc.get("location", "Unknown"),
                                    "value": 0,
                                    "percentage": 0,
                                }
                            )

        if (
            not chart_data["impact_categories"]
            and not chart_data["lifecycle_stages"]
            and not chart_data["process_contributions"]
        ):

            chart_data["debug_info"]["trying_root_level"] = True

            if "impact_analysis" in details:
                root_impact = details["impact_analysis"]
                if "impact_results" in root_impact and isinstance(
                    root_impact["impact_results"], list
                ):
                    for impact in root_impact["impact_results"]:
                        value = float(impact.get("value", 0))
                        if value != 0:
                            chart_data["impact_categories"].append(
                                {
                                    "category": impact.get("category", "Unknown"),
                                    "value": value,
                                    "unit": impact.get("unit", ""),
                                    "description": impact.get("description", ""),
                                }
                            )

        uncertainty = comprehensive.get("uncertainty_analysis", {})
        if uncertainty:
            chart_data["debug_info"]["has_uncertainty"] = True

            statistics = uncertainty.get("statistics", {})
            raw_results = uncertainty.get("raw_results", {})

            if statistics:

                climate_uncertainty = {}
                climate_raw_data = {}

                for category_name, stat_data in statistics.items():
                    if any(
                        keyword in category_name.lower()
                        for keyword in ["climate", "gwp", "warming", "gtp"]
                    ):
                        climate_uncertainty[category_name] = {
                            "mean": stat_data.get("mean", 0),
                            "std_dev": stat_data.get("std", 0),
                            "cv": stat_data.get("cv", 0),
                            "percentile_5": stat_data.get("p5", 0),
                            "percentile_95": stat_data.get("p95", 0),
                            "median": stat_data.get("median", 0),
                            "unit": stat_data.get("unit", "kg CO2 eq"),
                            "sample_size": stat_data.get("sample_size", 0),
                            "min": stat_data.get("min", 0),
                            "max": stat_data.get("max", 0),
                        }

                        if category_name in raw_results:
                            raw_category_data = raw_results[category_name]
                            if "values" in raw_category_data:
                                climate_raw_data[category_name] = raw_category_data[
                                    "values"
                                ]

                chart_data["uncertainty_analysis"] = {
                    "statistics": climate_uncertainty,
                    "raw_data": climate_raw_data,
                    "iterations": uncertainty.get("iterations", 0),
                    "impact_method": uncertainty.get("impact_method", ""),
                    "available_categories": list(climate_uncertainty.keys()),
                }

                print(
                    f"✅ Extracted uncertainty analysis results for {len(climate_uncertainty)} Climate Change categories"
                )
                print(f"✅ Extracted raw simulation data for {len(climate_raw_data)} categories")

    except Exception as e:
        import traceback

        chart_data["success"] = False
        chart_data["error"] = str(e)
        chart_data["debug_info"]["exception"] = traceback.format_exc()
        print(f"Chart data extraction error: {str(e)}")
        print(traceback.format_exc())

    return jsonify(chart_data)


@app.route("/lca_result/<int:result_id>/process_by_category")
@login_required
def get_process_by_category(result_id):

    lca_result = LCAResult.query.get_or_404(result_id)
    excel_file = ExcelFile.query.get(lca_result.excel_file_id)
    project = Project.query.get(excel_file.project_id)

    if project.user_id != current_user.id:
        return jsonify({"success": False, "error": "You do not have permission to view this analysis result!"})

    category_name = request.args.get("category", "")

    print(f"\n{'='*60}")
    print(f"📊 API call: get_process_by_category")
    print(f"📊 Result ID: {result_id}")
    print(f"📊 Requested category: {category_name}")
    print(f"{'='*60}")

    if not category_name:
        return jsonify({"success": False, "error": "Impact category not specified"})

    try:
        details = json.loads(lca_result.analysis_details)
        comprehensive = details.get("comprehensive_results", {})
        contribution = comprehensive.get("contribution_analysis", {})

        print(f"\n📊 contribution_analysis keys in database:")
        print(f"  {list(contribution.keys())}")

        if not contribution:
            return jsonify({"success": False, "error": "No contribution analysis data"})

        all_category_contributions = contribution.get("all_category_contributions", {})

        print(f"\n📊 Categories in all_category_contributions:")
        for cat_name in all_category_contributions.keys():
            cat_data = all_category_contributions[cat_name]
            total_val = (
                sum(p.get("impact_value", 0) for p in cat_data)
                if isinstance(cat_data, list)
                else 0
            )
            print(
                f"  - {cat_name}: {len(cat_data) if isinstance(cat_data, list) else 0} processes, total {total_val:.6e}"
            )

        if category_name in all_category_contributions:
            print(f"\n✅ Found precomputed contribution data for category {category_name}")
            process_contribs = all_category_contributions[category_name]

            print(f"📊 This category contains {len(process_contribs)} process contributions")
            if len(process_contribs) > 0:
                print("📊 First 3 process samples:")
                for i, p in enumerate(process_contribs[:3]):
                    print(
                        f"  {i+1}. {p.get('process_name')}: {p.get('impact_value'):.6e} {p.get('unit')}"
                    )

                category_total = sum(p.get("impact_value", 0) for p in process_contribs)
                print(
                    f"📊 Total of all processes in this category: {category_total:.6f} {process_contribs[0].get('unit', 'kg CO2 eq')}"
                )
        elif "process_contributions" in contribution:

            print(f"\n⚠️ No precomputed data for {category_name}, using default contribution data")
            process_contribs = contribution["process_contributions"]

            if process_contribs and len(process_contribs) > 0:
                default_total = sum(p.get("impact_value", 0) for p in process_contribs)
                print(f"⚠️ Default contribution data total: {default_total:.6f}")
        else:

            print(f"\n⚠️ Category '{category_name}' has no contribution analysis data (impact value may be 0)")
            return jsonify(
                {
                    "success": True,
                    "process_contributions": [],
                    "category_name": category_name,
                    "message": "No process contribution data for this category (impact value is 0 or contribution analysis was not performed)",
                }
            )

        stage_mappings_db = ProcessLifecycleStage.query.filter_by(
            excel_file_id=excel_file.id
        ).all()
        process_stage_map = {
            mapping.process_name: mapping.lifecycle_stage
            for mapping in stage_mappings_db
        }

        from lifecycle_classifier import classify_lifecycle_stage

        stage_name_map = {
            "overall": "Overall Stage",
            "raw_material": "Raw Material Acquisition",
            "production": "Production",
            "transport": "Distribution",
            "use": "Use",
            "disposal": "End of Life",
            "recycling": "Recycling",
        }

        sorted_processes = sorted(
            process_contribs, key=lambda x: abs(x.get("impact_value", 0)), reverse=True
        )
        top_processes = sorted_processes[:10]

        enriched_processes = []
        for proc in top_processes:
            process_name = proc.get("process_name", "Unknown")

            stage_key = process_stage_map.get(process_name)
            if not stage_key:

                stage_key = classify_lifecycle_stage(process_name)

            stage_name = stage_name_map.get(stage_key, "Unclassified")

            enriched_processes.append(
                {
                    "process_name": proc.get("process_name"),
                    "impact_value": proc.get("impact_value", 0),
                    "contribution_percent": proc.get("contribution_percent", 0),
                    "unit": proc.get("unit", "kg CO2 eq"),
                    "lifecycle_stage": stage_name,
                    "lifecycle_stage_key": stage_key,
                }
            )

        result_data = {
            "success": True,
            "process_contributions": enriched_processes,
            "category_name": category_name,
        }

        print(f"\n{'='*60}")
        print(f"✅ Preparing to return data to frontend")
        print(f"✅ Category name: {category_name}")
        print(f"✅ Process count: {len(enriched_processes)}")
        print(f"✅ First 3 processes (with life cycle stages):")
        for proc in enriched_processes[:3]:
            print(
                f"  - {proc.get('process_name')}: {proc.get('impact_value'):.6e} {proc.get('unit')} ({proc.get('lifecycle_stage')})"
            )
        print(f"{'='*60}\n")
        return jsonify(result_data)

    except Exception as e:
        import traceback

        print(f"Failed to get process contribution data: {str(e)}")
        print(traceback.format_exc())
        return jsonify({"success": False, "error": str(e)})


@app.route("/lca_result/<int:result_id>/lifecycle_by_category")
@login_required
def get_lifecycle_by_category(result_id):

    lca_result = LCAResult.query.get_or_404(result_id)
    excel_file = ExcelFile.query.get(lca_result.excel_file_id)
    project = Project.query.get(excel_file.project_id)

    if project.user_id != current_user.id:
        return jsonify({"success": False, "error": "You do not have permission to view this analysis result!"})

    category_name = request.args.get("category", "")

    print(f"\n{'='*60}")
    print(f"📊 API call: get_lifecycle_by_category")
    print(f"📊 Result ID: {result_id}")
    print(f"📊 Requested category: {category_name}")
    print(f"{'='*60}")

    if not category_name:
        return jsonify({"success": False, "error": "Impact category not specified"})

    try:
        details = json.loads(lca_result.analysis_details)
        comprehensive = details.get("comprehensive_results", {})
        contribution = comprehensive.get("contribution_analysis", {})

        print(f"\n📊 contribution_analysis keys in database:")
        print(f"  {list(contribution.keys())}")

        if not contribution:
            return jsonify({"success": False, "error": "No contribution analysis data"})

        all_category_contributions = contribution.get("all_category_contributions", {})

        print(f"\n📊 Categories in all_category_contributions:")
        for cat_name in all_category_contributions.keys():
            cat_data = all_category_contributions[cat_name]
            total_val = (
                sum(p.get("impact_value", 0) for p in cat_data)
                if isinstance(cat_data, list)
                else 0
            )
            print(
                f"  - {cat_name}: {len(cat_data) if isinstance(cat_data, list) else 0} processes, total {total_val:.6e}"
            )

        if category_name in all_category_contributions:
            print(f"\n✅ Found precomputed contribution data for category {category_name}")
            process_contribs = all_category_contributions[category_name]

            print(f"📊 This category contains {len(process_contribs)} process contributions")
            if len(process_contribs) > 0:
                print("📊 First 3 process samples:")
                for i, p in enumerate(process_contribs[:3]):
                    print(
                        f"  {i+1}. {p.get('process_name')}: {p.get('impact_value'):.6e} {p.get('unit')}"
                    )

                category_total = sum(p.get("impact_value", 0) for p in process_contribs)
                print(
                    f"📊 Total of all processes in this category: {category_total:.6f} {process_contribs[0].get('unit', 'kg CO2 eq')}"
                )
        elif "process_contributions" in contribution:

            print(f"\n⚠️ No precomputed data for {category_name}, using default contribution data")
            process_contribs = contribution["process_contributions"]

            if process_contribs and len(process_contribs) > 0:
                default_total = sum(p.get("impact_value", 0) for p in process_contribs)
                print(f"⚠️ Default contribution data total: {default_total:.6f}")
        else:

            print(f"\n⚠️ Category '{category_name}' has no contribution analysis data (impact value may be 0)")
            return jsonify(
                {
                    "success": True,
                    "lifecycle_stages": [],
                    "category_name": category_name,
                    "message": "No life cycle stage data for this category (impact value is 0 or contribution analysis was not performed)",
                }
            )

        stage_mappings_db = ProcessLifecycleStage.query.filter_by(
            excel_file_id=excel_file.id
        ).all()
        process_stage_map = {
            mapping.process_name: mapping.lifecycle_stage
            for mapping in stage_mappings_db
        }

        from lifecycle_classifier import classify_lifecycle_stage

        stage_name_map = {
            "overall": "Overall Stage",
            "raw_material": "Raw Material Acquisition",
            "production": "Production",
            "transport": "Distribution",
            "use": "Use",
            "disposal": "End of Life",
            "recycling": "Recycling",
        }

        lifecycle_aggregated = {}

        for proc in process_contribs:
            process_name = proc.get("process_name", "")
            impact = proc.get("impact_value", 0)

            stage_key = process_stage_map.get(process_name)
            if not stage_key:
                stage_key = classify_lifecycle_stage(process_name)

            stage_name = stage_name_map.get(stage_key, "Unclassified")

            if stage_name not in lifecycle_aggregated:
                lifecycle_aggregated[stage_name] = {"impacts": [], "processes": []}
            lifecycle_aggregated[stage_name]["impacts"].append(impact)
            lifecycle_aggregated[stage_name]["processes"].append(process_name)

        unit = "kg CO2 eq"
        if process_contribs and len(process_contribs) > 0:
            unit = process_contribs[0].get("unit", "kg CO2 eq")

        lifecycle_stages = []
        for stage_name, stage_data in lifecycle_aggregated.items():
            impacts = stage_data["impacts"]
            if impacts:
                total_impact = sum(impacts)
                if total_impact > 1e-15:
                    lifecycle_stages.append(
                        {
                            "stage": stage_name,
                            "value": total_impact,
                            "unit": unit,
                            "process_count": len(impacts),
                            "processes": stage_data["processes"][:5],
                        }
                    )

        print(f"✅ Aggregated {len(lifecycle_stages)} life cycle stages")
        for stage in lifecycle_stages:
            print(f"  - {stage['stage']}: {stage['value']:.6e} {stage['unit']}")

        has_overall_mapping = any(
            m.lifecycle_stage == "overall" for m in stage_mappings_db
        )
        if has_overall_mapping:
            total_all_stages = sum(
                s["value"] for s in lifecycle_stages if s["stage"] != "Overall Stage"
            )
            if total_all_stages > 1e-15:
                lifecycle_stages.insert(
                    0,
                    {
                        "stage": "Overall Stage",
                        "value": total_all_stages,
                        "unit": unit,
                        "process_count": sum(
                            s["process_count"] for s in lifecycle_stages
                        ),
                        "processes": [],
                    },
                )
                print(f"✅ Added Overall Stage: {total_all_stages:.6e} {unit}")

        result_data = {
            "success": True,
            "lifecycle_stages": lifecycle_stages,
            "category_name": category_name,
        }

        print(f"\n{'='*60}")
        print(f"✅ Preparing to return data to frontend")
        print(f"✅ Category name: {category_name}")
        print(f"✅ Stage count: {len(lifecycle_stages)}")
        print(f"✅ Stage details:")
        for stage in lifecycle_stages:
            print(f"  - {stage['stage']}: {stage['value']:.6e} {stage['unit']}")
        total = sum(s["value"] for s in lifecycle_stages)
        print(f"✅ Total: {total:.6e}")
        print(f"{'='*60}\n")
        return jsonify(result_data)

    except Exception as e:
        import traceback

        print(f"Failed to get life cycle data: {str(e)}")
        print(traceback.format_exc())
        return jsonify({"success": False, "error": str(e)})


@app.route("/lca_result/<int:result_id>/debug_raw_data")
@login_required
def debug_raw_lca_data(result_id):

    lca_result = LCAResult.query.get_or_404(result_id)
    excel_file = ExcelFile.query.get(lca_result.excel_file_id)
    project = Project.query.get(excel_file.project_id)

    if project.user_id != current_user.id:
        return jsonify({"success": False, "error": "You do not have permission to view this analysis result!"})

    debug_data = {
        "result_id": lca_result.id,
        "analysis_status": lca_result.analysis_status,
        "has_analysis_details": bool(lca_result.analysis_details),
        "details_length": (
            len(lca_result.analysis_details) if lca_result.analysis_details else 0
        ),
        "flows_count": lca_result.flows_count,
        "processes_count": lca_result.processes_count,
        "product_systems_count": lca_result.product_systems_count,
    }

    if lca_result.analysis_details:
        try:
            parsed = json.loads(lca_result.analysis_details)
            debug_data["parsed_successfully"] = True
            debug_data["top_level_keys"] = list(parsed.keys())

            debug_data["full_data"] = parsed

            if "comprehensive_results" in parsed:
                comp = parsed["comprehensive_results"]
                debug_data["comprehensive_keys"] = list(comp.keys())

                if "impact_analysis" in comp:
                    impact = comp["impact_analysis"]
                    debug_data["impact_analysis_keys"] = list(impact.keys())
                    if "impact_results" in impact:
                        debug_data["impact_results_sample"] = (
                            impact["impact_results"][:3]
                            if isinstance(impact["impact_results"], list)
                            else None
                        )

                if "inventory_results" in comp:
                    inv = comp["inventory_results"]
                    debug_data["inventory_keys"] = list(inv.keys())
                    if "flow_results" in inv:
                        debug_data["flow_results_sample"] = (
                            inv["flow_results"][:3]
                            if isinstance(inv["flow_results"], list)
                            else None
                        )

        except Exception as e:
            debug_data["parsed_successfully"] = False
            debug_data["parse_error"] = str(e)

    return jsonify(debug_data)


@app.route("/lca_system_status")
@login_required
def get_lca_system_status():

    status = lca_service.get_system_status()
    return jsonify(status)


@app.route("/switch_language/<language>")
def switch_language(language):
    """Switch language between Chinese and English"""
    if language in ["zh", "en"]:

        session["language"] = language

        referrer = request.referrer
        if referrer:

            from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

            parsed = urlparse(referrer)
            query_params = parse_qs(parsed.query)

            query_params["lang"] = [language]

            new_query = urlencode(query_params, doseq=True)
            new_url = urlunparse(
                (
                    parsed.scheme,
                    parsed.netloc,
                    parsed.path,
                    parsed.params,
                    new_query,
                    parsed.fragment,
                )
            )
            return redirect(new_url)
        else:

            return redirect(url_for("index", lang=language))

    return redirect(request.referrer or url_for("index"))


@app.route("/project/<string:project_id>/delete", methods=["POST"])
@login_required
def delete_project(project_id):

    project = Project.query.get_or_404(project_id)

    if project.user_id != current_user.id:
        flash("You do not have permission to delete this project!", "error")
        return redirect(url_for("dashboard"))

    try:

        for excel_file in project.excel_files:
            if os.path.exists(excel_file.file_path):
                os.remove(excel_file.file_path)

        LCAData.query.filter_by(project_id=project_id).delete()

        for excel_file in project.excel_files:
            LCAResult.query.filter_by(excel_file_id=excel_file.id).delete()

        ExcelFile.query.filter_by(project_id=project_id).delete()

        AssessmentBoundary.query.filter_by(project_id=project_id).delete()

        ProjectReportInfo.query.filter_by(project_id=project_id).delete()

        db.session.delete(project)
        db.session.commit()

        flash("Project deleted successfully!", "success")
        return redirect(url_for("dashboard"))

    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting project: {str(e)}", "error")
        return redirect(url_for("project_detail", project_id=project_id))


def _delete_project_with_related_data(project):

    for excel_file in project.excel_files:
        if os.path.exists(excel_file.file_path):
            os.remove(excel_file.file_path)

    LCAData.query.filter_by(project_id=project.id).delete()

    for excel_file in project.excel_files:
        LCAResult.query.filter_by(excel_file_id=excel_file.id).delete()

    ExcelFile.query.filter_by(project_id=project.id).delete()
    AssessmentBoundary.query.filter_by(project_id=project.id).delete()
    ProjectReportInfo.query.filter_by(project_id=project.id).delete()
    db.session.delete(project)


@app.route("/projects/batch_delete", methods=["POST"])
@login_required
def batch_delete_projects():

    selected_project_ids = [pid for pid in request.form.getlist("project_ids") if pid]
    if not selected_project_ids:
        flash("Please select the projects to delete first.", "warning")
        return redirect(url_for("dashboard"))

    projects = Project.query.filter(
        Project.id.in_(selected_project_ids), Project.user_id == current_user.id
    ).all()

    if not projects:
        flash("No deletable projects found, or you lack delete permission.", "error")
        return redirect(url_for("dashboard"))

    try:
        for project in projects:
            _delete_project_with_related_data(project)

        db.session.commit()
        flash(f"Successfully deleted {len(projects)} projects!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error during batch project deletion: {str(e)}", "error")

    return redirect(url_for("dashboard"))


@app.route("/project/<string:project_id>/generate_report", methods=["POST"])
@login_required
def generate_report(project_id):

    project = Project.query.get_or_404(project_id)

    if project.user_id != current_user.id:
        return jsonify({"success": False, "error": "You do not have permission to generate a report for this project!"})

    try:

        data = request.get_json() or {}
        openlca_project_name = data.get("openlca_project_name", project.name)
        template_type = data.get("template_type", "gb24067")
        color_scheme = data.get("color_scheme", "default")
        port = data.get(
            "port",
            async_lca_service.ipc_ports[0] if async_lca_service.ipc_ports else 8080,
        )

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        reports_dir = os.path.join(app.root_path, "static", "reports")
        os.makedirs(reports_dir, exist_ok=True)

        template_suffix = {
            "gb24067": "GB24067",
            "simple": "Simple",
            "custom": "Custom",
        }.get(template_type, "General")
        filename = f"LCA_Report_{project.name}_{template_suffix}_{timestamp}.pdf"
        output_path = os.path.join(reports_dir, filename)

        print(f"🔄 Starting report generation: {filename}")
        print(f"   OpenLCA project name: {openlca_project_name}")
        print(f"   Template type: {template_type}")
        print(f"   Color scheme: {color_scheme}")
        print(f"   Port: {port}")

        result = report_service.generate_report(
            project_name=openlca_project_name,
            output_path=output_path,
            port=port,
            template_type=template_type,
            color_scheme=color_scheme,
        )

        if result["success"]:

            download_url = url_for(
                "download_report",
                project_id=project_id,
                filename=filename,
                _external=False,
            )

            return jsonify(
                {
                    "success": True,
                    "message": "Report generated successfully!",
                    "download_url": download_url,
                    "filename": filename,
                }
            )
        else:
            return jsonify(
                {"success": False, "error": result.get("error", "Report generation failed")}
            )

    except Exception as e:
        print(f"❌ Error generating report: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": f"Error generating report: {str(e)}"})


@app.route("/project/<string:project_id>/download_report/<filename>")
@login_required
def download_report(project_id, filename):

    project = Project.query.get_or_404(project_id)

    if project.user_id != current_user.id:
        flash("You do not have permission to download this report!", "error")
        return redirect(url_for("project_detail", project_id=project_id))

    try:
        reports_dir = os.path.join(app.root_path, "static", "reports")
        file_path = os.path.join(reports_dir, filename)

        if os.path.exists(file_path):

            if filename.endswith(".pdf"):
                mimetype = "application/pdf"
            elif filename.endswith(".md"):
                mimetype = "text/markdown"
            else:
                mimetype = "application/octet-stream"

            return send_file(
                file_path, as_attachment=True, download_name=filename, mimetype=mimetype
            )
        else:
            flash("Report file does not exist!", "error")
            return redirect(url_for("project_detail", project_id=project_id))

    except Exception as e:
        flash(f"Error downloading report: {str(e)}", "error")
        return redirect(url_for("project_detail", project_id=project_id))


@app.route("/project/<string:project_id>/list_reports")
@login_required
def list_reports(project_id):

    project = Project.query.get_or_404(project_id)

    if project.user_id != current_user.id:
        return jsonify({"success": False, "error": "You do not have permission to view reports for this project!"})

    try:
        reports_dir = os.path.join(app.root_path, "static", "reports")

        if not os.path.exists(reports_dir):
            return jsonify({"success": True, "reports": []})

        project_reports = []
        for filename in os.listdir(reports_dir):
            if filename.endswith(".pdf") and project.name in filename:
                file_path = os.path.join(reports_dir, filename)
                file_stat = os.stat(file_path)

                project_reports.append(
                    {
                        "filename": filename,
                        "size": file_stat.st_size,
                        "created_time": datetime.fromtimestamp(
                            file_stat.st_ctime
                        ).strftime("%Y-%m-%d %H:%M:%S"),
                        "download_url": url_for(
                            "download_report", project_id=project_id, filename=filename
                        ),
                    }
                )

        project_reports.sort(key=lambda x: x["created_time"], reverse=True)

        return jsonify({"success": True, "reports": project_reports})

    except Exception as e:
        return jsonify({"success": False, "error": f"Error fetching report list: {str(e)}"})


@app.route("/project/<string:project_id>/edit_report_info", methods=["GET", "POST"])
@login_required
def edit_report_info_page(project_id):

    project = Project.query.filter_by(id=project_id, user_id=current_user.id).first()

    if project.user_id != current_user.id:
        flash("You do not have permission to access this project!", "error")
        return redirect(url_for("dashboard"))

    return render_template("edit_report_info.html", project=project)


@app.route("/project/<string:project_id>/report_info", methods=["GET"])
@login_required
def get_report_info(project_id):

    project = Project.query.get_or_404(project_id)

    if project.user_id != current_user.id:
        return jsonify({"success": False, "error": "You do not have permission to access this project info!"}), 403

    try:

        report_info = ProjectReportInfo.query.filter_by(project_id=project_id).first()

        if not report_info:

            report_info = ProjectReportInfo(
                project_id=project_id,
                product_name=project.name,
                time_scale=f"Year {datetime.now().year}",
            )
            db.session.add(report_info)
            db.session.commit()

        info_dict = {
            "product_name": report_info.product_name,
            "product_model": report_info.product_model,
            "producer_name": report_info.producer_name,
            "report_no": report_info.report_no,
            "address": report_info.address,
            "legal_representative": report_info.legal_representative,
            "contact_person": report_info.contact_person,
            "contact_phone": report_info.contact_phone,
            "contact_email": report_info.contact_email,
            "product_function": report_info.product_function,
            "standard_used": report_info.standard_used,
            "quantitative_purpose": report_info.quantitative_purpose,
            "functional_unit": report_info.functional_unit,
            "system_boundary_description": report_info.system_boundary_description,
            "system_boundary_stages": report_info.system_boundary_stages,
            "cutoff_criteria": report_info.cutoff_criteria,
            "time_scale": report_info.time_scale,
            "primary_data_source": report_info.primary_data_source,
            "secondary_data_source": report_info.secondary_data_source,
            "allocation_basis": report_info.allocation_basis,
            "allocation_procedure": report_info.allocation_procedure,
            "specific_allocations": report_info.specific_allocations,
            "data_quality_notes": report_info.data_quality_notes,
            "impact_type_description": report_info.impact_type_description,
            "assumptions_limitations": report_info.assumptions_limitations,
            "improvement_suggestions": report_info.improvement_suggestions,
            "enable_ai_suggestions": report_info.enable_ai_suggestions,
            "report_language": report_info.report_language,
        }

        return jsonify({"success": True, "data": info_dict})

    except Exception as e:
        print(f"❌ Error fetching report info: {e}")
        traceback.print_exc()
        return (
            jsonify({"success": False, "error": f"Error fetching report info: {str(e)}"}),
            500,
        )


@app.route("/project/<string:project_id>/report_info", methods=["POST"])
@login_required
def update_report_info(project_id):

    project = Project.query.get_or_404(project_id)

    if project.user_id != current_user.id:
        return jsonify({"success": False, "error": "You do not have permission to modify this project info!"}), 403

    try:
        data = request.get_json() or {}

        report_info = ProjectReportInfo.query.filter_by(project_id=project_id).first()

        if not report_info:
            report_info = ProjectReportInfo(project_id=project_id)
            db.session.add(report_info)

        updatable_fields = [
            "product_name",
            "product_model",
            "producer_name",
            "report_no",
            "address",
            "legal_representative",
            "contact_person",
            "contact_phone",
            "contact_email",
            "product_function",
            "standard_used",
            "quantitative_purpose",
            "functional_unit",
            "system_boundary_description",
            "system_boundary_stages",
            "cutoff_criteria",
            "time_scale",
            "primary_data_source",
            "secondary_data_source",
            "allocation_basis",
            "allocation_procedure",
            "specific_allocations",
            "data_quality_notes",
            "impact_type_description",
            "assumptions_limitations",
            "improvement_suggestions",
            "enable_ai_suggestions",
            "report_language",
        ]

        for field in updatable_fields:
            if field in data:
                setattr(report_info, field, data[field])

        report_info.updated_at = datetime.now()
        db.session.commit()

        return jsonify({"success": True, "message": "Report info updated"})

    except Exception as e:
        db.session.rollback()
        print(f"❌ Error updating report info: {e}")
        traceback.print_exc()
        return (
            jsonify({"success": False, "error": f"Error updating report info: {str(e)}"}),
            500,
        )


@app.route("/project/<string:project_id>/generate_markdown_report", methods=["POST"])
@login_required
def generate_markdown_report(project_id):
    """Generate bilingual PDF LCA reports (Chinese and English versions)"""
    project = Project.query.get_or_404(project_id)

    if project.user_id != current_user.id:
        return jsonify({"success": False, "error": "You do not have permission to generate a report for this project!"}), 403

    try:

        data = request.get_json() or {}

        language = data.get("language", "both")

        report_format = "pdf"

        report_info = ProjectReportInfo.query.filter_by(project_id=project_id).first()

        if not report_info:
            return jsonify({"success": False, "error": "Please fill in project report info first!"}), 400

        result_id = data.get("result_id")

        if result_id:

            print(f"📍 Using user-specified LCA result: result_id={result_id}")
            lca_result = LCAResult.query.get(result_id)

            if not lca_result:
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": f"LCA analysis result with ID {result_id} not found!",
                        }
                    ),
                    404,
                )

            excel_file = ExcelFile.query.get(lca_result.excel_file_id)
            if not excel_file or excel_file.project_id != project_id:
                return (
                    jsonify({"success": False, "error": "This LCA result does not belong to the current project!"}),
                    403,
                )

            if lca_result.analysis_status != "completed":
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": f"This LCA analysis is not complete yet (status: {lca_result.analysis_status})!",
                        }
                    ),
                    400,
                )
        else:

            print(f"📍 Automatically selecting latest completed LCA result")
            excel_files = ExcelFile.query.filter_by(
                project_id=project_id, is_deleted=False
            ).all()
            if not excel_files:
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "No Excel files in the project; please upload a file and run LCA analysis first!",
                        }
                    ),
                    400,
                )

            excel_file_ids = [f.id for f in excel_files]
            lca_result = (
                LCAResult.query.filter(
                    LCAResult.excel_file_id.in_(excel_file_ids),
                    LCAResult.analysis_status == "completed",
                )
                .order_by(LCAResult.end_time.desc())
                .first()
            )

        if not lca_result or not lca_result.analysis_details:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "No completed LCA analysis results found; please run LCA analysis first!",
                    }
                ),
                400,
            )

        try:
            lca_details = json.loads(lca_result.analysis_details)
        except:
            return jsonify({"success": False, "error": "LCA analysis result format error!"}), 400

        print(f"🔍 LCA result detail keys: {list(lca_details.keys())}")

        comprehensive_results = lca_details.get("comprehensive_results")
        if not comprehensive_results:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Detailed LCA analysis result data not found! Please ensure LCA analysis ran successfully.",
                    }
                ),
                400,
            )

        print(
            f"🔍 comprehensive_results keys: {list(comprehensive_results.keys()) if isinstance(comprehensive_results, dict) else 'Not a dict'}"
        )

        impact_analysis = comprehensive_results.get("impact_analysis", {})
        if not impact_analysis:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Impact assessment data not found! Please ensure LCA analysis includes the impact assessment step.",
                    }
                ),
                400,
            )

        print(
            f"🔍 impact_analysis keys: {list(impact_analysis.keys()) if isinstance(impact_analysis, dict) else 'Not a dict'}"
        )

        print("\n" + "=" * 80)
        print("🎯 Report data extraction (using the same logic as web visualization)")
        print("=" * 80)

        contribution = comprehensive_results.get("contribution_analysis", {})
        all_category_contributions = contribution.get("all_category_contributions", {})

        if not all_category_contributions:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "all_category_contributions data not found! Please re-run LCA analysis.",
                    }
                ),
                400,
            )

        print(f"\n📊 Available impact categories:")
        for cat_name in all_category_contributions.keys():
            cat_data = all_category_contributions[cat_name]
            if isinstance(cat_data, list) and len(cat_data) > 0:
                cat_total = sum(p.get("impact_value", 0) for p in cat_data)
                cat_unit = cat_data[0].get("unit", "") if cat_data else ""
                print(
                    f"  - {cat_name}: {len(cat_data)} processes, total {cat_total:.6f} {cat_unit}"
                )

        def find_best_climate_category(category_names, label=""):

            sub_keywords = [
                "biogenic",
                "fossil",
                "land use",
                "land-use",
                "short cycle",
                "short-cycle",
                "albedo",
                "contrail",
            ]

            def is_sub(name_lower):
                return any(kw in name_lower for kw in sub_keywords)

            cat_lower_map = {n.lower(): n for n in category_names}

            def best_hit(key_fragments, exclude_sub=True, exclude_no_lt=False):

                hits = []
                for cl, co in cat_lower_map.items():
                    if not all(frag in cl for frag in key_fragments):
                        continue
                    if exclude_sub and is_sub(cl):
                        continue
                    if exclude_no_lt and "no lt" in cl:
                        continue
                    hits.append((len(cl), co))
                if hits:
                    return sorted(hits)[0][1]
                return None

            for frags in (
                ["climate change", "gwp100"],
                ["climate change", "gwp 100"],
                ["climate change", "global warming potential"],
            ):
                m = best_hit(frags, exclude_sub=True, exclude_no_lt=True)
                if m:
                    print(f"  ✅ [{label}] P1-IPCC GWP100: {m}")
                    return m

            for frags in (
                ["climate change", "gwp100"],
                ["climate change", "gwp 100"],
                ["climate change", "global warming potential"],
            ):
                m = best_hit(frags, exclude_sub=True, exclude_no_lt=False)
                if m:
                    print(f"  ✅ [{label}] P2-IPCC GWP100 (including noLT): {m}")
                    return m

            m = best_hit(["global warming"], exclude_sub=True, exclude_no_lt=True)
            if m:
                print(f"  ✅ [{label}] P3-global warming (excluding noLT): {m}")
                return m
            m = best_hit(["global warming"], exclude_sub=True, exclude_no_lt=False)
            if m:
                print(f"  ✅ [{label}] P3b-global warming (including noLT): {m}")
                return m

            m = best_hit(["climate change"], exclude_sub=True, exclude_no_lt=True)
            if m:
                print(f"  ✅ [{label}] P4-climate change total (excluding noLT): {m}")
                return m

            m = best_hit(["climate change"], exclude_sub=True, exclude_no_lt=False)
            if m:
                print(f"  ✅ [{label}] P5-climate change total (including noLT): {m}")
                return m

            fallback = [
                (len(cl), co)
                for cl, co in cat_lower_map.items()
                if "climate change" in cl or "global warming" in cl
            ]
            if fallback:
                co = sorted(fallback)[0][1]
                print(f"  ✅ [{label}] P6-fallback shortest name: {co}")
                return co

            print(f"  ❌ [{label}] no match, available categories: {list(category_names)[:10]}")
            return None

        target_category_name = find_best_climate_category(
            list(all_category_contributions.keys()), label="main report"
        )
        process_contribs_for_report = None
        total_carbon_footprint = 0
        unit = "kg CO2-Eq"

        if target_category_name:
            process_contribs_for_report = all_category_contributions[
                target_category_name
            ]

            if (
                isinstance(process_contribs_for_report, list)
                and len(process_contribs_for_report) > 0
            ):
                total_carbon_footprint = sum(
                    p.get("impact_value", 0) for p in process_contribs_for_report
                )
                unit = process_contribs_for_report[0].get("unit", "kg CO2-Eq")

                print(f"\n✅ Found target category: {target_category_name}")
                print(f"   Process count: {len(process_contribs_for_report)}")
                print(
                    f"   ⭐ Total carbon footprint (sum of all processes): {total_carbon_footprint:.6f} {unit}"
                )
                print(f"   First 3 process samples:")
                for i, p in enumerate(process_contribs_for_report[:3]):
                    pname = p.get("process_name", "Unknown")
                    pval = p.get("impact_value", 0)
                    punit = p.get("unit", "")
                    print(f"      {i+1}. {pname}: {pval:.6e} {punit}")

        if not target_category_name:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": (
                            "Climate change / Global warming impact category not found!\n\n"
                            "Supported impact assessment methods include: IPCC 2021, EF 3.1/3.0, ReCiPe, CML, TRACI, ILCD, etc.\n\n"
                            f'Currently available categories: {", ".join(list(all_category_contributions.keys())[:15])}'
                        ),
                    }
                ),
                400,
            )

        if total_carbon_footprint == 0:
            print("⚠️ Total carbon footprint is 0, possible reasons:")
            print("   1. Excel flows were not matched to characterization factors of the selected method")
            print("   2. Issues in product system construction")
            print("   Will continue generating the report with carbon footprint shown as 0")

        print(f"\n✅ Data extraction succeeded:")
        print(f"   Impact category: {target_category_name}")
        print(f"   Total carbon footprint: {total_carbon_footprint:.6f} {unit}")
        print(
            f"   Data source: all_category_contributions['{target_category_name}'] (identical to web page)"
        )
        print(f"   LCA Result ID: {lca_result.id}")

        if total_carbon_footprint == 0:
            print("⚠️ Warning: Total climate change impact is 0, which may indicate:")
            print("   1. Flows in Excel file have no carbon emission data")
            print(
                "   2. Flows do not match characterization factors in the impact method"
            )
            print("   3. Product system construction has issues")
            print("   Report will be generated, but carbon footprint is 0")

        print("\n" + "=" * 80)
        print("🔄 Generating report data structure (using the same logic as web visualization)")
        print("=" * 80)

        lca_results_for_report = {
            "total_carbon_footprint": total_carbon_footprint,
            "unit": unit,
            "impact_category": target_category_name,
            "stages": {},
            "process_contributions": [],
            "uncertainty_analysis": {},
        }

        process_contribs = process_contribs_for_report

        if process_contribs:

            if isinstance(process_contribs, list) and len(process_contribs) > 0:
                print(
                    f"📊 Found {len(process_contribs)} process contributions, using same logic as visualization"
                )

                stage_mappings_db = ProcessLifecycleStage.query.filter_by(
                    excel_file_id=lca_result.excel_file_id
                ).all()
                process_stage_map = {
                    mapping.process_name: mapping.lifecycle_stage
                    for mapping in stage_mappings_db
                }
                print(
                    f"   📋 Found {len(process_stage_map)} process-stage mappings in database"
                )

                from lifecycle_classifier import classify_lifecycle_stage

                stage_key_to_report_key = {
                    "raw_material": "raw_material",
                    "production": "production",
                    "transport": "distribution",
                    "use": "use",
                    "disposal": "end_of_life",
                    "recycling": "end_of_life",
                    "overall": "production",
                }

                lifecycle_aggregated = {}
                total_impact_from_processes = 0

                for proc in process_contribs:
                    process_name = proc.get("process_name", "")
                    impact = proc.get("impact_value", 0)
                    total_impact_from_processes += impact

                    stage_key = process_stage_map.get(process_name)
                    if not stage_key:
                        stage_key = classify_lifecycle_stage(process_name)

                    report_key = stage_key_to_report_key.get(stage_key, "production")

                    if report_key not in lifecycle_aggregated:
                        lifecycle_aggregated[report_key] = 0
                    lifecycle_aggregated[report_key] += impact

                print(f"   ✅ Aggregated {len(process_contribs)} processes")
                print(
                    f"   📊 Total impact from processes: {total_impact_from_processes:.2f} kg CO2 eq"
                )

                stage_sum = 0
                for stage_name in [
                    "raw_material",
                    "production",
                    "distribution",
                    "use",
                    "end_of_life",
                ]:
                    value = lifecycle_aggregated.get(stage_name, 0)
                    percentage = (
                        (value / total_carbon_footprint * 100)
                        if total_carbon_footprint > 0
                        else 0
                    )
                    lca_results_for_report["stages"][stage_name] = {
                        "value": value,
                        "percentage": percentage,
                    }
                    stage_sum += value
                    if value > 0:
                        print(
                            f"   - {stage_name}: {value:.2f} kg CO2 eq ({percentage:.1f}%)"
                        )

                print(f"\n✅ Report stages built:")
                print(f"   Stages sum: {stage_sum:.2f} kg CO2 eq")
                print(f"   Total CF:   {total_carbon_footprint:.2f} kg CO2 eq")
                print(
                    f"   Difference: {abs(stage_sum - total_carbon_footprint):.2f} kg CO2 eq"
                )

                difference_ratio = (
                    abs(stage_sum - total_carbon_footprint) / total_carbon_footprint
                    if total_carbon_footprint > 0
                    else 0
                )
                if difference_ratio > 0.1:
                    print(
                        f"\n⚠️ Warning: difference between stages sum and total_carbon_footprint is too large ({difference_ratio:.1%})"
                    )
                    print(
                        f"   Using actual stages sum ({stage_sum:.2f}) as the report total carbon footprint"
                    )

                    for stage_name in [
                        "raw_material",
                        "production",
                        "distribution",
                        "use",
                        "end_of_life",
                    ]:
                        value = lifecycle_aggregated.get(stage_name, 0)
                        percentage = (value / stage_sum * 100) if stage_sum > 0 else 0
                        lca_results_for_report["stages"][stage_name] = {
                            "value": value,
                            "percentage": percentage,
                        }

                    lca_results_for_report["total_carbon_footprint"] = stage_sum
                    print(f"   ✅ Updated report total carbon footprint to: {stage_sum:.2f} kg CO2 eq")

        if not lca_results_for_report["stages"]:
            print("⚠️ Warning: No process contribution data found")
            print(
                "📋 Creating default stage allocation: all emissions allocated to 'production' stage"
            )

            lca_results_for_report["stages"] = {
                "raw_material": {"value": 0, "percentage": 0},
                "production": {
                    "value": total_carbon_footprint,
                    "percentage": 100.0 if total_carbon_footprint > 0 else 0,
                },
                "distribution": {"value": 0, "percentage": 0},
                "use": {"value": 0, "percentage": 0},
                "end_of_life": {"value": 0, "percentage": 0},
            }

            print(
                f"✅ Default stage allocation completed (production stage: {total_carbon_footprint})"
            )

        print("\n🔄 Extracting main process contribution data...")
        if (
            process_contribs
            and isinstance(process_contribs, list)
            and len(process_contribs) > 0
        ):

            stage_mappings_db = ProcessLifecycleStage.query.filter_by(
                excel_file_id=lca_result.excel_file_id
            ).all()
            process_stage_map = {
                mapping.process_name: mapping.lifecycle_stage
                for mapping in stage_mappings_db
            }

            from lifecycle_classifier import classify_lifecycle_stage

            sorted_contribs = sorted(
                process_contribs, key=lambda x: x.get("impact_value", 0), reverse=True
            )

            for proc in sorted_contribs[:15]:
                process_name = proc.get("process_name", "")
                impact_value = proc.get("impact_value", 0)
                contribution_percent = proc.get("contribution_percent", 0)

                stage_key = process_stage_map.get(process_name)
                if not stage_key:
                    stage_key = classify_lifecycle_stage(process_name)

                stage_name_map = {
                    "raw_material": "Raw Material Acquisition",
                    "production": "Production",
                    "transport": "Distribution",
                    "use": "Use",
                    "disposal": "End of Life",
                    "recycling": "Recycling",
                    "overall": "Overall Stage",
                }

                lca_results_for_report["process_contributions"].append(
                    {
                        "name": process_name,
                        "value": impact_value,
                        "percentage": contribution_percent,
                        "lifecycle_stage": stage_name_map.get(stage_key, stage_key),
                        "lifecycle_stage_key": stage_key,
                    }
                )

            print(
                f"   ✅ Extracted {len(lca_results_for_report['process_contributions'])} main process contributions"
            )

        print("\n🔄 Extracting uncertainty analysis data...")
        uncertainty = comprehensive_results.get("uncertainty_analysis", {})
        if uncertainty:
            statistics = uncertainty.get("statistics", {})
            if statistics:
                print(f"   📊 Available uncertainty categories:")
                for cat_name in statistics.keys():
                    print(f"      - {cat_name}")

                target_category = find_best_climate_category(
                    list(statistics.keys()), label="uncertainty"
                )
                climate_uncertainty = {}

                if target_category:
                    stat_data = statistics.get(target_category, {})
                    print(f"\n   🔍 Checking category: {target_category}")
                    print(f"      Data fields: {list(stat_data.keys())}")
                    print(f"      mean: {stat_data.get('mean')}")
                    print(f"      std: {stat_data.get('std')}")
                    print(f"      std_dev: {stat_data.get('std_dev')}")
                    print(f"      p5: {stat_data.get('p5')}")
                    print(f"      p95: {stat_data.get('p95')}")
                    print(f"      percentile_5: {stat_data.get('percentile_5')}")
                    print(f"      percentile_95: {stat_data.get('percentile_95')}")
                    print(f"      median: {stat_data.get('median')}")
                    print(f"      cv: {stat_data.get('cv')}")

                    climate_uncertainty[target_category] = {
                        "mean": stat_data.get("mean", 0),
                        "std_dev": stat_data.get("std", 0),
                        "cv": stat_data.get("cv", 0),
                        "median": stat_data.get("median", 0),
                        "percentile_5": stat_data.get("p5", 0),
                        "percentile_95": stat_data.get("p95", 0),
                    }
                    print(f"   ✅ Using uncertainty category: {target_category}")
                    print(f"      Extracted data: {climate_uncertainty[target_category]}")
                else:
                    print(f"   ⚠️ No suitable climate change category found for uncertainty analysis")
                    print(f"      Available categories: {', '.join(statistics.keys())}")

                if climate_uncertainty:
                    lca_results_for_report["uncertainty_analysis"] = {
                        "statistics": climate_uncertainty,
                        "iterations": uncertainty.get("iterations", 0),
                        "impact_method": uncertainty.get("impact_method", ""),
                    }
                    print(
                        f"\n   ✅ Extracted uncertainty analysis results for {len(climate_uncertainty)} Climate Change categories"
                    )
                    print(f"   📊 Iterations: {uncertainty.get('iterations', 0)}")

                    for cat_name, cat_data in climate_uncertainty.items():
                        print(f"\n   📋 Final stored data - {cat_name}:")
                        print(f"      mean: {cat_data.get('mean')}")
                        print(f"      std_dev: {cat_data.get('std_dev')}")
                        print(f"      median: {cat_data.get('median')}")
                        print(f"      percentile_5: {cat_data.get('percentile_5')}")
                        print(f"      percentile_95: {cat_data.get('percentile_95')}")
                        print(f"      cv: {cat_data.get('cv')}")
                else:
                    print(f"\n   ⚠️ No matching uncertainty categories found")
            else:
                print(f"   ⚠️ statistics is empty")
        else:
            print(f"   ⚠️ uncertainty_analysis does not exist")

        print(f"\n📦 uncertainty_analysis passed to report generator:")
        print(f"   {lca_results_for_report.get('uncertainty_analysis', 'None')}")

        project_info = {"name": project.name, "description": project.description}

        report_info_dict = {
            "product_name": report_info.product_name,
            "product_model": report_info.product_model,
            "producer_name": report_info.producer_name,
            "report_no": report_info.report_no,
            "address": report_info.address,
            "legal_representative": report_info.legal_representative,
            "contact_person": report_info.contact_person,
            "contact_phone": report_info.contact_phone,
            "contact_email": report_info.contact_email,
            "product_function": report_info.product_function,
            "standard_used": report_info.standard_used,
            "quantitative_purpose": report_info.quantitative_purpose,
            "functional_unit": report_info.functional_unit,
            "system_boundary_description": report_info.system_boundary_description,
            "cutoff_criteria": report_info.cutoff_criteria,
            "time_scale": report_info.time_scale,
            "primary_data_source": report_info.primary_data_source,
            "secondary_data_source": report_info.secondary_data_source,
            "allocation_basis": report_info.allocation_basis,
            "allocation_procedure": report_info.allocation_procedure,
            "specific_allocations": report_info.specific_allocations,
            "data_quality_notes": report_info.data_quality_notes,
            "impact_type_description": report_info.impact_type_description,
            "assumptions_limitations": report_info.assumptions_limitations,
            "improvement_suggestions": report_info.improvement_suggestions,
        }

        reports_dir = os.path.join(app.root_path, "static", "reports")
        os.makedirs(reports_dir, exist_ok=True)

        generator = ProfessionalPDFReportGenerator(
            project_info=project_info,
            report_info=report_info_dict,
            lca_results=lca_results_for_report,
            output_dir=reports_dir,
        )

        lang = language if language in ["zh", "en"] else "en"
        print(f"📄 Generating PDF report in {lang} language...")

        filepath, success = generator.generate_pdf_report(lang)
        if not success or not filepath:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "PDF report generation failed, please check server logs",
                    }
                ),
                500,
            )

        filename = os.path.basename(filepath)
        lang_label = "English" if lang == "zh" else "English"

        return jsonify(
            {
                "success": True,
                "message": f"{lang_label} PDF report generated successfully!",
                "filename": filename,
                "download_url": url_for(
                    "download_report", project_id=project_id, filename=filename
                ),
            }
        )

    except Exception as e:
        print(f"❌ Error generating Markdown report: {e}")
        traceback.print_exc()
        return (
            jsonify({"success": False, "error": f"Error generating report: {str(e)}"}),
            500,
        )


@app.route("/project/<string:project_id>/flows_units")
@login_required
def view_flows_units(project_id):

    project = Project.query.filter_by(id=project_id, user_id=current_user.id).first()
    if not project:
        flash("Project does not exist", "error")
        return redirect(url_for("dashboard"))

    try:

        latest_excel = (
            ExcelFile.query.filter_by(project_id=project_id)
            .order_by(ExcelFile.upload_time.desc())
            .first()
        )

        if not latest_excel:
            flash("This project has no uploaded Excel files yet", "warning")
            return redirect(url_for("project_detail", project_id=project_id))

        excel_path = latest_excel.file_path

        import openpyxl

        workbook = openpyxl.load_workbook(excel_path)

        flows_data = []
        for sheet_name in workbook.sheetnames:
            if sheet_name.lower() in ["sheet2", "empty"]:
                continue

            df = pd.read_excel(excel_path, sheet_name=sheet_name, header=None)

            for row_idx in range(df.shape[0]):
                row = df.iloc[row_idx]
                row_str = " ".join([str(val) for val in row if pd.notna(val)]).lower()

                if "flow" in row_str and "unit" in row_str:

                    flow_col = None
                    unit_col = None
                    io_col = None

                    for col_idx in range(len(row)):
                        cell_value = (
                            str(row.iloc[col_idx]).lower()
                            if pd.notna(row.iloc[col_idx])
                            else ""
                        )
                        if "flow" in cell_value and not flow_col:
                            flow_col = col_idx
                        if "unit" in cell_value and not unit_col:
                            unit_col = col_idx
                        if "input" in cell_value or "output" in cell_value:
                            io_col = col_idx

                    if flow_col is not None and unit_col is not None:
                        for data_row_idx in range(row_idx + 1, df.shape[0]):
                            data_row = df.iloc[data_row_idx]
                            flow_name = (
                                data_row.iloc[flow_col]
                                if pd.notna(data_row.iloc[flow_col])
                                else ""
                            )
                            unit_name = (
                                data_row.iloc[unit_col]
                                if pd.notna(data_row.iloc[unit_col])
                                else ""
                            )

                            if flow_name and str(flow_name).strip():
                                io_type = ""
                                if io_col is not None:
                                    io_type = (
                                        str(data_row.iloc[io_col])
                                        if pd.notna(data_row.iloc[io_col])
                                        else ""
                                    )

                                flows_data.append(
                                    {
                                        "sheet": sheet_name,
                                        "flow_name": str(flow_name).strip(),
                                        "unit": str(unit_name).strip(),
                                        "io_type": io_type.strip(),
                                    }
                                )
                    break

        available_units = {}
        try:
            if lca_service.connected:

                from lca_automation.lca_modeler import UniversalLCAModeler

                modeler = UniversalLCAModeler(lca_service.client)
                available_units = modeler.list_all_unit_groups()
        except Exception as e:
            print(f"⚠️ Unable to get unit group info: {e}")

        return render_template(
            "flows_units.html",
            project=project,
            flows_data=flows_data,
            available_units=available_units,
        )

    except Exception as e:
        print(f"❌ Error viewing flows and units: {e}")
        traceback.print_exc()
        flash(f"Error viewing flows and units: {str(e)}", "error")
        return redirect(url_for("project_detail", project_id=project_id))


@app.route("/project/<string:project_id>/update_flow_unit", methods=["POST"])
@login_required
def update_flow_unit(project_id):

    project = Project.query.filter_by(id=project_id, user_id=current_user.id).first()
    if not project:
        return jsonify({"success": False, "error": "Project does not exist"}), 404

    try:
        data = request.get_json()
        sheet_name = data.get("sheet")
        flow_name = data.get("flow_name")
        old_unit = data.get("old_unit")
        new_unit = data.get("new_unit")

        if not all([sheet_name, flow_name, new_unit]):
            return jsonify({"success": False, "error": "Missing required parameters"}), 400

        latest_excel = (
            ExcelFile.query.filter_by(project_id=project_id)
            .order_by(ExcelFile.upload_time.desc())
            .first()
        )

        if not latest_excel:
            return jsonify({"success": False, "error": "This project has no Excel files"}), 404

        excel_path = latest_excel.file_path

        import openpyxl

        workbook = openpyxl.load_workbook(excel_path)

        if sheet_name not in workbook.sheetnames:
            return (
                jsonify({"success": False, "error": f"Sheet {sheet_name} does not exist"}),
                404,
            )

        sheet = workbook[sheet_name]

        flow_col = None
        unit_col = None
        header_row = None

        for row_idx, row in enumerate(sheet.iter_rows(min_row=1, max_row=50), start=1):
            for col_idx, cell in enumerate(row, start=1):
                if cell.value and "flow" in str(cell.value).lower():
                    flow_col = col_idx
                    header_row = row_idx
                if cell.value and "unit" in str(cell.value).lower():
                    unit_col = col_idx

            if flow_col and unit_col:
                break

        if not (flow_col and unit_col):
            return jsonify({"success": False, "error": "Could not find Flow or Unit columns"}), 400

        updated = False
        for row_idx in range(header_row + 1, sheet.max_row + 1):
            cell_flow = sheet.cell(row=row_idx, column=flow_col)
            if cell_flow.value and str(cell_flow.value).strip() == flow_name:
                cell_unit = sheet.cell(row=row_idx, column=unit_col)
                cell_unit.value = new_unit
                updated = True
                print(
                    f"✅ Updated unit for '{flow_name}' from '{old_unit}' to '{new_unit}' in sheet '{sheet_name}'"
                )

        if not updated:
            return jsonify({"success": False, "error": f'Flow "{flow_name}" not found'}), 404

        workbook.save(excel_path)
        workbook.close()

        return jsonify(
            {
                "success": True,
                "message": f'Successfully updated unit of flow "{flow_name}" from "{old_unit}" to "{new_unit}"',
            }
        )

    except Exception as e:
        print(f"❌ Error updating flow unit: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    app.run(debug=True, host="0.0.0.0", port=8087)
