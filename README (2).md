# Health Prediction App

A small Streamlit application for managing patient blood test records. When a record is saved, its glucose, haemoglobin and cholesterol values are sent to an external AI service (the Google Gemini API). The short assessment that comes back is stored in the record's **Remarks** field.

This is a software-integration project. The AI output is an informational risk assessment, **not a medical diagnosis**, and the app is not suitable for real patient data.

## Features

- Create, read, update and delete patient records, stored persistently in SQLite
- Validation with clear error messages, run before any AI request is made
- Date of birth accepted as `dd/mm/yyyy` or `dd.mm.yyyy`
- AI remarks generated when a record is created
- On update, remarks are regenerated only when a blood value changes (an email-only change does not call the API)
- If the AI request fails, nothing is saved and the user can simply submit again
- Confirmation step before a record is deleted
- Dashboard with the record count and average blood values

## Technology stack

| Layer | Technology |
|---|---|
| Backend | Python 3.10 or newer |
| Frontend | Streamlit |
| Database | SQLite (standard-library `sqlite3`) |
| AI | Google Gemini API, called over REST with `requests` |
| Configuration | `python-dotenv` (`.env` file) |
| Tests | `pytest` |

## Project structure

```
health-prediction-app/
├── app.py            # Streamlit interface and the create/update handlers
├── database.py       # SQLite create, read, update, delete
├── validation.py     # Input validation rules
├── ai_service.py     # Gemini API client
├── test_app.py       # Automated tests
├── requirements.txt  # Python dependencies
├── .env.example      # Placeholder configuration (copy to .env)
├── .gitignore
└── README.md
```

How the parts connect: `app.py` collects the form input and passes it to `validation.py`. If it is valid, `app.py` asks `ai_service.py` for the remarks and then saves the record with `database.py`. The three helper modules know nothing about Streamlit.

## Installation

```bash
git clone <your-repository-url>
cd health-prediction-app

# create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows (PowerShell): .venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

## Configure the API key

1. Create a Gemini API key in [Google AI Studio](https://aistudio.google.com/apikey).
2. Copy the example file: `cp .env.example .env` (Windows: `copy .env.example .env`).
3. Open `.env` and replace `your_gemini_api_key_here` with your key.

| Variable | Purpose | Default |
|---|---|---|
| `GEMINI_API_KEY` | Your Gemini API key (required) | none |
| `GEMINI_MODEL` | Gemini model to use | `gemini-3.8-flash` |
| `DB_PATH` | Location of the SQLite file | `patients.db` |

`.env` is listed in `.gitignore` and must never be committed. The `.env` file is read when the app starts, so restart the app after changing it. If Google retires or renames the model, set `GEMINI_MODEL` to a current model name; no code change is needed.

## Run the application

```bash
streamlit run app.py
```

Open the address Streamlit prints (normally http://localhost:8501).

Run the automated tests with:

```bash
python -m pytest -v
```

The tests never call the real Gemini API.

## Database

SQLite stores everything in one file, `patients.db`, created automatically in the project folder on first run. Records stay available after the app is restarted. The file is git-ignored because it holds patient data.

Table `patients`:

| Column | Type | Notes |
|---|---|---|
| id | INTEGER | primary key, auto-increment |
| full_name | TEXT | |
| date_of_birth | TEXT | stored as `yyyy-mm-dd`, shown as `dd/mm/yyyy` |
| email | TEXT | |
| glucose | REAL | mg/dL |
| haemoglobin | REAL | g/dL |
| cholesterol | REAL | mg/dL |
| remarks | TEXT | text returned by the AI API |

All queries use `?` placeholders. There is no unique constraint, so identical records can be saved separately.

## AI integration

`ai_service.generate_remarks(glucose, haemoglobin, cholesterol)` does the following:

1. Reads `GEMINI_API_KEY` from the environment. If it is missing, an error is raised before any request is made.
2. Builds a prompt that contains only the three blood values. The function has no parameters for a name, email or date of birth, so none can be sent.
3. Sends a `POST` request to  
   `https://generativelanguage.googleapis.com/v1beta/models/<model>:generateContent`  
   with the headers `x-goog-api-key` and `Content-Type: application/json`, and a 30 second timeout. The body contains `contents` (the prompt), `generationConfig.maxOutputTokens` and `generationConfig.thinkingConfig.thinkingLevel` (`low`, so the short answer is not cut off by the thinking budget). `temperature` is deliberately not sent because current Gemini models ignore it.
4. Reads the answer from `candidates[0].content.parts[*].text` and returns it unchanged apart from trimming whitespace. That text is what is stored in Remarks.
5. Raises `AIServiceError` with a readable message for: missing key, timeout, network failure, HTTP 400/401/403 (bad key or request), 404 (unknown model), 429 (rate limit), 5xx (service unavailable), blocked prompts, responses that stop early (`finishReason` other than `STOP`), empty text and malformed JSON.

When an error is raised the interface shows it and saves nothing, so no remark is ever made up. The prompt asks the model to describe each value, give an overall risk level in plain English and end by saying the result is informational and not a medical diagnosis. The interface also repeats that notice next to the remarks.

The default model name follows Google's published Gemini model documentation. The exact model and request format should be confirmed with your own API key, because model availability depends on your account and region.

## Input validation rules

| Field | Rule |
|---|---|
| Full Name | Must not be empty |
| Email | Must look like `name@domain.tld` |
| Date of Birth | Must be a real calendar date in `dd/mm/yyyy` or `dd.mm.yyyy`; must not be in the future; year must be 1900 or later |
| Glucose, Haemoglobin, Cholesterol | Must be numeric and greater than zero |

Invalid input is never corrected silently; the actual problem is shown. Leading and trailing spaces are ignored, and the date is converted to `yyyy-mm-dd` for storage.

## Known limitations

- Remarks come from an AI model, so the wording and risk level can differ between runs. They are not medical advice.
- Units are assumed to be mg/dL (glucose, cholesterol) and g/dL (haemoglobin); there is no unit conversion.
- The email check is a format check only and does not confirm the address exists.
- There is no login or access control, and the database is not encrypted.
- Free Gemini API tiers have rate limits.
- The automated tests replace the Gemini API and Streamlit with test doubles. The real API and the browser interface need to be checked manually.
