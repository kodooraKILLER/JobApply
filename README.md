# JobApply - AI-Powered Resume Tailoring System

An intelligent resume tailoring application that uses **Google Gemini AI** to automatically customize resumes for job applications, generate PDFs, and provide an interactive comparison interface.

## 🎯 Features

- **AI-Powered Resume Tailoring**: Uses Google Gemini 2.5 Flash to intelligently adapt your base resume to match specific job descriptions
- **Real-time Resume Editor**: Side-by-side comparison view with direct editing capabilities
- **Automatic PDF Generation**: Generates ATS-friendly PDF resumes from tailored content using LaTeX
- **Job Tracking Dashboard**: Manage multiple job applications with status pipeline tracking
- **Clipboard Integration**: Quick copy functionality for resume paths
- **Async Processing**: Background resume generation to keep the UI responsive
- **Dark Theme UI**: Modern Bootstrap-based interface with smooth animations

## 📋 Tech Stack

**Backend:**
- Python 3.x with Flask
- SQLite for job tracking database
- Google Gemini API for AI resume tailoring
- LaTeX (pdflatex) for PDF generation
- Jinja2 templating engine

**Frontend:**
- HTML5, CSS3, JavaScript
- Bootstrap 5 for responsive design
- Diff2HTML for side-by-side comparison
- Diff.js for text diffing

## 🚀 Getting Started

### Prerequisites

- Python 3.8+
- LaTeX distribution (with `pdflatex` command available)
- Google Gemini API key
- pip (Python package manager)

### Installation

1. **Clone or download the project**
```bash
cd JobApply
```

2. **Install Python dependencies**
```bash
pip install flask google-genai jinja2
```

3. **Configure API Key**
Edit `config.py` and add your Google Gemini API key:
```python
GEMINI_API_KEY = "your-api-key-here"
```

4. **Run the application**
```bash
python app.py
```

5. **Access the web interface**
Open your browser and navigate to `http://localhost:5000`

## 📁 Project Structure

```
JobApply/
├── app.py                          # Flask application & API endpoints
├── pdfgen.py                       # PDF generation logic
├── config.py                       # Configuration (API keys)
├── base.tex                        # LaTeX template for resume
├── resume_json/
│   └── base.json                   # Base resume data
├── tailored_resumes/               # Generated tailored resumes
│   └── job_1_*.json
├── resumes/                        # Generated PDFs organized by job ID
│   └── {job_id}/
│       └── senthil_resume.pdf
├── templates/
│   ├── index.html                  # Job tracker dashboard
│   └── comparison.html             # Resume comparison editor
├── jobapply.db                     # SQLite database
└── .gitignore
```

## 🔑 Core Features Explained

### 1. Job Tracking Dashboard (`templates/index.html`)
- Add new jobs with company name, designation, description, and URL
- Track application status through pipeline stages
- Real-time resume generation indicator with rotating/glowing star animation
- Quick access to copy PDF resume paths

### 2. Resume Tailoring (`templates/comparison.html`)
- **Side-by-side comparison**: Base resume vs. tailored version
- **Interactive editing**: Directly modify tailored resume content
- **Transfer button** (>>): Copy base resume content to tailored version
- **Live validation**: JSON syntax checking with error feedback
- **Auto-save**: Debounced updates as you type

### 3. AI Tailoring System
The `tailor_resume_with_gemini()` function:
- Analyzes job descriptions for technical keywords
- Infuses relevant technologies into existing bullet points
- Preserves original resume structure (no deletions)
- Maintains company names without hallucination
- Returns enhanced JSON ready for PDF generation

### 4. PDF Generation (`pdfgen.py`)
- Escapes LaTeX special characters for safe rendering
- Renders resume data into professional LaTeX document
- Compiles to ATS-friendly PDF
- Automatic cleanup of intermediate files

## 💾 Database Schema

```sql
CREATE TABLE jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT NOT NULL,
    designation TEXT NOT NULL,
    job_description TEXT,
    job_url TEXT,
    status TEXT DEFAULT 'viewed',
    resume_path TEXT,
    resume_generated INTEGER DEFAULT 0
)
```

**Status Pipeline**: viewed → waiting for referral → applied → got interview call → being interviewed

## 🔌 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Main dashboard |
| GET | `/jobs` | Fetch all tracked jobs |
| POST | `/add_job` | Add new job (triggers background resume generation) |
| GET | `/resume/<job_id>` | Fetch tailored resume JSON |
| POST | `/update-resume/<job_id>` | Save edited resume and regenerate PDF |
| GET | `/resume-status/<job_id>` | Check if resume is generated |
| GET | `/fetch_resume_path/<job_id>` | Get absolute path to PDF resume |
| GET | `/base-resume` | Fetch base resume template |
| GET | `templates/comparison.html` | Resume comparison editor page |

## ⚙️ Configuration

### Environment Variables
Store sensitive data in `config.py`:
```python
GEMINI_API_KEY = "AIza..."
```

### LaTeX Customization
Edit `base.tex` to customize:
- Resume styling and layout
- Color scheme (currently black text on light background)
- Section formatting
- Contact information

## 🎨 UI Customization

Dark theme colors (in HTML files):
- Background: `#0f172a`
- Cards: `#1e293b`
- Primary accent: `#38bdf8`
- Success: `#10b981`
- Warning: `#fbbf24`

## 🐛 Troubleshooting

**PDF not generating?**
- Ensure `pdflatex` is installed: `pdflatex --version`
- Check LaTeX syntax in `base.tex`
- Review error logs in console output

**Resume not tailoring?**
- Verify GEMINI_API_KEY in `config.py`
- Check internet connection
- Review job description format

**Database errors?**
- Delete `jobapply.db` to reset (careful - loses job history)
- Ensure write permissions in project directory

## 📝 License

This project is personal and meant for educational purposes.

## 🤝 Contributing

Feel free to extend this project with:
- Multiple resume templates
- Additional tailoring strategies
- Export formats (DOCX, etc.)
- Interview preparation features
- Cover letter generation

---

**Built with ❤️ by Senthil Kumar R**

