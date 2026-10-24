import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
    jsonify,
)
from werkzeug.security import generate_password_hash, check_password_hash
from .models import db, User, Report, Result
from .extract import extract_text, parse_results
from .explain import explain, MODE, DISCLAIMER
bp = Blueprint("main", __name__)
# Supported upload types and basic file signatures.

SIGS = {
    "pdf": (b"%PDF",),
    "png": (b"\x89PNG\r\n\x1a\n",),
    "jpg": (b"\xff\xd8\xff",),
    "jpeg": (b"\xff\xd8\xff",),
    "tif": (b"II*\x00", b"MM\x00*"),
    "tiff": (b"II*\x00", b"MM\x00*"),
    "webp": (b"RIFF",),
}

MAX_UPLOAD_SIZE = 15 * 1024 * 1024

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

FEATURES = [
    ("Registration, login, sessions", "Available",
     "Hashed passwords, CSRF protection, 2-hour sessions."),
    ("Report upload (PDF, PNG, JPG)", "Available",
     "Validated by extension, file signature, and size."),
    ("Lab value extraction from text PDFs", "Available",
     "Extracts recognizable laboratory results."),
    ("OCR for scans and images", "Requires Configuration",
     "Needs Tesseract installed."),
    ("Educational explanations", "Available",
     "Provides explanations for educational purposes."),
    ("Report history, search, delete", "Available",
     "Filter by name and status."),
    ("Summary export", "Available",
     "Plain-text download with disclaimer."),
    ("External AI provider", "Requires Configuration",
     "AI explanations depend on provider configuration."),
    ("Historical trend charts", "Available",
     "Charts repeated lab tests with matching units across reports."),
    ("Report comparison", "In Development",
     "Needs unit matching rules."),
    ("Health insights", "In Development",
     "Will derive from saved results."),
    ("AI health assistant", "Coming Soon",
     "Availability depends on AI provider configuration."),
    ("Medical glossary", "Coming Soon", "Not built yet."),
    ("Reminders", "Coming Soon", "No notification delivery exists."),
    ("Multilingual and voice explanations", "Coming Soon",
     "Not built yet."),
    ("Family profiles and sharing", "Coming Soon",
     "Requires consent and access-control design."),
    ("Password reset by email", "Requires Configuration",
     "No email service is configured."),
]

# -------------------- Authentication helpers --------------------

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "uid" not in session:
            flash("Please sign in to continue.", "warning")
            return redirect(url_for("main.login"))
        return f(*args, **kwargs)
    return wrapper

def start_session(user):
    token = session.get("csrf")
    session.clear()
    if token:
        session["csrf"] = token
    session["uid"] = user.id
    session.permanent = True

def me():
    if "uid" not in session:
        return None
    return db.session.get(User, session["uid"])

def own_report(rid):
    report = db.session.get(Report, rid)
    if not report or report.user_id != session["uid"]:
        abort(404)
    return report

def valid_signature(ext, data):
    """Check basic file signatures before saving uploaded files."""
    if ext not in SIGS or not data:
        return False
    if ext == "webp":
        return (
            len(data) >= 12
            and data.startswith(b"RIFF")
            and data[8:12] == b"WEBP"
        )
    return any(data.startswith(signature) for signature in SIGS[ext])
@bp.app_context_processor

def ctx():
    return {
        "user": me(),
        "FEATURES": FEATURES,
    }

# -------------------- Public pages --------------------

@bp.route("/")

def landing():
    return render_template("landing.html")

@bp.route("/features")

def features():
    return render_template("features.html")

@bp.route("/privacy")

def privacy():
    return render_template("privacy.html")

# -------------------- Registration and login --------------------

@bp.route("/register", methods=["GET", "POST"])

def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        error = None
        if not name or len(name) > 80:
            error = "Enter your name."
        elif not EMAIL.match(email):
            error = "Enter a valid email address."
        elif len(password) < 8:
            error = "Use a password of at least 8 characters."
        elif User.query.filter_by(email=email).first():
            error = "An account with this email already exists."
        if error:
            return render_template(
                "auth.html",
                mode="register",
                error=error,
                name=name,
                email=email,
            ), 400
        user = User(
            name=name,
            email=email,
            pw=generate_password_hash(password),
        )
        db.session.add(user)
        db.session.commit()
        start_session(user)
        return redirect(url_for("main.dashboard"))
    return render_template("auth.html", mode="register")

@bp.route("/login", methods=["GET", "POST"])

def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.pw, password):
            return render_template(
                "auth.html",
                mode="login",
                error="Email or password is incorrect.",
                email=email,
            ), 401
        start_session(user)
        return redirect(url_for("main.dashboard"))
    return render_template("auth.html", mode="login")

@bp.route("/logout", methods=["POST"])

def logout():
    session.clear()
    return redirect(url_for("main.landing"))

# -------------------- Dashboard --------------------

@bp.route("/dashboard")
@login_required

