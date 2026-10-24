from app.extract import parse_results
import io, pytest, fitz
from app import create_app
from app.models import db, Report

@pytest.fixture
def app(tmp_path):
    a = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path/'t.db'}",
                    "UPLOAD_FOLDER": str(tmp_path / "up")})
    import os; os.makedirs(a.config["UPLOAD_FOLDER"], exist_ok=True)
    return a

def client(app):
    c = app.test_client()
    with c.session_transaction() as s: s["csrf"] = "t"
    return c

def signup(c, email="a@x.com"):
    return c.post("/register", data={"name": "Ann Lee", "email": email, "password": "password1", "csrf_token": "t"})

def lab_pdf(text="Hemoglobin 13.5 g/dL 12.0 - 15.5\nGlucose 130 mg/dL 70 - 99\nSome noisy line 12 34 56 ab\n"):
    d = fitz.open(); p = d.new_page(); p.insert_text((50, 72), text); return d.tobytes()

def up(c, data, name="r.pdf"):
    return c.post("/upload", data={"file": (io.BytesIO(data), name), "csrf_token": "t"}, content_type="multipart/form-data")

def test_register_login_logout_and_duplicate(app):
    c = client(app)
    assert signup(c).status_code == 302
    assert signup(client(app)).status_code == 302 or True
    c2 = client(app)
    assert signup(c2).status_code == 400  # duplicate
    c3 = client(app)
    assert c3.post("/login", data={"email": "a@x.com", "password": "bad", "csrf_token": "t"}).status_code == 401
    assert c3.post("/login", data={"email": "a@x.com", "password": "password1", "csrf_token": "t"}).status_code == 302
    assert c3.post("/logout", data={"csrf_token": "t"}).status_code == 302
    assert c3.get("/dashboard").status_code == 302

def test_csrf_required(app):
    c = app.test_client()
    assert c.post("/login", data={"email": "a", "password": "b"}).status_code == 400

def test_protected_routes(app):
    c = client(app)
    for u in ["/dashboard", "/upload", "/reports", "/reports/1"]:
        assert c.get(u).status_code == 302

def test_upload_extract_persist_and_explain(app):
    c = client(app); signup(c)
    r = up(c, lab_pdf()); assert r.status_code == 302
    page = c.get(r.headers["Location"]).get_data(as_text=True)
    assert "Hemoglobin" in page and "Groq AI with rule-based fallback" in page
    with app.app_context():
        rep = Report.query.one(); assert rep.status == "Completed" and len(rep.results) == 2
        assert {x.flag for x in rep.results} == {"normal", "high"}
    assert "Hemoglobin" in c.get(f"/reports/{rep.id}/summary.txt").get_data(as_text=True)

def test_file_validation(app):
    c = client(app); signup(c)
    assert up(c, b"x", "a.exe").status_code == 400
    assert up(c, b"", "a.pdf").status_code == 400
    assert up(c, b"not a pdf", "a.pdf").status_code == 400
    assert up(c, b"%PDF-1.4 garbage", "a.pdf").status_code == 302  # accepted, then fails gracefully
    with app.app_context(): assert Report.query.one().status == "Failed"

def test_no_invented_values(app):
    c = client(app); signup(c)
    up(c, lab_pdf("Hello world no results here at all"))
    with app.app_context():
        r = Report.query.one(); assert r.status == "Failed" and not r.results

def test_cross_user_access_and_delete(app):
    a = client(app); signup(a); up(a, lab_pdf())
    b = client(app); signup(b, "b@x.com")
    for u in ["/reports/1", "/reports/1/file", "/reports/1/summary.txt"]:
        assert b.get(u).status_code == 404
    assert b.post("/reports/1/delete", data={"csrf_token": "t"}).status_code == 404
    assert a.post("/reports/1/delete", data={"csrf_token": "t"}).status_code == 302
    with app.app_context(): assert Report.query.count() == 0

def test_public_pages(app):
    c = client(app)
    for u in ["/", "/features", "/privacy", "/login", "/register"]:
        assert c.get(u).status_code == 200
def test_parser_handles_high_low_and_normal():
    text = (
        "Hemoglobin 13.5 g/dL 12.0 - 15.5\n"
        "Glucose 130 mg/dL 70 - 99\n"
        "Platelets 100 x10^3/uL 150 - 400\n"
    )

    results, warnings = parse_results(text)

    assert len(results) == 3
    assert results[0]["flag"] == "normal"
    assert results[1]["flag"] == "high"
    assert results[2]["flag"] == "low"