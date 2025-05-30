import os
import re
import json
import pdfplumber
import spacy
from flask import Flask, request, render_template, jsonify
from werkzeug.utils import secure_filename
from datetime import datetime
from pathlib import Path

# Load SpaCy NLP model
nlp = spacy.load("en_core_web_sm")

# Setup Flask
app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "generated"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# --- Utilities ---
def extract_caption_from_page_text(text):
    if not text:
        return ""
    match = re.search(r"(Figure|Fig)[\s\-:]*(\d+)?[:\.\-]?\s*(.+)", text, re.IGNORECASE)
    return match.group(0) if match else ""

def find_page(text_snippet, parsed_doc):
    for el in parsed_doc["content"]:
        if text_snippet in el.get("text", ""):
            return el["page_number"]
    return -1

def is_valid_name(name):
    generic_terms = {"Contractor", "Request", "Works", "Milestones", "no.", "Name", "Company"}
    return name and name.strip() and name not in generic_terms

# --- Extraction Functions ---
def extract_elements_from_page(page, page_number):
    elements = []
    for block in page.extract_words():
        text = block["text"].strip()
        if text:
            elements.append({
                "type": "paragraph",
                "text": text,
                "page_number": page_number,
                "metadata": {"bbox": [block["x0"], block["top"], block["x1"], block["bottom"]]}
            })

    tables = page.extract_tables()
    for table in tables:
        table_text = "\n".join([" | ".join(row) for row in table])
        html_table = "<table>" + "".join(["<tr>" + "".join([f"<td>{cell}</td>" for cell in row]) + "</tr>" for row in table]) + "</table>"
        elements.append({
            "type": "table",
            "text": table_text,
            "html": html_table,
            "page_number": page_number,
            "metadata": {}
        })

    caption = extract_caption_from_page_text(page.extract_text())
    elements.append({
        "type": "figure",
        "image_filename": f"page_{page_number}.png",
        "caption": caption,
        "page_number": page_number,
        "metadata": {}
    })

    return elements

def parse_document(file_path):
    parsed = {"content": []}
    with pdfplumber.open(file_path) as pdf:
        for i, page in enumerate(pdf.pages):
            elements = extract_elements_from_page(page, i + 1)
            parsed["content"].extend(elements)
    return parsed

def extract_legal_metadata(parsed_doc, pdf_filename):
    metadata = {
        "document_name": pdf_filename,
        "document_date": "not found",
        "dates": [],
        "references": {
            "letters_mentioned": [],
            "laws_clauses_articles_acts": [],
            "persons": []
        }
    }

    all_text = " ".join(el.get("text", "") for el in parsed_doc["content"])
    doc = nlp(all_text)

    # Dates (multiple formats)
    date_patterns = [
        r"\b\d{4}-\d{2}-\d{2}\b",
        r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
        r"\b\d{1,2} [A-Za-z]+ \d{4}\b"
    ]
    found_dates = set()
    for pattern in date_patterns:
        for match in re.finditer(pattern, all_text):
            date_str = match.group(0)
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
            except:
                try:
                    dt = datetime.strptime(date_str, "%d/%m/%Y")
                except:
                    try:
                        dt = datetime.strptime(date_str, "%d %B %Y")
                    except:
                        continue
            iso = dt.strftime("%Y-%m-%d")
            found_dates.add((iso, match.start(), match.end()))

    for iso, start, end in sorted(found_dates):
        metadata["dates"].append({
            "date": iso,
            "surrounding_context": all_text[max(start-50, 0):end+50]
        })

    if metadata["dates"]:
        metadata["document_date"] = metadata["dates"][0]["date"]

    # Persons
    seen_persons = set()
    for ent in doc.ents:
        if ent.label_ == "PERSON" and is_valid_name(ent.text):
            name = ent.text.strip()
            if name not in seen_persons:
                seen_persons.add(name)
                metadata["references"]["persons"].append({
                    "name": name,
                    "page_number": find_page(name, parsed_doc)
                })

    # Letters
    for match in re.findall(r"Letter\s+(?:No\.|Number)?\s*([\w\-\/]+)", all_text, re.IGNORECASE):
        if is_valid_name(match):
            metadata["references"]["letters_mentioned"].append({
                "name": match,
                "page_number": find_page(match, parsed_doc)
            })

    # Clauses / Articles / Acts
    pattern = r"(Clause|Article|Act)\s+\d+(\.\d+)?"
    seen_clauses = set()
    for ref in re.findall(pattern, all_text):
        full_ref = f"{ref[0]} {ref[1] if ref[1] else ''}".strip()
        if full_ref not in seen_clauses:
            seen_clauses.add(full_ref)
            metadata["references"]["laws_clauses_articles_acts"].append({
                "reference": full_ref,
                "type": ref[0].lower(),
                "page_number": find_page(full_ref, parsed_doc)
            })

    return {"metadata": metadata}

# --- Flask Routes ---
@app.route("/", methods=["GET"])
def index():
    return render_template("upload.html")

@app.route("/upload", methods=["POST"])
def upload():
    uploaded_file = request.files.get("file")
    if not uploaded_file or uploaded_file.filename == "":
        return "No file uploaded", 400

    filename = secure_filename(uploaded_file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    uploaded_file.save(filepath)

    parsed = parse_document(filepath)
    metadata = extract_legal_metadata(parsed, filename)

    base = Path(filename).stem
    parsed_out = os.path.join(OUTPUT_FOLDER, f"{base}_parsed.json")
    meta_out = os.path.join(OUTPUT_FOLDER, f"{base}_metadata.json")

    with open(parsed_out, "w", encoding="utf-8") as f:
        json.dump(parsed, f, indent=2, ensure_ascii=False)
    with open(meta_out, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    return jsonify({
        "message": "✅ PDF processed successfully.",
        "parsed_file": parsed_out,
        "metadata_file": meta_out
    })

if __name__ == "__main__":
    app.run(debug=True)
