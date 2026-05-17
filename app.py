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
DB_FILE = "jobs.db"
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
                resume_generated INTEGER DEFAULT 0,
                referrals INTEGER DEFAULT 0
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
    prompt_path = os.path.join(os.path.dirname(__file__), 'system_prompt.md')
    try:
        with open(prompt_path, 'r', encoding='utf-8') as f:
            system_prompt = f.read()
    except Exception as e:
        print(f"Error loading system prompt file: {e}")
        return None

    user_message = f"Base Resume:\n{json.dumps(base_resume)}\n\nJob Description:\n{job_description}"

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json"
        )

        response = client.models.generate_content(
            model='gemini-3-flash-preview',
            contents=user_message,
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

def summarise_job(job_description):
    """Use Gemini 3.1 Flash Lite to parse job metrics based on summariser.md rules"""
    prompt_path = os.path.join(os.path.dirname(__file__), 'summariser.md')
    try:
        with open(prompt_path, 'r', encoding='utf-8') as f:
            system_prompt = f.read()
    except Exception as e:
        print(f"Error loading summariser prompt file: {e}")
        return None

    user_message = f"Job Description:\n{job_description}"

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json"
        )

        response = client.models.generate_content(
            model='gemini-3.1-flash-lite',
            contents=user_message,
            config=config
        )
        content = response.text

        # Strip markdown code blocks if present
        if content.startswith("```"):
            content = content.strip("`").replace("json\n", "", 1)

        summary_json = json.loads(content)
        return summary_json
    except Exception as e:
        print(f"Error extracting job insights: {e}")
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
            
            # Request LLM Summary evaluations before updating target row tracking flag
            summary_data = summarise_job(job_description)
            if summary_data:
                summary_filename = f"job_{job_id}_summary.json"
                summary_path = os.path.join(TAILORED_RESUMES_DIR, summary_filename)
                try:
                    with open(summary_path, 'w', encoding='utf-8') as f:
                        json.dump(summary_data, f, indent=2)
                except Exception as e:
                    print(f"Failed to record summary JSON to disk: {e}")

            # Update the job record with the resume path
            conn = get_db_connection()
            conn.execute('UPDATE jobs SET resume_path = ?, resume_generated = 1 WHERE id = ?',
                        (resume_path, job_id))
            conn.commit()
            conn.close()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/update-job-status/<int:job_id>', methods=['PUT'])
def update_job_status(job_id):
    """Updates the pipeline pipeline/tracking status stage for a specific job."""
    data = request.get_json() or {}
    new_status = data.get('status')
    
    valid_stages = ["viewed", "waiting for referral", "applied", "got interview call", "being interviewed"]
    
    if not new_status:
        return jsonify({
            "status": "error",
            "message": f"Invalid status stage. Must be one of: {', '.join(valid_stages)}"
        }), 400

    try:
        conn = get_db_connection()
        job = conn.execute('SELECT id FROM jobs WHERE id = ?', (job_id,)).fetchone()
        
        if not job:
            conn.close()
            return jsonify({"status": "error", "message": "Job tracking row not found."}), 404
            
        conn.execute('UPDATE jobs SET status = ? WHERE id = ?', (new_status, job_id))
        conn.commit()
        conn.close()
        
        return jsonify({
            "status": "success",
            "message": f"Job status updated successfully to '{new_status}'",
            "job_id": job_id,
            "new_status": new_status
        }), 200
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Database write transaction failure: {str(e)}"
        }), 500

@app.route('/referrals/<int:job_id>', methods=['GET'])
def get_referrals(job_id):
    """Fetch the number of referrals for a specific job"""
    conn = get_db_connection()
    job = conn.execute('SELECT referrals FROM jobs WHERE id = ?', (job_id,)).fetchone()
    conn.close()
    
    if not job:
        return jsonify({"error": "Job not found"}), 404
    
    return jsonify({"referrals": job['referrals']})

@app.route('/update-referrals/<int:job_id>', methods=['PUT'])
def no_of_referrals(job_id):
    """Updates the number of referrals asked for a specific job."""
    data = request.get_json() or {}
    referrals_count = data.get('referrals')
    
    if referrals_count is None:
        return jsonify({
            "status": "error",
            "message": "Referrals count is required"
        }), 400
    
    if not isinstance(referrals_count, int) or referrals_count < 0:
        return jsonify({
            "status": "error",
            "message": "Referrals count must be a non-negative integer"
        }), 400

    try:
        conn = get_db_connection()
        job = conn.execute('SELECT id FROM jobs WHERE id = ?', (job_id,)).fetchone()
        
        if not job:
            conn.close()
            return jsonify({"status": "error", "message": "Job not found."}), 404
            
        conn.execute('UPDATE jobs SET referrals = ? WHERE id = ?', (referrals_count, job_id))
        conn.commit()
        conn.close()
        
        return jsonify({
            "status": "success",
            "message": f"Referrals count updated successfully to {referrals_count}",
            "job_id": job_id,
            "referrals": referrals_count
        }), 200
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Database write transaction failure: {str(e)}"
        }), 500
    
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

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_filename = f"job_{job_id}_{timestamp}_updated.json"
        new_path = os.path.join(TAILORED_RESUMES_DIR, new_filename)

        with open(new_path, 'w') as f:
            json.dump(updated_resume, f, indent=2)
        job_folder = os.path.join(RESUMES_DIR, str(job_id))
        os.makedirs(job_folder, exist_ok=True)
        target_pdf_path = os.path.join(job_folder, "senthil_resume.pdf")
        pdfgen.generate_pdf(new_path, target_pdf_path)

        conn = get_db_connection()
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

@app.route('/job-summary/<int:job_id>', methods=['GET'])
def get_job_summary(job_id):
    """Fetch the generated job summary and extracted metrics from disk if present."""
    summary_filename = f"job_{job_id}_summary.json"
    summary_path = os.path.join(TAILORED_RESUMES_DIR, summary_filename)
    
    if not os.path.exists(summary_path):
        return jsonify({
            "status": "error",
            "message": f"Summary details for job registration {job_id} could not be located."
        }), 404
        
    try:
        with open(summary_path, 'r', encoding='utf-8') as f:
            summary_content = json.load(f)
        return jsonify(summary_content), 200
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Failed to retrieve summary configurations: {str(e)}"
        }), 500

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
    
    cursor = conn.execute('''
        INSERT INTO jobs (company_name, designation, job_description, job_url, resume_generated)
        VALUES (?, ?, ?, ?, 0)
    ''', (data['company_name'], data['designation'], data['job_description'], data['job_url']))
    
    job_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    response = jsonify({"status": "success", "job_id": job_id})
    
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