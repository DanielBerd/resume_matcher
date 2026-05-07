# Implementation Plan: Local Resume Matcher with Gemma

## 1. Project Overview
The goal of this project is to build an application that automatically ingests job opening emails, parses them, and matches them against a local repository of resumes. The core matching logic will rely on a locally hosted, lightweight Gemma model to ensure privacy and avoid API costs.

## 2. Architecture & Tech Stack
*   **Language:** Python (excellent ecosystem for document processing and AI)
*   **Email Ingestion:** Python's built-in `imaplib` or a service-specific API (like `google-api-python-client` for Gmail) to fetch emails.
*   **Document Parsing:** 
    *   PDFs: `pymupdf` (fitz) or `pypdf`
    *   DOCX: `python-docx`
*   **Local LLM Engine:** `Ollama` or `llama.cpp` (using `llama-cpp-python`). Ollama is recommended for ease of setting up Gemma locally.
*   **Data Storage:** Local SQLite database to keep track of parsed resumes, job descriptions, and match scores.
*   **Interface:** A Command-Line Interface (CLI) initially, with the option to expand to a lightweight web UI (e.g., using Streamlit or Gradio) later.

## 3. Core Workflows

### A. Resume Ingestion
1.  Read a predefined local folder containing resumes.
2.  Parse text from each resume file.
3.  (Optional but recommended) Use the local Gemma model to extract a structured summary or key skills from each resume to save processing time later.
4.  Store the parsed text/summary in the local database.

### B. Email Processing
1.  Connect to the email inbox and filter for new, unread emails that match job opening criteria (e.g., specific senders, keywords like "Job Opening", "Role").
2.  Extract the email body text.
3.  Clean the text to isolate the core job description and requirements.

### C. Matching Engine
1.  **Prompt Design:** Construct a prompt that includes the parsed job description and a candidate's resume (or resume summary).
2.  **Inference:** Ask the local Gemma model to evaluate the match. The prompt should ask for:
    *   A fit score (e.g., 1-10 or 1-100).
    *   A brief justification (matching skills vs. missing skills).
3.  **Iteration:** Loop through all available resumes for a given job description.
4.  **Ranking:** Store and sort the results based on the score.

## 4. Development Phases

### Phase 1: Foundation & Document Parsing
*   Set up the Python project environment and dependencies.
*   Implement text extraction for local resume files (PDF, DOCX).
*   Create a local SQLite database to store candidate information.

### Phase 2: Local LLM Setup
*   Install Ollama and pull a small Gemma model (e.g., `gemma:2b` or `gemma:7b` depending on your hardware limits).
*   Write Python code to interface with the local model API.
*   Test basic prompts for text summarization.

### Phase 3: Email Integration
*   Set up a script to securely connect to an email account via IMAP.
*   Fetch recent emails and extract the plain text body.
*   Implement basic filtering to ignore non-job emails.

### Phase 4: Matching Logic Implementation
*   Design the matching prompt.
*   Build the pipeline that takes an email, loops through the resumes, queries Gemma, and records the scores.
*   Implement basic rate-limiting/batching if necessary to manage local compute load.

### Phase 5: User Interface & Refinement
*   Create a CLI script or Streamlit dashboard to view incoming jobs and their top matching candidates.
*   Fine-tune prompts to improve the accuracy and formatting of the Gemma model's output.

## 5. Next Steps
Please review this plan. If it looks good, we can start with Phase 1: setting up the project and the document parsing logic. Do you have a preference for which email provider you will be using (e.g., Gmail, Outlook), and do you already have Ollama installed on your system?
