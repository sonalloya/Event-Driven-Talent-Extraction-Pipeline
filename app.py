from flask import Flask, render_template, request, redirect, url_for, session, flash
import os
import re
import PyPDF2
import docx
from datetime import datetime
import time
import uuid
import csv
from io import StringIO
def extract_text_from_file(file_path):
    ext = file_path.rsplit('.', 1)[-1].lower()
    text = ""
    try:
        if ext == 'pdf':
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    if page.extract_text():
                        text += page.extract_text() + "\n"
        elif ext in ['doc', 'docx']:
            try:
                doc = docx.Document(file_path)
                for para in doc.paragraphs:
                    text += para.text + "\n"
            except Exception:
                pass # docx parsing might fail if it's an older .doc file
        else:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
    except Exception as e:
        print(f"Error extracting text: {e}")
    return text

def parse_resume_data(text):
    data = {
        "name": "Unknown Candidate",
        "email": "N/A",
        "phone": "N/A",
        "skills": [],
        "experience": "N/A"
    }
    
    if not text.strip():
        return data
        
    # Email extraction
    email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
    if email_match:
        data["email"] = email_match.group(0)
        
    # Phone extraction
    phone_match = re.search(r'(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', text)
    if phone_match:
        data["phone"] = phone_match.group(0)
        
    # Name extraction heuristic (first non-empty line)
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    if lines:
        data["name"] = lines[0][:50]
        
    # Skills extraction
    tech_skills = ["Python", "Java", "C++", "AWS", "Azure", "GCP", "Docker", "Kubernetes", 
                   "React", "Angular", "Vue", "Node.js", "Flask", "Django", "SQL", "NoSQL",
                   "Machine Learning", "Data Science", "CI/CD", "Git", "REST APIs", "HTML", "CSS", "JavaScript"]
    
    text_lower = text.lower()
    found_skills = []
    for skill in tech_skills:
        # Simple word boundary check or exact match
        if re.search(r'\b' + re.escape(skill.lower()) + r'\b', text_lower):
            found_skills.append(skill)
            
    if found_skills:
        data["skills"] = found_skills
    else:
        data["skills"] = ["General Professional Skills"]
        
    # Experience extraction heuristic
    exp_match = re.search(r'(\d+)\+?\s*(years?|yrs?)(?:\s*of)?\s*experience', text, re.IGNORECASE)
    if exp_match:
        data["experience"] = f"{exp_match.group(1)} Years"
    
    return data

def calculate_dynamic_scores(text, skills):
    word_count = len(text.split())
    
    # Brevity: sweet spot is 300-600 words
    if 300 <= word_count <= 600:
        brevity = 95
    elif 150 <= word_count < 300 or 600 < word_count <= 900:
        brevity = 75
    else:
        brevity = 50
        
    # Impact: check for action verbs or numbers
    has_numbers = len(re.findall(r'\d+', text))
    action_verbs = ["managed", "led", "developed", "created", "designed", "improved", "increased", "built"]
    verb_count = sum(1 for verb in action_verbs if verb in text.lower())
    impact = min(100, 50 + (verb_count * 5) + (has_numbers * 2))
    
    # Style: simple length and structure heuristic
    sentences = text.split('.')
    style = min(100, 60 + len(sentences) * 2)
    
    # Soft skills / Skills: based on tech skills found
    soft_skills = min(100, 50 + len(skills) * 8)
    
    overall = int((brevity + impact + style + soft_skills) / 4)
    
    return {
        "overall": overall,
        "impact": int(impact),
        "brevity": int(brevity),
        "style": int(style),
        "soft_skills": int(soft_skills)
    }

app = Flask(__name__)
app.secret_key = "secret123"

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# In-memory user store (replace with a real DB in production)
users = {
    "admin@talentai.com": {"password": "admin", "role": "admin"}
}

# In-memory store for recent activity
recent_activity = [
    {
        'id': 'mock1',
        'file':'sonal_resume.pdf',
        'name':'Sonal Sharma',
        'skills':'Python, AWS, Flask',
        'status':'Done',
        'date':'Today 10:30',
        'uploaded_by': 'user@example.com',
        'result': {
            'name': 'Sonal Sharma',
            'scores': {'overall': 82, 'impact': 80, 'brevity': 95, 'style': 75, 'soft_skills': 90}
        }
    },
    {
        'id': 'mock2',
        'file':'john_cv.docx',
        'name':'John Carter',
        'skills':'React, Node.js, SQL',
        'status':'Done',
        'date':'Today 09:15',
        'uploaded_by': 'user@example.com',
        'result': {
            'name': 'John Carter',
            'scores': {'overall': 74, 'impact': 60, 'brevity': 75, 'style': 80, 'soft_skills': 80}
        }
    },
]

# ──────────────────────────────────────────────
# Auth
# ──────────────────────────────────────────────

@app.route("/")
def login_page():
    if "user" in session:
        return redirect("/dashboard")
    return render_template("login.html")


@app.route("/login", methods=["POST"])
def login():
    email    = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    if email in users and users[email]["password"] == password:
        session["user"] = email
        session["role"] = users[email]["role"]
        return redirect("/dashboard")

    flash("Invalid email or password. Please try again.", "danger")
    return redirect("/")


