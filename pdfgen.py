import json
import subprocess
import os
import re
from jinja2 import Environment, FileSystemLoader

# Hardcoded template name
TEMPLATE_NAME = os.path.join("resume_json", "base.tex")

def tex_escape(text):
    """
    Finds and escapes special LaTeX characters in a plain text string.
    """
    if not isinstance(text, str):
        return text
    
    conv = {
        '\\': r'\textbackslash{}',
        '&': r'\&',
        '%': r'\%',
        '$': r'\$',
        '#': r'\#',
        '_': r'\_',
        '{': r'\{',
        '}': r'\}',
        '~': r'\textasciitilde{}',
        '^': r'\textasciicircum{}',
    }
    
    pattern = '|'.join(re.escape(str(key)) for key in sorted(conv.keys(), key=lambda item: -len(item)))
    regex = re.compile(pattern)
    
    return regex.sub(lambda match: conv[match.group()], text)

def escape_data_recursively(data):
    """
    Recursively travels through the JSON structure (lists and dicts)
    and escapes all string values, while keeping dictionary keys intact.
    """
    if isinstance(data, dict):
        return {key: escape_data_recursively(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [escape_data_recursively(item) for item in data]
    elif isinstance(data, str):
        return tex_escape(data)
    return data

def generate_pdf(json_path, target_pdf_path):
    """
    Generates a PDF from a JSON data file and a hardcoded LaTeX template.
    
    :param json_path: Path to the input JSON file.
    :param target_pdf_path: The full expected output path for the PDF (e.g., 'output/my_resume.pdf').
    """
    # 1. Load the JSON data
    with open(json_path, 'r', encoding='utf-8') as f:
        raw_data = json.load(f)
        
    # 2. Sanitize and escape all special characters
    data = escape_data_recursively(raw_data)

    # 3. Locate the hardcoded template relative to this script's directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    env = Environment(
        loader=FileSystemLoader(script_dir),
        comment_start_string='((--',  
        comment_end_string='--))'     
    )
    
    try:
        template = env.get_template(TEMPLATE_NAME)
    except Exception as e:
        print(f"Error loading template '{TEMPLATE_NAME}' from {script_dir}: {e}")
        return

    # 4. Render the LaTeX code
    rendered_tex = template.render(
        Skillset=data.get("Skillset", []),
        Work_experience=data.get("Work experience", {}),
        Projects=data.get("Projects", {})
    )

    # 5. Extract output directory, filename, and base name
    target_pdf_path = os.path.abspath(target_pdf_path)
    output_dir = os.path.dirname(target_pdf_path)
    pdf_filename = os.path.basename(target_pdf_path)
    
    # Strip .pdf extension if the user included it, to get the base name for aux files
    base_name = os.path.splitext(pdf_filename)[0]
    
    # Ensure the target directory exists
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Define paths for compilation (run in the output directory to keep things clean)
    tex_filename = f"{base_name}.tex"
    tex_filepath = os.path.join(output_dir, tex_filename)
    
    with open(tex_filepath, "w", encoding="utf-8") as f:
        f.write(rendered_tex)

    try:
        # Run pdflatex inside the target directory
        for _ in range(2):
            subprocess.run(
                ["pdflatex", "-interaction=nonstopmode", tex_filename],
                check=True,
                capture_output=True,
                cwd=output_dir  # Changes working directory for the command
            )
        print(f"Successfully generated {target_pdf_path}")
        
    except subprocess.CalledProcessError as e:
        print("LaTeX Error Output:")
        print(e.stderr.decode('utf-8', errors='ignore'))
        
    finally:
        # Cleanup auxiliary files in the target directory
        for ext in [".aux", ".log", ".out", ".tex"]:
            aux_file = os.path.join(output_dir, base_name + ext)
            if os.path.exists(aux_file):
                os.remove(aux_file)