import sqlite3
from flask import Flask, request, jsonify, render_template
from google import genai
from google.genai import types
import json
import os
from datetime import datetime
import threading
from config import GEMINI_API_KEY

# Import the pdfgen library
import pdfgen

app = Flask(__name__)
DB_FILE = "jobapply.db"
RESUMES_DIR = "resumes"
TAILORED_RESUMES_DIR = "tailored_resumes"

# Ensure the root resumes directory exists
os.makedirs(RESUMES_DIR, exist_ok=True)

# Ensure the directory for tailored resumes exists
os.makedirs(TAILORED_RESUMES_DIR, exist_ok=True)

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_connection() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name TEXT NOT NULL,
                designation TEXT NOT NULL,
                job_description TEXT,
                job_url TEXT,
                status TEXT DEFAULT 'viewed',
                resume_path TEXT,
                resume_generated INTEGER DEFAULT 0
            )
        ''')
        conn.commit()

def load_base_resume():
    """Load the base resume from resume_json/base.json"""
    base_json_path = os.path.join(os.path.dirname(__file__), 'resume_json', 'base.json')
    if not os.path.exists(base_json_path):
        return None
    with open(base_json_path, 'r') as f:
        return json.load(f)

def tailor_resume_with_gemini(base_resume, job_description):
    """Use Gemini to tailor the resume based on job description"""
    
    
    system_prompt = (
        """
        ### ROLE
You are an expert Technical Resume Strategist. Your goal is to optimize a candidate's "base.json" resume to pass Applicant Tracking Systems (ATS) for a specific Job Description (JD) without compromising the integrity of the original experience.

### INPUT DATA
1. [BASE_JSON]: A JSON file containing Skillset, Work experience, and Projects.
2. [JOB_DESCRIPTION]: The target role requirements.

### OPERATIONAL RULES (THE "GUARDRAILS")
1. **NO DELETIONS:** You are strictly prohibited from deleting any bullet points or categories from the [BASE_JSON]. Every existing achievement/point must remain.
2. **NO COMPANY HALLUCINATION:** Do not mention the name of the company from the [JOB_DESCRIPTION] within the "Work experience" section of the [BASE_JSON]. Maintain the user's original employer names (e.g., JPMorgan Chase).
3. **PRESERVE STRUCTURE & ORDER:** Maintain the exact JSON schema and the internal order of bullet points. You can only add new points or modify existing ones, but you cannot rearrange or remove them.
4. **BIAS TOWARD TECHNOLOGY INFUSION:** Your primary task is to identify technical keywords, tools, or methodologies in the [JOB_DESCRIPTION] that are missing from the [BASE_JSON] and naturally weave them into existing bullet points where they logically fit the stack (e.g., Scala, PySpark, AWS, Terraform).

### TRANSFORMATION LOGIC
- **Skillset:** Expand this section by adding relevant technologies from the JD that the candidate has likely used given their background in Data Engineering, AI and AWS.
- **Bullet Point Enhancement:** Rephrase existing work experience bullets to use "technical terms", "Action Verbs" and "Keywords" found in the JD. 
- **Example of Infusion:** If the JD mentions "Data Governance" and the user has a bullet about "AWS Glue," modify the bullet to: "Leveraged AWS Glue for ETL pipelines, ensuring strict data governance and quality standards".

### OUTPUT
Return ONLY the updated valid JSON object. No preamble. No summary of changes."""
    )

    user_message = f"Base Resume:\n{json.dumps(base_resume)}\n\nJob Description:\n{job_description}"

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json"
        )

        # 3. Request generation directly via the client model route
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=user_message, # Execution prompt goes here
            config=config
        )
        print(response)
        content = response.text

        
        # Strip markdown code blocks if present
        if content.startswith("```"):
            content = content.strip("`").replace("json\n", "", 1)

        tailored_json = json.loads(content)
        return tailored_json
    except Exception as e:
        print(f"Error tailoring resume: {e}")
        return None

def tailor_resume_background(job_id, job_description):
    """Background task to tailor resume asynchronously"""
    base_resume = load_base_resume()
    if base_resume and job_description:
        tailored_resume = tailor_resume_with_gemini(base_resume, job_description)
        
        if tailored_resume:
            # Set up target path structured: resumes/{job_id}/
            job_folder = os.path.join(RESUMES_DIR, str(job_id))
            os.makedirs(job_folder, exist_ok=True)
            # Save the tailored resume to a file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            resume_filename = f"job_{job_id}_{timestamp}.json"
            resume_path = os.path.join(TAILORED_RESUMES_DIR, resume_filename)
            
            with open(resume_path, 'w') as f:
                json.dump(tailored_resume, f, indent=2)
            # Absolute target path for the final PDF output filename
            target_pdf_path = os.path.join(job_folder, "senthil_resume.pdf")
            # Compile PDF directly into target folder
            pdfgen.generate_pdf(resume_path, target_pdf_path)
            # Update the job record with the resume path
            conn = get_db_connection()
            conn.execute('UPDATE jobs SET resume_path = ?, resume_generated = 1 WHERE id = ?',
                        (resume_path, job_id))
            conn.commit()
            conn.close()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/update-resume/<int:job_id>', methods=['POST'])
def update_resume(job_id):
    """
    Receives updated resume JSON from the frontend, saves it to a new file,
    and updates the database mapping to point to the edited version.
    """
    try:
        data = request.get_json()
        updated_resume = data.get('resume')

        if not updated_resume:
            return jsonify({"error": "No resume data provided"}), 400

        # Generate a new filename with an '_updated' suffix
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_filename = f"job_{job_id}_{timestamp}_updated.json"
        new_path = os.path.join(TAILORED_RESUMES_DIR, new_filename)

        # 1. Save the new JSON file
        with open(new_path, 'w') as f:
            json.dump(updated_resume, f, indent=2)
        job_folder = os.path.join(RESUMES_DIR, str(job_id))
        os.makedirs(job_folder, exist_ok=True)
        target_pdf_path = os.path.join(job_folder, "senthil_resume.pdf")
        # Compile PDF through package library
        pdfgen.generate_pdf(new_path, target_pdf_path)
        # 2. Update the database mapping
        conn = get_db_connection()
        # We also set resume_generated to 1 just in case it was somehow 0
        conn.execute('''
            UPDATE jobs 
            SET resume_path = ?, resume_generated = 1 
            WHERE id = ?
        ''', (new_path, job_id))
        conn.commit()
        conn.close()

        return jsonify({
            "status": "success", 
            "message": "Resume updated and saved successfully",
            "new_path": new_path
        }), 200

    except Exception as e:
        print(f"Error updating resume: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/fetch_resume_path/<int:job_id>', methods=['GET'])
def fetch_resume_path(job_id):
    """Checks if a tailored resume exists in resumes/{job_id}/senthil_resume.pdf."""
    relative_path = os.path.join(RESUMES_DIR, str(job_id), "senthil_resume.pdf")
    # Convert the relative path into an absolute path
    absolute_path = os.path.abspath(relative_path)
    
    if os.path.exists(absolute_path):
        return jsonify({
            "status": "success",
            "job_id": job_id,
            "resume_path": absolute_path
        }), 200
    else:
        return jsonify({
            "status": "error",
            "message": f"Resume for Job ID {job_id} does not exist at the expected location."
        }), 404

@app.route('/jobs', methods=['GET'])
def get_jobs():
    conn = get_db_connection()
    jobs = conn.execute('SELECT * FROM jobs').fetchall()
    conn.close()
    return jsonify([dict(job) for job in jobs])

@app.route('/add_job', methods=['POST'])
def add_job():
    data = request.get_json()
    conn = get_db_connection()
    
    # Insert job without resume path initially
    cursor = conn.execute('''
        INSERT INTO jobs (company_name, designation, job_description, job_url, resume_generated)
        VALUES (?, ?, ?, ?, 0)
    ''', (data['company_name'], data['designation'], data['job_description'], data['job_url']))
    
    job_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    # Return 201 immediately
    response = jsonify({"status": "success", "job_id": job_id})
    
    # Start resume tailoring in background thread
    if data.get('job_description'):
        background_thread = threading.Thread(
            target=tailor_resume_background,
            args=(job_id, data['job_description']),
            daemon=True
        )
        background_thread.start()
    
    return response, 201

@app.route('/resume/<int:job_id>', methods=['GET'])
def get_resume(job_id):
    """Fetch the tailored resume for a specific job"""
    conn = get_db_connection()
    job = conn.execute('SELECT resume_path, resume_generated FROM jobs WHERE id = ?', (job_id,)).fetchone()
    conn.close()
    
    if not job or not job['resume_path']:
        return jsonify({"error": "Resume not found"}), 404
    
    try:
        with open(job['resume_path'], 'r') as f:
            resume_data = json.load(f)
        return jsonify({"resume": resume_data, "generated": job['resume_generated']})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/resume-status/<int:job_id>', methods=['GET'])
def resume_status(job_id):
    """Check if resume has been generated"""
    conn = get_db_connection()
    job = conn.execute('SELECT resume_generated FROM jobs WHERE id = ?', (job_id,)).fetchone()
    conn.close()
    
    if not job:
        return jsonify({"error": "Job not found"}), 404
    
    return jsonify({"generated": job['resume_generated']})

@app.route('/base-resume', methods=['GET'])
def get_base_resume():
    """Fetch the base resume"""
    base_resume = load_base_resume()
    if not base_resume:
        return jsonify({"error": "Base resume not found"}), 404
    return jsonify({"resume": base_resume})

@app.route('/comparison.html')
def comparison():
    return render_template('comparison.html')

if __name__ == '__main__':
    init_db()
    app.run(debug=True)