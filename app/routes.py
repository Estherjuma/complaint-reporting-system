from flask import Blueprint, render_template, request, flash, redirect, url_for, session, current_app
from flask_login import login_required
from app import db
from app.models import Complaint, User
import uuid
from datetime import datetime
import os
from werkzeug.utils import secure_filename
from flask import make_response
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import letter
from io import BytesIO

bp = Blueprint("main", __name__, template_folder="templates")

#home page
@bp.route("/") 
def home():
    return render_template("index.html")

#submit complaint page
@bp.route("/submit", methods=["GET", "POST"])
def submit_complaint():
    if request.method == "POST":
        is_anonymous = request.form.get("anonymous") == "on"
        name = None if is_anonymous else request.form.get("name") 
        category = request.form.get("category")
        description = request.form.get("description")
        ticket_id = f"TCK-{datetime.utcnow().year}-{uuid.uuid4().hex[:6].upper()}" # generate unique ticket ID
        evidence = request.files.get("evidence") # file upload
        filename = None
        if evidence and evidence.filename != "":
            filename = secure_filename(evidence.filename)

            upload_folder = os.path.join(current_app.root_path, "static/uploads")
            os.makedirs(upload_folder, exist_ok=True)

            upload_path = os.path.join(upload_folder, filename)
            evidence.save(upload_path)
            
        new_complaint = Complaint(
            user_id=session.get("user_id") if not is_anonymous else None,
            ticket_id=ticket_id,
            name=name,
            category=category,
            description=description,
            evidence_file=filename,
            is_anonymous=is_anonymous
        )
        db.session.add(new_complaint)
        db.session.commit()

        return render_template(
    "submit_complaint.html",
    success=True,
    ticket_id=new_complaint.ticket_id
)
    return render_template("submit_complaint.html")
# Track complaint page
@bp.route("/track", methods=["GET", "POST"]) 
def track_complaint():
    complaint = None

    if request.method == "POST":
        ticket_id = request.form.get("ticket_id")
        complaint = Complaint.query.filter_by(ticket_id=ticket_id).first()
        if not complaint:
            flash("No complaint found with that Ticket ID.", "danger")
    return render_template("track_complaint.html", complaint=complaint)
# Registration page
@bp.route("/register", methods=["GET", "POST"]) # registration page
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        # check if username already exists
        if User.query.filter_by(username=username).first():
            flash("username already taken. Please choose another.", "danger")

            return render_template("register.html")

        user = User(username=username, role="student")
        user.set_password(password)

        db.session.add(user)
        db.session.commit()

        flash("Account created successfully. Please login.", "success")
        return redirect(url_for("main.login"))
    return render_template("register.html")  
# Admin login page
@bp.route("/admin/login", methods=["GET", "POST"]) 
def admin_login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        user = User.query.filter(User.username == username, User.role.in_(["admin", "super_admin"])).first()
        
        if user and user.check_password(password):
            session.clear()
            session["user_id"] = user.id
            session["role"] = "super_admin" if user.role == "super_admin" else "admin"
            session["username"] = user.username
            session["department"] = user.department
            print("SESSION ROLE:", session["role"])
            return redirect(url_for("main.admin_dashboard"))
        flash("Invalid credentials", "danger")
    return render_template("admin_login.html")
# Student login page
@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        user = User.query.filter_by(username=username, role="student").first()

        if user and user.check_password(password):
            session["user_id"] = user.id
            session["role"] = "student"
            session["username"] = user.username
            return redirect(url_for("main.student_dashboard"))

        flash("Invalid student credentials", "danger")

    return render_template("student_login.html")
# Student dashboard
@bp.route("/student")
def student_dashboard():
    if session.get("role") != "student":
        flash("Unauthorized access.", "danger")
        return redirect(url_for("main.login"))
    complaints = Complaint.query.filter_by(user_id=session["user_id"]).order_by(Complaint.created_at.desc()).all()
    return render_template("student_dashboard.html", complaints=complaints)

# Admin dashboard
@bp.route("/admin")
def admin_dashboard():

    if session.get("role") not in ["admin", "super_admin"]:
        flash("Unauthorized access.", "danger")
        return redirect(url_for("main.login"))

    role = session.get("role")
    department = session.get("department")

    # SUPER ADMIN sees everything
    if role == "super_admin":
        query = Complaint.query

    # NORMAL ADMINS see only their department
    else:
        query = Complaint.query.filter_by(
            category=department
        )

    complaints = query.order_by(
        Complaint.created_at.desc()
    ).all()

    return render_template(
        "admin_dashboard.html",
        complaints=complaints
    )