def dashboard():
    reports = (
        Report.query
        .filter_by(user_id=session["uid"])
        .order_by(Report.created.desc())
        .all()
    )
    latest = next(
        (report for report in reports if report.status == "Completed"),
        None,
    )
    return render_template(
        "dashboard.html",
        reports=reports[:5],
        total=len(reports),
        done=sum(report.status == "Completed" for report in reports),
        latest=latest,
        flagged=sum(
            1
            for result in (latest.results if latest else [])
            if result.flag != "normal"
        ),
    )

@bp.route("/trends")
@login_required

def trends():
    reports = (
        Report.query
        .filter_by(
            user_id=session["uid"],
            status="Completed",
        )
        .order_by(Report.created.asc())
        .all()
    )
    grouped = {}
    for report in reports:
        for result in report.results:
            name = (result.name or "").strip()
            unit = (result.unit or "").strip()
            if not name or not unit or result.value is None:
                continue
            key = (name.casefold(), unit.casefold())
            if key not in grouped:
                grouped[key] = {
                    "name": name,
                    "unit": unit,
                    "points": [],
                }
            grouped[key]["points"].append({
                "date": report.created.strftime("%Y-%m-%d"),
                "value": result.value,
            })
    trends_data = [
        item for item in grouped.values()
        if len(item["points"]) >= 2
    ]
    return render_template(
        "trends.html",
        trends_data=trends_data,
    )

@bp.route("/profile")
@login_required

def profile():
    return render_template("profile.html")

# -------------------- Upload and process reports --------------------

@bp.route("/upload", methods=["GET", "POST"])
@login_required

def upload():
    if request.method == "GET":
        return render_template("upload.html")
    uploaded_file = request.files.get("file")
    if not uploaded_file or not uploaded_file.filename:
        return render_template(
            "upload.html",
            error="Choose a file to upload.",
        ), 400
    filename = (
        uploaded_file.filename
        .rsplit("/", 1)[-1]
        .rsplit("\\\\", 1)[-1]
    )
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in SIGS:
        return render_template(
            "upload.html",
            error="Unsupported type. Upload a PDF, PNG, JPG, JPEG, TIFF, or WebP.",
        ), 400
    data = uploaded_file.stream.read(MAX_UPLOAD_SIZE + 1)
    if not data:
        return render_template(
            "upload.html",
            error="That file is empty.",
        ), 400
    if len(data) > MAX_UPLOAD_SIZE:
        return render_template(
            "upload.html",
            error="File is too large. Maximum size is 15 MB.",
        ), 400
    if not valid_signature(ext, data):
        return render_template(
            "upload.html",
            error="The file content does not match its extension.",
        ), 400
    stored = uuid.uuid4().hex + "." + ext
    upload_folder = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(upload_folder, exist_ok=True)
    file_path = os.path.join(upload_folder, stored)
    with open(file_path, "wb") as output:
        output.write(data)
    title = re.sub(
        r"[^\w .\-()]",
        "",
        filename.rsplit(".", 1)[0],
    )[:160] or "Report"
    report = Report(
        user_id=session["uid"],
        title=title,
        stored=stored,
        status="Processing",
    )
    try:
        db.session.add(report)
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Could not save uploaded report")
        try:
            if os.path.isfile(file_path):
                os.remove(file_path)
        except OSError:
            current_app.logger.exception("Could not clean up uploaded file")
        return render_template(
            "upload.html",
            error="The report could not be saved. Please try again.",
        ), 500
    try:
        kind = "pdf" if ext == "pdf" else ext
        extracted_text, warnings = extract_text(file_path, kind)
        used_ocr = any(
            "OCR was used" in warning for warning in warnings
        )
        rows, parse_warnings = parse_results(extracted_text)
        warnings.extend(parse_warnings)
        if used_ocr and not any(
            "OCR was used" in warning for warning in warnings
        ):
            warnings.append(
                "OCR was used. Verify extracted values against the original report."
            )
        for row in rows:
            report.results.append(Result(**row))
        report.status = "Completed" if rows else "Failed"
        report.warning = "\n".join(warnings)
    except ValueError as error:
        report.status = "Failed"
        report.warning = str(error)
    except Exception:
        current_app.logger.exception("Report processing failed")
        report.status = "Failed"
        report.warning = (
            "The report could not be processed. "
            "Check the file and OCR configuration, then try again."
        )
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Could not save processed report")
        flash("The report was uploaded, but its results could not be saved.", "danger")
        return redirect(url_for("main.reports"))
    return redirect(url_for("main.report", rid=report.id))

# -------------------- My Reports --------------------

@bp.route("/reports")
@login_required

def reports():
    q = request.args.get("q", "").strip()
    st = request.args.get("status", "").strip()
    query = Report.query.filter_by(user_id=session["uid"])
    if q:
        query = query.filter(Report.title.ilike(f"%{q}%"))
    if st:
        query = query.filter_by(status=st)
    report_list = query.order_by(Report.created.desc()).all()
    return render_template(
        "reports.html",
        reports=report_list,
        q=q,
        st=st,
    )

