from flask import Blueprint, render_template, request, flash, redirect, url_for, session, current_app
from flask_login import login_required
from app import db
from app.models import Complaint, User, Notification
import uuid
from datetime import datetime
import os
from werkzeug.utils import secure_filename
from flask import make_response
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import letter
from io import BytesIO
import csv
from io import StringIO
from flask import make_response

bp = Blueprint("main", __name__, template_folder="templates")

@bp.context_processor
def inject_unread_notifications():

    if session.get("user_id"):

        unread_count = Notification.query.filter_by(
            user_id=session["user_id"],
            is_read=False
        ).count()

        return dict(unread_count=unread_count)

    return dict(unread_count=0)

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
        
        if not is_anonymous and session.get("user_id"):
            notification = Notification(
                user_id=session["user_id"],
                message=f"Complaint {ticket_id} submitted successfully."
                )
            db.session.add(notification)
        admins = User.query.filter( 
            db.or_(
                User.role == "super_admin",
                db.and_(
                    User.role == "admin",
                    User.department == category
                )
            )
        ).all()
        
        for admin in admins:
            admin_notification = Notification(
                user_id=admin.id,
                message=f"New complaint submitted: {ticket_id}"
                )
            db.session.add(admin_notification)
        db.session.commit()
            
        return render_template("submit_complaint.html", success=True, ticket_id=new_complaint.ticket_id)
    return render_template("submit_complaint.html")
# Track complaint page
@bp.route("/track", methods=["GET", "POST"])
def track_complaint():

    complaint = None
    ticket_id = ""

    # From notification click
    ticket_id = request.args.get("ticket")

    if ticket_id:
        complaint = Complaint.query.filter_by(
            ticket_id=ticket_id
        ).first()

    # From normal search form
    elif request.method == "POST":
        ticket_id = request.form.get("ticket_id")

        complaint = Complaint.query.filter_by(
            ticket_id=ticket_id
        ).first()

        if not complaint:
            flash(
                "No complaint found with that Ticket ID.",
                "danger"
            )

    return render_template(
        "track_complaint.html",
        complaint=complaint,
        ticket_id=ticket_id
    )
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
        query = Complaint.query.filter_by(category=department)
        
    complaints = query.order_by(Complaint.created_at.desc()).all()
        
    service_count = len([c for c in complaints if c.category == "Service"])
    staff_count = len([c for c in complaints if c.category == "Staff"])
    facilities_count = len([c for c in complaints if c.category == "Facilities"])
    other_count = len([c for c in complaints if c.category == "Other"])
        
    max_count = max(
        service_count,
        staff_count,
        facilities_count,
        other_count,
        1
    ) # prevent division by zero
    service_percent = (service_count / max_count) * 100
    staff_percent = (staff_count / max_count) * 100
    facilities_percent = (facilities_count / max_count) * 100
    other_percent = (other_count / max_count) * 100

    return render_template(
        "admin_dashboard.html",
        complaints=complaints,
        service_percent=service_percent,
        staff_percent=staff_percent,
        facilities_percent=facilities_percent,
        other_percent=other_percent
    )
# Manage complaints page
@bp.route("/admin/complaints")
def manage_complaints():

    if session.get("role") not in ["admin", "super_admin"]:
        flash("Unauthorized access.", "danger")
        return redirect(url_for("main.login"))

    category = request.args.get("category")
    status = request.args.get("status")
    search = request.args.get("search", "").strip()

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
        
    # SEARCH FILTER
    if search:
        query = query.filter(
            db.or_(
                Complaint.ticket_id.ilike(f"%{search}%"),
                Complaint.name.ilike(f"%{search}%"),
                Complaint.description.ilike(f"%{search}%")
            )
        )
    # CATEGORY FILTER
    if category:
        query = query.filter(
            Complaint.category == category
        )
    # status filter
    if status:
        query = query.filter(
            Complaint.status == status
        )
    page = request.args.get("page", 1, type=int)
    complaints = query.order_by(
        Complaint.created_at.desc()
    ).paginate(
        page=page,
        per_page=10,
        error_out=False
    )

    return render_template(
        "manage_complaints.html",
        complaints=complaints,
        status=status,
        search=search,
        category=category
    )
# update complaint status
@bp.route("/admin/update/<ticket_id>/<status>")
def update_status(ticket_id, status):
    if session.get("role") not in ["admin", "super_admin"]:
        flash("Unauthorized access.", "danger")
        return redirect(url_for("main.login"))

    complaint = Complaint.query.filter_by(ticket_id=ticket_id).first_or_404()
    complaint.status = status
    if complaint.user_id:
        notification = Notification(
            user_id=complaint.user_id,
            message=f"Your complaint {complaint.ticket_id} status changed to {status}."
            )
        db.session.add(notification)
    db.session.commit()
    flash(f'Complaint {ticket_id} status updated to {status}.',"success")
    return redirect(url_for("main.admin_dashboard"))
