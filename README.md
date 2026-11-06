# Apply Better — local application tracker

A React + Tailwind CSS dashboard served by Python/FastAPI. No database or cloud services. All application data lives in one CSV; resumes are ordinary local files.

## Start

Requires Python 3.10+ and Node.js 20.19+.

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
npm install --prefix frontend
npm run build --prefix frontend
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000**. Python serves both the compiled frontend and API. Rebuild the frontend after editing it, then restart Python.

## Features

- Save company, job title, job URL, job description, applied date, status, and resume.
- Search application history, filter by status, and update status from application details.
- Preview PDFs in the website and download original resumes. DOC/DOCX files are download-only because browsers do not natively render Word documents.
- Dashboard: application total, interview count, offer count, response rate, daily applications for the last 14 days, and top five exact job titles.
- Export applications as CSV.
- Responsive layout, upload validation, and empty/loading/error states.

## Storage

On first launch the backend creates:

```text
data/
  applications.csv
  resumes/
    <application-id>.pdf
```

CSV fields: `id, company, job_title, job_link, job_description, status, applied_date, created_at, resume_name, resume_path, status_history`. Resume paths are relative to the data directory. The original filename is preserved separately. Back up the **entire `data/` folder together**. Override its location with the `TRACKER_DATA_DIR` environment variable. Data and resumes are excluded from Git.

Uploads support PDF, DOC, and DOCX up to 10 MB. PDF headers are validated. CSV writes use a lock and atomic replacement; run one Python worker only. Do not edit the CSV while the app is writing to it. Export neutralizes spreadsheet formulas in user input.

This is a personal local application without authentication. Keep the server bound to `127.0.0.1`; sharing it publicly requires authentication and deployment hardening. No example applications are mixed into real data.

## Frontend development

Run Python as above and, in another terminal:

```sh
npm run dev --prefix frontend
```

Open the Vite URL shown in the terminal. Vite proxies `/api` to Python on port 8000.

## API

- `GET /api/applications` — history
- `POST /api/applications` — multipart application form and resume
- `PATCH /api/applications/{id}` — JSON `{ "status": "Interviewing" }`
- `GET /api/applications/{id}/resume` — inline file; add `?download=true` for download
- `GET /api/export` — CSV download

Test the storage and API flow with `.venv/bin/python -m unittest discover -s tests -v` after installing dependencies.

## Status history and application flow

Statuses include Applied, Online Assessment, Interviewing, Offer, Rejected, Ghosted, and Withdrawn. Changing a status appends a dated event to `status_history`, a JSON field in the same CSV. No extra database or history file is needed.

Open application details to view the history or use **Edit history** to backfill stages in chronological order. The last stage sets the current status. Backfilled stages have no invented dates. Existing records without history show their known status and a **Prior stages unknown** branch; earlier assessment/interview stages are not inferred.

The Sankey follows recorded paths. A rejection after assessment stays separate from a rejection after interview. Pending assessments and interviews have in-progress endpoints so counts balance. Ghosted is selected manually; no automatic time-based inference is made.

Older CSVs migrate automatically at Python startup: missing history columns or empty histories are written to disk. The original file is preserved as `data/applications.csv.pre-history.bak`. Only the known current status is recorded for legacy records; its event date remains unknown. Existing histories remain unchanged.

## Resume Builder

Open **Resume Builder** from the sidebar. Hover over the document and click its text to edit it directly. Changes autosave about one second after editing pauses, including new resumes. **Save resume** still saves immediately. The status shows pending/saving/saved or a retry option on failure; newer edits are preserved if an earlier request finishes late. Reusable drafts appear in the saved-resumes dropdown.

- Inline edits cover name, contacts, summary, entry titles, organizations, dates, bullets, and skills. Contact URLs and optional professional title are available under **Contact details & links**.
- Hover over an entry to remove it, move it, or edit its location. Hover over a bullet to add, reorder, or remove it; Enter adds the next bullet.
- The left panel adds/hides sections and changes their order via dragging or arrow buttons. Hidden section content is retained so it can be restored. Optional sections include volunteering, achievements, certifications, and publications.
- Formatting controls include compact/classic templates, Times New Roman/Arial/Georgia, font size, alignment, line spacing, section spacing, margins, and Letter/A4/Legal paper.
- Undo/redo buttons and Ctrl/Cmd+Z, Ctrl/Cmd+Shift+Z, Ctrl/Cmd+Y are supported. Ctrl/Cmd+S saves. **Save a copy** creates a separate draft.
- **Download PDF** exports current content, including unsaved edits, with the selected formatting and automatic pagination. **Preview PDF** displays the actual generated file to check final line wrapping and page breaks; the inline editor displays fixed-size sheets with automatic overflow, visible page breaks, and a live page count.
- Page-break decorations are kept out of saved text. Drafts are local files in `data/resume_drafts/<id>.json`. Applications continue to use the single `applications.csv`. Download a resume and upload it with an application to preserve the version used for that job.
- Unsaved edits remain when navigating between app sections. Refresh/close warns if edits have not yet been saved successfully.

After updating an older checkout, install `requirements.txt`, rebuild the frontend, and restart Python to load the updated schema and PDF generation.

Builder API: `GET/POST /api/resume-drafts`, `PUT /api/resume-drafts/{id}`, and `POST /api/resume-drafts/pdf`.

Checks: `npm run test:builder --prefix frontend`, `npm run test:render --prefix frontend`, and `.venv/bin/python -m unittest discover -s tests -v`.

### Import a resume

Use **Upload resume** in Resume Builder to import a text-based PDF or DOCX (up to 10 MB and 30 PDF pages). Extraction runs locally in Python. The result is saved as a new editable draft; existing saved resumes are preserved. Import recognizes common contact information, links, section headings, dated entries, education, and bullets. Review the grouping before exporting: multi-column or unusual layouts may need corrections. The original extracted text is retained under **View extracted text**. Scanned PDFs need OCR first; older `.doc` files must be converted to `.docx`. Imported resumes use the builder’s default formatting rather than replicating the source design.
# Apply-Better
# Apply-Better
