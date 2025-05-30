# Legal PDF Metadata Extractor

This project is a Flask-based web application for parsing PDF documents, extracting structured content (paragraphs, tables, figures), and generating legal metadata (e.g., dates, persons, references to clauses/articles/acts).

## Features

- Upload PDF files via a web interface
- Extract:
  - Paragraphs with bounding boxes
  - Tables (in text and HTML)
  - Figures with captions
- Generate metadata:
  - Document date and multiple date formats
  - Named persons
  - References to letters, clauses, articles, acts
- Save parsed content and metadata as JSON

---

## Setup Instructions

### 1. Clone the Repository

```bash
git clone https://github.com/your-username/legal-pdf-parser.git
cd legal-pdf-parser