# complaint details page
@bp.route("/admin/complaint/<ticket_id>")
def complaint_details(ticket_id):

    if session.get("role") not in ["admin", "super_admin"]:
        flash("Unauthorized access.", "danger")
        return redirect(url_for("main.login"))

    complaint = Complaint.query.filter_by(
        ticket_id=ticket_id
    ).first_or_404()

    return render_template(
        "complaint_details.html",
        complaint=complaint
    )
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
    if complaint.user_id:
        notification = Notification(
            user_id=complaint.user_id,
            message=f"An administrator replied to complaint {complaint.ticket_id}."
            )
        db.session.add(notification)
    db.session.commit()

    flash("Reply added successfully.", "success")

    return redirect(url_for("main.manage_complaints"))
# notifications
@bp.route("/notifications")
def notifications():
    if not session.get("user_id"):
        flash("Unauthorized access.", "danger")
        return redirect(url_for("main.login"))

    notifications = Notification.query.filter_by(user_id=session["user_id"]).order_by(Notification.created_at.desc()).all()
    for notification in notifications:
        notification.is_read = True
    db.session.commit()
    return render_template(
        "notifications.html",
        notifications=notifications
    )
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
# profile page
@bp.route("/profile")
def profile():

    if not session.get("user_id"):
        flash("Please login first.", "danger")
        return redirect(url_for("main.login"))

    user = User.query.get(session["user_id"])

    return render_template(
        "profile.html",
        user=user
    )
# change password
@bp.route("/change-password", methods=["GET", "POST"])
def change_password():

    if not session.get("user_id"):
        flash("Please login first.", "danger")
        return redirect(url_for("main.login"))

    user = User.query.get(session["user_id"])

    if request.method == "POST":

        current_password = request.form.get("current_password")
        new_password = request.form.get("new_password")
        confirm_password = request.form.get("confirm_password")

        if not user.check_password(current_password):
            flash("Current password is incorrect.", "danger")
            return redirect(url_for("main.change_password"))

        if new_password != confirm_password:
            flash("New passwords do not match.", "danger")
            return redirect(url_for("main.change_password"))
        if user.check_password(new_password):
            flash("New password must be different from the current password.", "danger")
            return redirect(url_for("main.change_password"))

        user.set_password(new_password)
        db.session.commit()

        session.clear()
        flash("Password changed successfully. Please login again.", "success")
        return redirect(url_for("main.login"))

    return render_template("change_password.html")
# generate PDF report
@bp.route("/generate-report")
def generate_report():
    if session.get("role") not in ["admin", "super_admin"]:
        flash("Unauthorized access.", "danger")
        return redirect(url_for("main.login"))

    role = session.get("role")
    department = session.get("department")

    if role == "super_admin":
        complaints = Complaint.query.order_by(Complaint.created_at.desc()).all()
    else:
        complaints = Complaint.query.filter_by(category=department).order_by(Complaint.created_at.desc()).all()

    buffer = BytesIO()

    pdf = SimpleDocTemplate(
        buffer,
        pagesize=letter
    )
    styles = getSampleStyleSheet()
    elements = []
    # logo
    logo_path = os.path.join(
        current_app.root_path,
        "static",
        "uploads",
        "logo.jpeg"
    )

    if os.path.exists(logo_path):
        logo = Image(
            logo_path,
            width=80,
            height=80
        )
        elements.append(logo)

    title = Paragraph("<b>UNIVERSITY COMPLAINT MANAGEMENT SYSTEM</b>",styles["Title"])
    report_banner = Paragraph("<b>OFFICIAL COMPLAINT ANALYSIS REPORT</b>",styles["Heading2"])

    if role == "super_admin":
        report_title = "System-Wide Complaints Report"
    else:
        report_title = f"{department} Department Complaints Report"

    subtitle = Paragraph(report_title, styles["Heading3"])

    generated = Paragraph(f"Generated on: {datetime.now().strftime('%d %B %Y %H:%M')}", styles["Normal"])
    generated_by = Paragraph(f"Generated by: {session.get('username')}",styles["Normal"])

    elements.append(title)
    elements.append(report_banner)
    elements.append(subtitle)
    elements.append(Spacer(1, 12))
    elements.append(generated)
    elements.append(generated_by)
    elements.append(Spacer(1, 20))