# -------------------- View individual report --------------------

@bp.route("/reports/<int:rid>")
@login_required

def report(rid):
    current_report = own_report(rid)
    return render_template(
        "report.html",
        r=current_report,
        rows=[
            (result, explain(result))
            for result in current_report.results
        ],
        mode=MODE,
        disclaimer=DISCLAIMER,
    )

# -------------------- Human review and verification --------------------

@bp.route("/reports/<int:rid>/review", methods=["POST"])
@login_required

def save_review(rid):
    current_report = own_report(rid)
    review_status = request.form.get("review_status", "").strip()
    review_notes = request.form.get("review_notes", "").strip()
    allowed_statuses = {
        "Pending Review",
        "Verified",
        "Needs Attention",
    }
    if review_status not in allowed_statuses:
        abort(400)
    if len(review_notes) > 3000:
        flash("Review notes must be 3000 characters or fewer.", "warning")
        return redirect(url_for("main.report", rid=rid))
    current_report.review_status = review_status
    current_report.review_notes = review_notes
    current_report.reviewed_at = (
    datetime.now(timezone(timedelta(hours=5, minutes=30)))
    if review_status != "Pending Review"
    else None
)
    try:
        db.session.commit()
        flash("Review saved successfully.", "success")
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Could not save review for report %s", rid
        )
        flash("Could not save the review. Please try again.", "danger")
    return redirect(url_for("main.report", rid=rid))

# -------------------- View uploaded original file --------------------

@bp.route("/reports/<int:rid>/file")
@login_required

def report_file(rid):
    current_report = own_report(rid)
    return send_from_directory(
        current_app.config["UPLOAD_FOLDER"],
        current_report.stored,
        as_attachment=False,
    )

# -------------------- Download report summary --------------------

@bp.route("/reports/<int:rid>/summary.txt")
@login_required

def summary(rid):
    current_report = own_report(rid)
    lines = [
        f"LabReportAgent summary: {current_report.title}",
        f"Uploaded: {current_report.created:%Y-%m-%d}",
        MODE,
        "",
    ]
    for result in current_report.results:
        explanation = explain(result)
        low = (
            f"{result.low:g}"
            if result.low is not None
            else "N/A"
        )
        high = (
            f"{result.high:g}"
            if result.high is not None
            else "N/A"
        )
        lines.extend([
            f"{result.name}: {result.value:g} {result.unit} "
            f"(report range {low}-{high})",
            "  " + explanation["comparison"],
            "  " + explanation["what"],
            "",
        ])
    lines.append(DISCLAIMER)
    return Response(
        "\n".join(lines),
        mimetype="text/plain",
        headers={
            "Content-Disposition":
                f'attachment; filename="summary-{current_report.id}.txt"'
        },
    )

# -------------------- Delete a report --------------------

@bp.route("/reports/<int:rid>/delete", methods=["POST"])
@login_required

def delete(rid):
    current_report = own_report(rid)
    # Keep the user's current search and status filter.
    q = request.args.get("q", "").strip()
    st = request.args.get("status", "").strip()
    upload_folder = current_app.config["UPLOAD_FOLDER"]
    file_path = os.path.join(upload_folder, current_report.stored)
    try:
        # The model relationships delete related Result records too.
        db.session.delete(current_report)
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Could not delete report %s", rid
        )
        flash(
            "Could not delete this report. Please try again.",
            "danger",
        )
        return redirect(url_for(
            "main.reports",
            q=q,
            status=st,
        ))
    # The database deletion succeeded. Remove only this report's file.
    try:
        if os.path.isfile(file_path):
            os.remove(file_path)
    except OSError:
        # Do not send the user to a blank page if file cleanup fails.
        current_app.logger.exception(
            "Could not remove uploaded file for report %s", rid
        )
    # Always return to My Reports after successful database deletion.
    return redirect(url_for(
        "main.reports",
        q=q,
        status=st,
    ))

# -------------------- AI chat API --------------------

@bp.route("/api/chat", methods=["POST"])
@login_required

def chat():
    from google import genai
    message_data = request.get_json(silent=True) or {}
    question = str(message_data.get("message", "")).strip()
    if not question:
        return jsonify({
            "error": "Please enter a message."
        }), 400
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return jsonify({
            "error": "Gemini API key is not configured."
        }), 500
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=(
                "You are LabCare Assistant in an educational lab-report "
                "explainer. Explain general medical terms in simple language. "
                "Do not diagnose, prescribe medicines, or recommend treatment. "
                "Encourage users to discuss results with a qualified clinician. "
                "If a user describes an emergency, advise them to seek urgent "
                "local medical care. Keep answers concise. "
                "User question: " + question
            ),
        )
        return jsonify({
            "reply": response.text or
            "I couldn't prepare an answer. Please try again."
        })
    except Exception:
        current_app.logger.exception("Gemini chat request failed")
        return jsonify({
            "error": "The assistant is temporarily unavailable. Please try again."
        }), 502
