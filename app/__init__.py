import os, secrets
from datetime import timedelta
from flask import Flask, session, request, abort, render_template
from dotenv import load_dotenv
load_dotenv()
from .models import db

def create_app(overrides=None):
    load_dotenv()
    app = Flask(__name__, instance_relative_config=True)
    os.makedirs(app.instance_path, exist_ok=True)
    app.config.update(
        SECRET_KEY=os.getenv("SECRET_KEY") or secrets.token_hex(32),  # random per run if unset
        SQLALCHEMY_DATABASE_URI="sqlite:///" + os.path.join(app.instance_path, "labreport.db"),
        UPLOAD_FOLDER=os.path.join(app.instance_path, "uploads"),
        MAX_CONTENT_LENGTH=10 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=2))
    if overrides:
        app.config.update(overrides)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    cmd = os.getenv("TESSERACT_CMD")
    if cmd:
        try:
            import pytesseract; pytesseract.pytesseract.tesseract_cmd = cmd
        except ImportError:
            pass
    db.init_app(app)

    @app.before_request
    def csrf():
        if request.method == "POST":
            tok = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
            if not tok or tok != session.get("csrf"):
                abort(400)

    @app.context_processor
    def inject():
        if "csrf" not in session:
            session["csrf"] = secrets.token_hex(16)
        return dict(csrf_token=session["csrf"])

    for code, msg in ((400, "The request could not be verified. Reload the page and try again."),
                      (403, "You don't have access to this page."),
                      (404, "We couldn't find that page."),
                      (413, "That file is larger than the 10 MB limit."),
                      (500, "Something went wrong on our side.")):
        app.register_error_handler(code, lambda e, c=code, m=msg: (render_template("error.html", code=c, msg=m), c))

    from .routes import bp
    app.register_blueprint(bp)
    with app.app_context():
        db.create_all()
    return app
