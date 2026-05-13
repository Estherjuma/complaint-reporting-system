from flask import Blueprint, render_template, request, flash, redirect, url_for, session, current_app
from app import db
from app.models import Complaint, User
import uuid
from datetime import datetime
import os
from werkzeug.utils import secure_filename

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

        flash(f"Complaint submitted successfully. Your Ticket ID is {new_complaint.ticket_id}. Keep it safe.", "success")
        return redirect(url_for("main.submit_complaint"))
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

        user = User.query.filter_by(username=username, role="admin").first()

        if user and user.check_password(password):
            session["user_id"] = user.id
            session["role"] = "admin"
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
    if session.get("role") != "admin":
        flash("Unauthorized access.", "danger")
        return redirect(url_for("main.login"))

    status = request.args.get("status")
    category = request.args.get("category")

    query = Complaint.query
    # status filter
    if status:
        query = query.filter(Complaint.status == status)
    # category filter 
    if category:
        query = query.filter(Complaint.category == category)
    complaints = query.order_by(Complaint.created_at.desc()).all()

    return render_template("admin_dashboard.html", complaints=complaints, status=status, category=category)
# update complaint status
@bp.route("/admin/update/<ticket_id>/<status>")
def update_status(ticket_id, status):
    if session.get("role") != "admin":
        flash("Unauthorized access.", "danger")
        return redirect(url_for("main.login"))

    complaint = Complaint.query.filter_by(ticket_id=ticket_id).first_or_404()
    complaint.status = status
    db.session.commit()

    flash(f'Complaint {ticket_id} status updated to {status}.',"success")
    return redirect(url_for("main.admin_dashboard"))
# logout
@bp.route("/logout") 
def logout():
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for("main.home"))
    