@app.route("/register")
def register_page():
    return render_template("register.html")


@app.route("/register", methods=["POST"])
def register():
    email    = request.form.get("email", "").strip()
    password = request.form.get("password", "")
    role     = request.form.get("role", "user")

    if not email or not password:
        flash("All fields are required.", "danger")
        return redirect("/register")

    if email in users:
        flash("An account with that email already exists.", "danger")
        return redirect("/register")

    users[email] = {"password": password, "role": role}
    flash("Account created! Please sign in.", "success")
    return redirect("/")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ──────────────────────────────────────────────
# Dashboard
# ──────────────────────────────────────────────

@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/")
    
    if session.get("role") == "admin":
        return redirect("/admin")
    else:
        return redirect("/user_dashboard")

@app.route("/admin")
def admin():
    if session.get("role") != "admin":
        return redirect("/dashboard")
    
    total_processed = 124 + len(recent_activity)
    return render_template("admin_dashboard.html", recent_activity=recent_activity, total_processed=total_processed)

@app.route("/user_dashboard")
def user_dashboard():
    if "user" not in session:
        return redirect("/")
    
    user_email = session["user"]
    user_activity = [act for act in recent_activity if act.get("uploaded_by") == user_email]
    
    return render_template("user_dashboard.html", recent_activity=user_activity)

@app.route("/resume/<resume_id>")
def view_resume(resume_id):
    if "user" not in session:
        return redirect("/")
        
    # Find the resume in recent_activity
    for act in recent_activity:
        if act.get("id") == resume_id:
            # Check RBAC: if user is normal user, they can only view their own
            if session.get("role") != "admin" and act.get("uploaded_by") != session["user"]:
                flash("Unauthorized access.", "danger")
                return redirect("/dashboard")
                
            return render_template("user_results.html", result=act.get("result"))
            
    flash("Resume not found.", "danger")
    return redirect("/dashboard")

@app.route("/delete/<resume_id>", methods=["POST"])
def delete_resume(resume_id):
    if "user" not in session:
        return redirect("/")
        
    global recent_activity
    for idx, act in enumerate(recent_activity):
        if act.get("id") == resume_id:
            # Check RBAC: if user is normal user, they can only delete their own
            if session.get("role") != "admin" and act.get("uploaded_by") != session["user"]:
                flash("Unauthorized access.", "danger")
                return redirect("/dashboard")
                
            del recent_activity[idx]
            flash("Resume deleted successfully.", "success")
            return redirect("/dashboard")
            
    flash("Resume not found.", "danger")
    return redirect("/dashboard")

@app.route("/export")
def export_reports():
    if session.get("role") != "admin":
        return redirect("/dashboard")
        
    si = StringIO()
    cw = csv.writer(si)
    # Header row
    cw.writerow(['Candidate Name', 'File Name', 'Uploaded By', 'Skills', 'Overall Score', 'Status', 'Date'])
    
    for act in recent_activity:
        # Safely extract the overall score if it exists
        overall_score = 'N/A'
        if 'result' in act and 'scores' in act['result'] and 'overall' in act['result']['scores']:
            overall_score = act['result']['scores']['overall']
            
        cw.writerow([
            act.get('name', 'Unknown'),
            act.get('file', ''),
            act.get('uploaded_by', ''),
            act.get('skills', ''),
            overall_score,
            act.get('status', ''),
            act.get('date', '')
        ])
        
    from flask import Response
    output = Response(si.getvalue(), mimetype='text/csv')
    output.headers["Content-Disposition"] = "attachment; filename=talent_report.csv"
    return output

# ──────────────────────────────────────────────
# Upload & Extraction
# ──────────────────────────────────────────────

@app.route("/upload")
def upload_page():
    if "user" not in session:
        return redirect("/")
    return render_template("uploadpage.html")


@app.route("/upload", methods=["POST"])
def upload():
    if "user" not in session:
        return redirect("/")

    file = request.files.get("file")
    if not file or file.filename == "":
        flash("No file selected.", "danger")
        return redirect("/upload")

    file_path = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
    file.save(file_path)

    # ── Actual extraction result ──
    # Simulate processing delay
    time.sleep(2)
    
    raw_text = extract_text_from_file(file_path)
    result = parse_resume_data(raw_text)

    # Dynamic scoring
    result["scores"] = calculate_dynamic_scores(raw_text, result.get("skills", []))

    # Add to recent activity
    now_str = datetime.now().strftime("%I:%M %p")
    skills_str = ', '.join(result.get('skills', [])[:3]) if result.get('skills') else 'None'
    resume_id = uuid.uuid4().hex
    
    activity_record = {
        'id': resume_id,
        'file': file.filename,
        'name': result.get('name', 'Unknown Candidate'),
        'skills': skills_str,
        'status': 'Done',
        'date': f"Today {now_str}",
        'uploaded_by': session["user"],
        'result': result
    }
    recent_activity.insert(0, activity_record)

    return redirect(url_for('view_resume', resume_id=resume_id))


if __name__ == "__main__":
    app.run(debug=True)