# Manage complaints page
@bp.route("/admin/complaints")
def manage_complaints():

    if session.get("role") not in ["admin", "super_admin"]:
        flash("Unauthorized access.", "danger")
        return redirect(url_for("main.login"))

    status = request.args.get("status")

    role = session.get("role")
    department = session.get("department")

    # SUPER ADMIN sees all complaints
    if role == "super_admin":
        query = Complaint.query

    # NORMAL ADMINS see only their department
    else:
        query = Complaint.query.filter_by(
            category=department
        )

    # status filter
    if status:
        query = query.filter(
            Complaint.status == status
        )

    complaints = query.order_by(
        Complaint.created_at.desc()
    ).all()

    return render_template(
        "manage_complaints.html",
        complaints=complaints,
        status=status
    )
# update complaint status
@bp.route("/admin/update/<ticket_id>/<status>")
def update_status(ticket_id, status):
    if session.get("role") not in ["admin", "super_admin"]:
        flash("Unauthorized access.", "danger")
        return redirect(url_for("main.login"))

    complaint = Complaint.query.filter_by(ticket_id=ticket_id).first_or_404()
    complaint.status = status
    db.session.commit()

    flash(f'Complaint {ticket_id} status updated to {status}.',"success")
    return redirect(url_for("main.admin_dashboard"))
# admin reply
@bp.route("/admin/reply/<ticket_id>", methods=["POST"])
def admin_reply(ticket_id):

    if session.get("role") not in ["admin", "super_admin"]:
        flash("Unauthorized access.", "danger")
        return redirect(url_for("main.login"))

    complaint = Complaint.query.filter_by(
        ticket_id=ticket_id
    ).first_or_404()

    complaint.admin_reply = request.form.get("reply")

    db.session.commit()

    flash("Reply added successfully.", "success")

    return redirect(url_for("main.manage_complaints"))
# delete account
@bp.route("/delete_account")
def delete_account():
    if "user_id" not in session:
        flash("Please login first.", "danger")
        return redirect(url_for("main.login"))
    user = User.query.get(session["user_id"])
    if user:
        complaints = Complaint.query.filter_by(user_id=user.id).all()
        for complaint in complaints:
            complaint.user_id = None
            complaint.name = "Deleted User"
        db.session.delete(user)
        db.session.commit()
    session.clear()
    flash("Your account has been deleted successfully.", "success")
    return redirect(url_for("main.home"))
# logout
@bp.route("/logout") 
def logout():
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for("main.home"))
# generate PDF report
@bp.route("/generate-report")
def generate_report():
    if session.get("role") not in ["admin", "super_admin"]:
        flash("Unauthorized access.", "danger")
        return redirect(url_for("main.login"))
    complaints = Complaint.query.order_by(Complaint.created_at.desc()).all()
    buffer = BytesIO()
    pdf = SimpleDocTemplate(buffer,pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []
    title = Paragraph("University Complaint System Report",styles['Title'])

    elements.append(title)
    elements.append(Spacer(1,20))

    total = len(complaints)

    pending = len([c for c in complaints
        if c.status == "Pending"
    ])
    progress = len([c for c in complaints
        if c.status == "In Progress"
    ])
    resolved = len([c for c in complaints
        if c.status == "Resolved"
    ])

    summary = f"""
    <b>Total Complaints:</b> {total}<br/>
    <b>Pending:</b> {pending}<br/>
    <b>In Progress:</b> {progress}<br/>
    <b>Resolved:</b> {resolved}<br/><br/>
    """

    elements.append(Paragraph(summary, styles['BodyText']))

    for complaint in complaints:

        text = f"""
        <b>Ticket:</b> {complaint.ticket_id}<br/>
        <b>Category:</b> {complaint.category}<br/>
        <b>Status:</b> {complaint.status}<br/>
        <b>Date:</b> {complaint.created_at.strftime('%d %b %Y')}<br/>
        <b>Description:</b> {complaint.description}<br/><br/>
        """

        elements.append(Paragraph(text, styles['BodyText']))
        elements.append( Spacer(1,12))

    pdf.build(elements)
    buffer.seek(0)

    response = make_response(buffer.read())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = ('attachment; filename=complaints_report.pdf')

    return response