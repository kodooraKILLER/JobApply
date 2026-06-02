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
        # Create core tracking table if it doesn't exist yet
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

        # Schema Evolution: Automatically append flexible "params" column to existing databases
        cursor = conn.execute("PRAGMA table_info(jobs)")
        columns = [row['name'] for row in cursor.fetchall()]
        
        if 'params' not in columns:
            print("Database Migration: Appending flexible 'params' column to the jobs table.")
            conn.execute("ALTER TABLE jobs ADD COLUMN params TEXT DEFAULT '{}'")
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
            model='gemini-3.5-flash',
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

def autobold_resume_with_gemini(tailored_resume, job_description):
    """Use Gemini 2.5 Flash to automatically apply markdown bolding to the resume"""
    prompt_path = os.path.join(os.path.dirname(__file__), 'hr_autobolder.md')
    try:
        with open(prompt_path, 'r', encoding='utf-8') as f:
            system_prompt = f.read()
    except Exception as e:
        print(f"Error loading hr_autobolder prompt file: {e}")
        return None

    user_message = f"Base Resume:\n{json.dumps(tailored_resume)}\n\nJob Description:\n{job_description}"

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

        autobolded_json = json.loads(content)
        return autobolded_json
    except Exception as e:
        print(f"Error autobolding resume: {e}")
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
    """Background task to tailor resume asynchronously with fallback error handling"""
    base_resume = load_base_resume()
    
    # Initialize variables for failure capture
    error_occurred = False
    error_message = "Unknown error occurred during background execution."

    if not base_resume:
        error_occurred = True
        error_message = "Base resume configuration JSON could not be loaded."
    elif not job_description:
        error_occurred = True
        error_message = "Job description empty or invalid."
    else:
        # 1. Attempt Resume Tailoring via Gemini
        tailored_resume = tailor_resume_with_gemini(base_resume, job_description)
        
        if tailored_resume:
            try:
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
                
                # Request LLM Summary evaluations 
                summary_data = summarise_job(job_description)
                if summary_data:
                    summary_filename = f"job_{job_id}_summary.json"
                    summary_path = os.path.join(TAILORED_RESUMES_DIR, summary_filename)
                    try:
                        with open(summary_path, 'w', encoding='utf-8') as f:
                            json.dump(summary_data, f, indent=2)
                    except Exception as e:
                        print(f"Failed to record summary JSON to disk: {e}")

                # SUCCESS TRANSACTION UPDATE
                conn = get_db_connection()
                conn.execute('UPDATE jobs SET resume_path = ?, resume_generated = 1 WHERE id = ?',
                            (resume_path, job_id))
                conn.commit()
                conn.close()
                return # Exit function on successful build
                
            except Exception as e:
                error_occurred = True
                error_message = f"File compilation or storage update failure: {str(e)}"
        else:
            error_occurred = True
            error_message = "Gemini AI pipeline failed to respond or encountered a rate limit."

    # 2. FAILURE RECORDING BLOCK
    if error_occurred:
        try:
            conn = get_db_connection()
            job_row = conn.execute('SELECT params FROM jobs WHERE id = ?', (job_id,)).fetchone()
            
            try:
                params = json.loads(job_row['params'] or '{}') if job_row else {}
            except Exception:
                params = {}
            
            # Pack error state details safely into tracking data map
            params['error_log'] = error_message
            params['failed_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            conn.execute('''
                UPDATE jobs 
                SET resume_generated = -1, params = ? 
                WHERE id = ?
            ''', (json.dumps(params), job_id))
            conn.commit()
            conn.close()
        except Exception as db_err:
            print(f"CRITICAL: Failed to write error fallback state to database: {db_err}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/update-job-status/<int:job_id>', methods=['PUT'])
def update_job_status(job_id):
    """Updates the pipeline pipeline/tracking status stage for a specific job."""
    data = request.get_json() or {}
    new_status = data.get('status')
    
    
    if not new_status:
        return jsonify({
            "status": "error",
            "message": f"Invalid status stage"
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

@app.route('/autobold/<int:job_id>', methods=['POST'])
def autobold_endpoint(job_id):
    """
    Saves recent edits made to the baseline tailored resume,
    then executes the HR Autobolder subprocess via Gemini 2.5 Flash.
    """
    try:
        data = request.get_json() or {}
        current_resume = data.get('resume')

        if not current_resume:
            return jsonify({"error": "No resume data provided for autobolding"}), 400

        # 1. Sync current manual baseline tailored edits first
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        tailored_filename = f"job_{job_id}_{timestamp}_updated.json"
        tailored_path = os.path.join(TAILORED_RESUMES_DIR, tailored_filename)

        with open(tailored_path, 'w') as f:
            json.dump(current_resume, f, indent=2)
        
        job_folder = os.path.join(RESUMES_DIR, str(job_id))
        os.makedirs(job_folder, exist_ok=True)
        target_pdf_path = os.path.join(job_folder, "senthil_resume.pdf")
        pdfgen.generate_pdf(tailored_path, target_pdf_path)

        # 2. Extract Job Details
        conn = get_db_connection()
        job_row = conn.execute('SELECT job_description, params FROM jobs WHERE id = ?', (job_id,)).fetchone()
        
        if not job_row:
            conn.close()
            return jsonify({"error": "Job tracking element missing."}), 404

        job_description = job_row['job_description'] or ""
        
        # 3. Fire processing core running on Gemini 2.5 Flash
        autobolded_json = autobold_resume_with_gemini(current_resume, job_description)
        if not autobolded_json:
            conn.close()
            return jsonify({"error": "Failed to safely bold the configuration map."}), 500

        # 4. Save autobolded content maps
        autobold_filename = f"job_{job_id}_{timestamp}_autobolded.json"
        autobold_json_path = os.path.join(TAILORED_RESUMES_DIR, autobold_filename)
        with open(autobold_json_path, 'w') as f:
            json.dump(autobolded_json, f, indent=2)

        autobold_pdf_path = os.path.join(job_folder, "senthil_resume_autobolded.pdf")
        pdfgen.generate_pdf(autobold_json_path, autobold_pdf_path)

        # 5. Extract/Pack parameter items for tracking state backward-compatibility
        try:
            params = json.loads(job_row['params'] or '{}')
        except Exception:
            params = {}
        
        params['autobold_json_path'] = autobold_json_path
        params['autobold_pdf_path'] = autobold_pdf_path
        params['has_autobolded'] = True
        params_json_text = json.dumps(params)

        conn.execute('''
            UPDATE jobs 
            SET resume_path = ?, resume_generated = 1, params = ? 
            WHERE id = ?
        ''', (tailored_path, job_id, params_json_text))
        conn.commit()
        conn.close()

        return jsonify({
            "status": "success",
            "message": "Resume synced & HR Autobolded successfully!",
            "autobolded_resume": autobolded_json
        }), 200

    except Exception as e:
        print(f"Error executing Autobolder engine: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/autobold-resume/<int:job_id>', methods=['GET'])
def get_autobold_resume(job_id):
    """Fetch the compiled autobolded resume data if it has been executed"""
    conn = get_db_connection()
    job_row = conn.execute('SELECT params FROM jobs WHERE id = ?', (job_id,)).fetchone()
    conn.close()

    if not job_row:
        return jsonify({"error": "Job record missing"}), 404

    try:
        params = json.loads(job_row['params'] or '{}')
    except Exception:
        params = {}

    autobold_json_path = params.get('autobold_json_path')
    if not autobold_json_path or not os.path.exists(autobold_json_path):
        return jsonify({"error": "Autobolded configuration has not been generated yet."}), 404

    try:
        with open(autobold_json_path, 'r') as f:
            autobold_data = json.load(f)
        return jsonify({"resume": autobold_data, "has_autobolded": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/update-autobold-resume/<int:job_id>', methods=['POST'])
def update_autobold_resume(job_id):
    """Update manually shifted or configured weights inside the compiled autobold block layout"""
    try:
        data = request.get_json() or {}
        updated_autobold_resume = data.get('resume')

        if not updated_autobold_resume:
            return jsonify({"error": "No configuration parameters provided"}), 400

        conn = get_db_connection()
        job_row = conn.execute('SELECT params FROM jobs WHERE id = ?', (job_id,)).fetchone()

        if not job_row:
            conn.close()
            return jsonify({"error": "Job tracking row missing"}), 404

        try:
            params = json.loads(job_row['params'] or '{}')
        except Exception:
            params = {}

        autobold_json_path = params.get('autobold_json_path')
        
        if not autobold_json_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            autobold_json_path = os.path.join(TAILORED_RESUMES_DIR, f"job_{job_id}_{timestamp}_autobolded.json")
            params['autobold_json_path'] = autobold_json_path

        with open(autobold_json_path, 'w') as f:
            json.dump(updated_autobold_resume, f, indent=2)

        job_folder = os.path.join(RESUMES_DIR, str(job_id))
        os.makedirs(job_folder, exist_ok=True)
        autobold_pdf_path = os.path.join(job_folder, "senthil_resume_autobolded.pdf")
        pdfgen.generate_pdf(autobold_json_path, autobold_pdf_path)

        params['autobold_pdf_path'] = autobold_pdf_path
        params['has_autobolded'] = True
        
        conn.execute('UPDATE jobs SET params = ? WHERE id = ?', (json.dumps(params), job_id))
        conn.commit()
        conn.close()

        return jsonify({
            "status": "success",
            "message": "Autobold manual tweaks compiled to storage file systems.",
            "new_path": autobold_json_path
        }), 200

    except Exception as e:
        print(f"Error writing update to autobold block: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/fetch_resume_path/<int:job_id>', methods=['GET'])
def fetch_resume_path(job_id):
    """Checks if a tailored resume or an HR autobolded resume exists and returns its absolute path."""
    resume_type = request.args.get('type', 'tailored')
    
    if resume_type == 'autobold':
        conn = get_db_connection()
        job_row = conn.execute('SELECT params FROM jobs WHERE id = ?', (job_id,)).fetchone()
        conn.close()
        if job_row:
            try:
                params = json.loads(job_row['params'] or '{}')
                autobold_pdf_path = params.get('autobold_pdf_path')
                if autobold_pdf_path and os.path.exists(autobold_pdf_path):
                    return jsonify({
                        "status": "success",
                        "job_id": job_id,
                        "resume_path": os.path.abspath(autobold_pdf_path)
                    }), 200
            except Exception:
                pass
        return jsonify({
            "status": "error",
            "message": f"Autobolded resume PDF for Job ID {job_id} does not exist yet."
        }), 404
    else:
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
    
    processed_jobs = []
    for job in jobs:
        # Convert sqlite3.Row object instance to a native mutable dictionary
        job_dict = dict(job)
        
        # Safe string-to-JSON serialization decoding block
        try:
            unpacked_params = json.loads(job_dict.get('params') or '{}')
        except Exception:
            unpacked_params = {}
            
        # Extract the date field, gracefully falling back to None if older rows lack it
        job_dict['date_added'] = unpacked_params.get('date_added', None)
        
        processed_jobs.append(job_dict)
        
    return jsonify(processed_jobs)

@app.route('/add_job', methods=['POST'])
def add_job():
    data = request.get_json()
    
    # Generate stringified YYYY-MM-DD format of today's date
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # Initialize flexible json storage map parameter dictionary
    flexible_params = {
        "date_added": today_str
    }
    
    # Convert payload mapping directly into a text string representation
    params_json_text = json.dumps(flexible_params)

    conn = get_db_connection()
    cursor = conn.execute('''
        INSERT INTO jobs (company_name, designation, job_description, job_url, resume_generated, params)
        VALUES (?, ?, ?, ?, 0, ?)
    ''', (data['company_name'], data['designation'], data['job_description'], data['job_url'], params_json_text))
    
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
    """Fetch the tailored resume for a specific job, with fallback error detection"""
    conn = get_db_connection()
    job = conn.execute('SELECT resume_path, resume_generated, params FROM jobs WHERE id = ?', (job_id,)).fetchone()
    conn.close()
    
    if not job:
        return jsonify({"error": "Job tracking row not found"}), 404
        
    if job['resume_generated'] == -1:
        try:
            params = json.loads(job['params'] or '{}')
            err_msg = params.get('error_log', "Pipeline execution exception.")
        except Exception:
            err_msg = "Unknown background processing fault."
        return jsonify({
            "error": "Resume generation failed",
            "generated": -1,
            "details": err_msg
        }), 422
    
    if not job['resume_path'] or not os.path.exists(job['resume_path']):
        return jsonify({"error": "Resume file path not found or still generating", "generated": job['resume_generated']}), 404
    
    try:
        with open(job['resume_path'], 'r') as f:
            resume_data = json.load(f)
        return jsonify({"resume": resume_data, "generated": job['resume_generated']})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/regenerate-resume/<int:job_id>', methods=['POST'])
def regenerate_resume(job_id):
    """Resets tracking keys and fires the background LLM thread to retry generation."""
    try:
        conn = get_db_connection()
        job_row = conn.execute('SELECT job_description FROM jobs WHERE id = ?', (job_id,)).fetchone()
        
        if not job_row:
            conn.close()
            return jsonify({"status": "error", "message": "Job record missing."}), 404

        job_description = job_row['job_description']
        
        if not job_description:
            conn.close()
            return jsonify({"status": "error", "message": "Cannot generate resume without a job description."}), 400

        # Reset row status flag back to 0 (generating)
        conn.execute('UPDATE jobs SET resume_generated = 0 WHERE id = ?', (job_id,))
        conn.commit()
        conn.close()

        # Spin up worker subprocess thread 
        background_thread = threading.Thread(
            target=tailor_resume_background,
            args=(job_id, job_description),
            daemon=True
        )
        background_thread.start()

        return jsonify({
            "status": "success",
            "message": "Resume generation process re-triggered successfully!"
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    

@app.route('/resume-status/<int:job_id>', methods=['GET'])
def resume_status(job_id):
    """Check if resume has been generated, is compiling, or encountered an LLM fault"""
    conn = get_db_connection()
    job = conn.execute('SELECT resume_generated, params FROM jobs WHERE id = ?', (job_id,)).fetchone()
    conn.close()
    
    if not job:
        return jsonify({"error": "Job not found"}), 404
    
    status_code = job['resume_generated']
    response_payload = {"generated": status_code}
    
    # If a failure was caught, pass the logged context text back out 
    if status_code == -1:
        try:
            params = json.loads(job['params'] or '{}')
            response_payload['error_message'] = params.get('error_log', "API pipeline error.")
        except Exception:
            response_payload['error_message'] = "Failed parsing background configuration details."
            
    return jsonify(response_payload)

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