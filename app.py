import os
import re
import sqlite3
import pandas as pd
from flask import Flask, render_template, request, redirect, send_file
from pdfminer.high_level import extract_text as extract_pdf_text
from docx import Document

app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Skills list
SKILLS = ["python", "java", "c++", "excel", "sql", "communication", "data analysis", "machine learning"]

# Setup DB
conn = sqlite3.connect('ats.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS candidates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT,
        skills TEXT,
        resume_path TEXT
    )
''')
conn.commit()

# ===== Resume Parsing Helpers =====
def extract_email(text):
    match = re.search(r'[\w\.-]+@[\w\.-]+', text)
    return match.group(0) if match else "Not Found"

def extract_name(text):
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    return lines[0] if lines else "Unknown"

def extract_skills(text):
    text = text.lower()
    return list(set(skill for skill in SKILLS if skill in text))

def extract_text(file_path):
    if file_path.endswith('.pdf'):
        return extract_pdf_text(file_path)
    elif file_path.endswith('.docx'):
        doc = Document(file_path)
        return "\n".join(p.text for p in doc.paragraphs)
    return ""

def parse_resume(file_path):
    text = extract_text(file_path)
    return {
        "name": extract_name(text),
        "email": extract_email(text),
        "skills": extract_skills(text)
    }

def save_to_db(data, filepath):
    # Check if email already exists
    cursor.execute("SELECT id FROM candidates WHERE email = ?", (data.get('email'),))
    existing = cursor.fetchone()
    if not existing:
        cursor.execute('''
            INSERT INTO candidates (name, email, skills, resume_path)
            VALUES (?, ?, ?, ?)
        ''', (
            data.get('name'),
            data.get('email'),
            ', '.join(data.get('skills')),
            filepath
        ))
        conn.commit()



# ===== Routes =====
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        resumes = request.files.getlist('resumes')
        for resume in resumes:
            if resume:
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], resume.filename)
                resume.save(filepath)
                data = parse_resume(filepath)
                save_to_db(data,filepath)
        return redirect('/')
    return render_template('index.html', success="Resumes uploaded successfully!")

@app.route('/dashboard')
def dashboard():
    search = request.args.get('search', '').lower()
    cursor.execute("SELECT id, name, email, skills FROM candidates")
    candidates = cursor.fetchall()

    if search:
        candidates = [
            c for c in candidates
            if search in c[1].lower() or search in c[2].lower() or search in c[3].lower()
        ]
    
    return render_template('dashboard.html', candidates=candidates, search=search)

@app.route('/preview/<int:candidate_id>')
def preview(candidate_id):
    cursor.execute("SELECT resume_path FROM candidates WHERE id = ?", (candidate_id,))
    result = cursor.fetchone()
    if result:
        text = extract_text(result[0])
        return render_template('preview.html', content=text)
    return "Resume not found", 404


@app.route('/clear-db', methods=['POST'])
def clear_db_route():
    cursor.execute("DELETE FROM candidates")
    conn.commit()
    # Do NOT delete files from the uploads folder
    return redirect('/dashboard')

@app.route('/search', methods=['GET'])
def search():
    skill = request.args.get('skill', '')
    cursor.execute('SELECT name, email, skills FROM candidates')
    results = cursor.fetchall()
    matched = [r for r in results if skill.lower() in r[2].lower()]
    return render_template('results.html', candidates=matched, skill=skill)

@app.route('/jd-upload', methods=['GET', 'POST'])
def jd_upload():
    matched = []
    jd_skills = []
    if request.method == 'POST':
        jd_file = request.files['jd']
        if jd_file:
            path = os.path.join(app.config['UPLOAD_FOLDER'], jd_file.filename)
            jd_file.save(path)
            jd_text = extract_text(path)
            jd_skills = extract_skills(jd_text)

            cursor.execute('SELECT name, email, skills FROM candidates')
            candidates = cursor.fetchall()

            for c in candidates:
                cand_skills = c[2].lower()
                if any(skill in cand_skills for skill in jd_skills):
                    matched.append(c)

    return render_template('jd_results.html', candidates=matched, jd_skills=jd_skills)

@app.route('/export-csv')
def export_csv():
    cursor.execute('SELECT name, email, skills FROM candidates')
    data = cursor.fetchall()
    df = pd.DataFrame(data, columns=["Name", "Email", "Skills"])
    csv_path = os.path.join(app.config['UPLOAD_FOLDER'], "candidates.csv")
    df.to_csv(csv_path, index=False)
    return send_file(csv_path, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)
