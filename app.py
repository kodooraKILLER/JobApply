import sqlite3
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)
DB_FILE = "jobs.db"

def get_db_connection():
    # This connects to the file; if it doesn't exist, it creates it
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row  # This allows accessing columns by name
    return conn

# Create the table if it doesn't exist (Runs once on startup)
def init_db():
    with get_db_connection() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name TEXT NOT NULL,
                designation TEXT NOT NULL,
                job_description TEXT,
                job_url TEXT,
                status TEXT DEFAULT 'viewed'
            )
        ''')
        conn.commit()



@app.route('/')
def index():
    return render_template('index.html')

@app.route('/jobs', methods=['GET'])
def get_jobs():
    conn = get_db_connection()
    jobs = conn.execute('SELECT * FROM jobs').fetchall()
    conn.close()
    # Convert rows to list of dicts for JSON
    return jsonify([dict(job) for job in jobs])

@app.route('/add_job', methods=['POST'])
def add_job():
    data = request.get_json()
    conn = get_db_connection()
    conn.execute('''
        INSERT INTO jobs (company_name, designation, job_description, job_url)
        VALUES (?, ?, ?, ?)
    ''', (data['company_name'], data['designation'], data['job_description'], data['job_url']))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"}), 201

if __name__ == '__main__':
    init_db()
    app.run(debug=True)