# =======Statistics=========
    total = len(complaints)

    pending = len([
        c for c in complaints
        if c.status == "Pending"
    ])
    progress = len([
        c for c in complaints
        if c.status == "In Progress"
    ])
    resolved = len([
        c for c in complaints
        if c.status == "Resolved"
    ])
    service_count = len([
        c for c in complaints
        if c.category == "Service"
    ])
    staff_count = len([
        c for c in complaints
        if c.category == "Staff"
    ])
    facilities_count = len([
        c for c in complaints
        if c.category == "Facilities"
    ])
    other_count = len([
        c for c in complaints
        if c.category == "Other"
    ])

    pending_percent = round(
        (pending / total) * 100, 1
    ) if total else 0

    progress_percent = round(
        (progress / total) * 100, 1
    ) if total else 0

    resolved_percent = round(
        (resolved / total) * 100, 1
    ) if total else 0

    # =========================
    # EXECUTIVE SUMMARY
    # =========================

    summary = f"""
    <b>EXECUTIVE SUMMARY</b><br/><br/>
    This report contains <b>{total}</b> complaint(s).
    <b>{pending}</b> are Pending,
    <b>{progress}</b> are In Progress,
    and <b>{resolved}</b> have been Resolved.

    <b>CATEGORY BREAKDOWN</b><br/><br/>

    Service: {service_count}<br/>
    Staff: {staff_count}<br/>
    Facilities: {facilities_count}<br/>
    Other: {other_count}<br/>
    """

    elements.append(
        Paragraph(
            summary,
            styles["BodyText"]
        )
    )

    elements.append(Spacer(1, 20))

    # =========================
    # STATUS DISTRIBUTION
    # =========================

    status_summary = f"""
    <b>STATUS DISTRIBUTION</b><br/><br/>

    Pending: {pending_percent}%<br/>
    In Progress: {progress_percent}%<br/>
    Resolved: {resolved_percent}%<br/>
    """

    elements.append(
        Paragraph(
            status_summary,
            styles["BodyText"]
        )
    )

    elements.append(Spacer(1, 20))

    # =========================
    # COMPLAINT DETAILS TABLE
    # =========================

    elements.append(
        Paragraph(
            "COMPLAINT DETAILS",
            styles["Heading2"]
        )
    )

    elements.append(Spacer(1, 10))

    table_data = [
        [
            "Ticket ID",
            "Category",
            "Status",
            "Submitted By",
            "Date"
        ]
    ]

    for complaint in complaints:
        submitted_by = (
            "Anonymous"
            if complaint.is_anonymous
            else complaint.name or "Registered User"
            )

        table_data.append([
            complaint.ticket_id,
            complaint.category,
            complaint.status,
            submitted_by,
            complaint.created_at.strftime("%d-%m-%Y")
        ])

    table = Table(
        table_data,
        colWidths=[110, 90, 90, 120, 90]
        )

    table.setStyle(
        TableStyle([

            ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#0f172a')),
            ('TEXTCOLOR',(0,0),(-1,0),colors.white),
            ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
            ('GRID',(0,0),(-1,-1),0.5,colors.grey),
            ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f8fafc')]),
            ('ALIGN',(0,0),(-1,-1),'CENTER'),    
            ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
            ('BOTTOMPADDING',(0,0),(-1,0),12),
            ('FONTSIZE',(0,0),(-1,-1),9)
        ])
    )

    elements.append(table)

    # =========================
    # SIGNATURE
    # =========================

    elements.append(Spacer(1, 40))

    elements.append(
        Paragraph( "____________________________", styles["Normal"] )
    )
    elements.append(
        Paragraph(f"Generated by: {session.get('username')}",styles["Normal"])
    )
    elements.append(
        Paragraph("System Administrator",styles["Normal"])
    )
    elements.append(Spacer(1, 15))
    elements.append(
        Paragraph( "End of Report", styles["Italic"] )
    )

    # =========================
    # BUILD PDF
    # =========================

    pdf.build(elements)

    buffer.seek(0)

    response = make_response(
        buffer.read()
    )

    response.headers["Content-Type"] = "application/pdf"

    response.headers["Content-Disposition"] = (
        "attachment; filename=complaints_report.pdf"
    )

    return response
# Export complaints to CSV
@bp.route("/admin/export")
def export_complaints():

    if session.get("role") not in ["admin", "super_admin"]:
        flash("Unauthorized access.", "danger")
        return redirect(url_for("main.login"))

    status = request.args.get("status")
    category = request.args.get("category")
    search = request.args.get("search")

    role = session.get("role")
    department = session.get("department")

    if role == "super_admin":
        query = Complaint.query
    else:
        query = Complaint.query.filter_by(
            category=department
        )

    if category:
        query = query.filter(
            Complaint.category == category
        )

    if status:
        query = query.filter(
            Complaint.status == status
        )

    if search:
        query = query.filter(
            db.or_(
                Complaint.ticket_id.ilike(f"%{search}%"),
                Complaint.name.ilike(f"%{search}%"),
                Complaint.description.ilike(f"%{search}%")
            )
        )

    complaints = query.all()

    output = StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Ticket ID",
        "Name",
        "Category",
        "Description",
        "Status",
        "Date"
    ])

    for complaint in complaints:
        writer.writerow([
            complaint.ticket_id,
            complaint.name,
            complaint.category,
            complaint.description,
            complaint.status,
            complaint.created_at.strftime("%Y-%m-%d")
        ])

    response = make_response(output.getvalue())
    response.headers[
        "Content-Disposition"
    ] = "attachment; filename=complaints.csv"

    response.headers[
        "Content-Type"
    ] = "text/csv"

    return response