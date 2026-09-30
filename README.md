# PocketSmart AI — Smart Budget & Recommendation Assistant

FastAPI + Gemini + Jinja2. Home, Party and Jewelry budget planners with login, history and image upload.

## Run in VS Code
1. Open this folder in VS Code (File > Open Folder).
2. Terminal > New Terminal, then:
   ```
   python -m venv venv
   venv\Scripts\activate          # Windows   (Mac/Linux: source venv/bin/activate)
   pip install -r requirements.txt
   copy .env.example .env         # Mac/Linux: cp .env.example .env
   ```
3. Open `.env` and paste your key from https://aistudio.google.com/app/apikey
4. Start the server: `uvicorn main:app --reload`
5. Open http://127.0.0.1:8000  (API docs: /docs)

No key? The app still works and shows a default budget split (fallback mode).

## Deploy on Render
1. Push this folder to a GitHub repo (`.env` is git-ignored, so your key stays private).
2. Render dashboard > New > Blueprint (uses `render.yaml`) — or New > Web Service with:
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
3. Add environment variables: `GEMINI_API_KEY` (your key), `SECRET_KEY` (any long random text), `GEMINI_MODEL` = `gemini-2.5-flash`.
4. Deploy. Open the `.onrender.com` URL.

Note: Render free tier sleeps after inactivity and its disk is temporary, so the SQLite users/history reset on redeploy. For a permanent DB, attach a Render Postgres or a paid disk.

## Routes
`/register /login /logout /token /session-info /session-data /dashboard /home-planner /party-planner /jewelry-planner /generate-home /generate-party /generate-jewelry /history /recommendations-details/{id} /health`

## Files
`main.py` routes · `gemini_utils.py` prompts + Gemini + fallback · `auth.py` JWT/password · `database.py` SQLite · `templates/` Jinja2 pages · `static/style.css`
