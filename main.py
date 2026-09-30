"""PocketSmart AI - FastAPI backend."""
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

import auth
import database as db
from gemini_utils import get_recommendations

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PLANNERS = {"home": "Home Interior Planner", "party": "Party Planner", "jewelry": "Jewelry Planner"}
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


@asynccontextmanager
async def lifespan(app):  # startup
    db.init_db()
    yield


app = FastAPI(title="PocketSmart AI", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
templates.env.filters["inr"] = lambda v: f"{float(v):,.0f}"


# ---------- auth helpers ----------
class NotLoggedIn(Exception):
    pass


@app.exception_handler(NotLoggedIn)
async def _redirect_to_login(request, exc):
    return RedirectResponse("/login", status_code=303)


def optional_user(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        header = request.headers.get("authorization", "")
        if header.lower().startswith("bearer "):
            token = header[7:]
    username = auth.decode_token(token) if token else None
    return db.get_user(username) if username else None


def current_user(user=Depends(optional_user)):
    if not user:
        raise NotLoggedIn()
    return user


def login_response(username):
    resp = RedirectResponse("/dashboard", status_code=303)
    resp.set_cookie("access_token", auth.create_token(username), httponly=True,
                    samesite="lax", secure=bool(os.getenv("RENDER")), max_age=43200)
    return resp


def render(request, name, user=None, status_code=200, **ctx):
    return templates.TemplateResponse(request, name, {"user": user, **ctx}, status_code=status_code)


# ---------- public pages ----------
@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def home(request: Request, user=Depends(optional_user)):
    return render(request, "home.html", user)


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return render(request, "auth.html", mode="register")


@app.post("/register")
async def register(request: Request):
    form = await request.form()
    username, email, password = (form.get("username", "").strip(), form.get("email", "").strip(),
                                 form.get("password", ""))
    error = None
    if len(username) < 3 or "@" not in email or len(password) < 6:
        error = "Username 3+ chars, valid email, password 6+ chars."
    elif db.get_user(username):
        error = "Username already taken."
    if error:
        return render(request, "auth.html", status_code=400, mode="register", error=error)
    db.create_user(username, email, auth.hash_password(password))
    return login_response(username)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return render(request, "auth.html", mode="login")


@app.post("/login")
async def login(request: Request):
    form = await request.form()
    username = form.get("username", "").strip()
    user = db.get_user(username)
    if not user or not auth.verify_password(form.get("password", ""), user["password_hash"]):
        return render(request, "auth.html", status_code=401, mode="login", error="Invalid username or password.")
    return login_response(username)


@app.get("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie("access_token")
    return resp


@app.post("/token")
def token(form: OAuth2PasswordRequestForm = Depends()):
    """JWT for API clients (Swagger /docs 'Authorize' button uses this)."""
    user = db.get_user(form.username)
    if not user or not auth.verify_password(form.password, user["password_hash"]):
        return JSONResponse({"detail": "Incorrect username or password"}, status_code=401)
    return {"access_token": auth.create_token(form.username), "token_type": "bearer"}


# ---------- session ----------
@app.get("/session-info")
def session_info(user=Depends(optional_user)):
    if not user:
        return {"logged_in": False}
    return {"logged_in": True, "user_id": user["id"], "username": user["username"]}


@app.get("/session-data")
def session_data(user=Depends(current_user)):
    recs = db.list_recs(user["id"], limit=500)
    counts = {k: sum(1 for r in recs if r["category"] == k) for k in PLANNERS}
    return {"username": user["username"], "total_recommendations": len(recs), "by_category": counts}


# ---------- dashboard / history ----------
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, user=Depends(current_user)):
    recs = db.list_recs(user["id"], limit=200)
    return render(request, "dashboard.html", user, recent=recs[:5], total=len(recs))


@app.get("/history", response_class=HTMLResponse)
def history(request: Request, user=Depends(current_user)):
    return render(request, "history.html", user, recs=db.list_recs(user["id"]))


@app.get("/recommendations-details/{rec_id}", response_class=HTMLResponse)
def recommendation_details(rec_id: int, request: Request, user=Depends(current_user)):
    rec = db.get_rec(user["id"], rec_id)
    if not rec:
        return RedirectResponse("/history", status_code=303)
    return render(request, "result.html", user, kind=rec["category"], title=PLANNERS[rec["category"]],
                  result=rec["result"], budget=rec["budget"])


# ---------- planners ----------
@app.get("/home-planner", response_class=HTMLResponse)
def home_planner(request: Request, user=Depends(current_user)):
    return render(request, "planner.html", user, kind="home", title=PLANNERS["home"])


@app.get("/party-planner", response_class=HTMLResponse)
def party_planner(request: Request, user=Depends(current_user)):
    return render(request, "planner.html", user, kind="party", title=PLANNERS["party"])


@app.get("/jewelry-planner", response_class=HTMLResponse)
def jewelry_planner(request: Request, user=Depends(current_user)):
    return render(request, "planner.html", user, kind="jewelry", title=PLANNERS["jewelry"])


async def generate(request, user, kind):
    form = await request.form()
    inputs = {k: (form.getlist(k) if k == "rooms" else form.get(k)) for k in form.keys() if k != "image"}
    try:
        budget = float(inputs.get("budget") or 0)
    except ValueError:
        budget = 0
    image = mime = None
    upload = form.get("image")
    if upload is not None and getattr(upload, "filename", ""):
        image, mime = await upload.read(), upload.content_type
    error = None
    if budget <= 0:
        error = "Please enter a valid budget."
    elif image and (mime not in IMAGE_TYPES or len(image) > 4 * 1024 * 1024):
        error = "Upload a JPG/PNG/WEBP image under 4 MB."
    if error:
        return render(request, "planner.html", user, status_code=400, kind=kind, title=PLANNERS[kind], error=error)
    inputs["budget"] = budget
    result = await run_in_threadpool(get_recommendations, kind, inputs, image, mime)
    db.save_rec(user["id"], kind, budget, inputs, result)
    return render(request, "result.html", user, kind=kind, title=PLANNERS[kind], result=result, budget=budget)


@app.post("/generate-home", response_class=HTMLResponse)
async def generate_home(request: Request, user=Depends(current_user)):
    return await generate(request, user, "home")


@app.post("/generate-party", response_class=HTMLResponse)
async def generate_party(request: Request, user=Depends(current_user)):
    return await generate(request, user, "party")


@app.post("/generate-jewelry", response_class=HTMLResponse)
async def generate_jewelry(request: Request, user=Depends(current_user)):
    return await generate(request, user, "jewelry")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)), reload=True)
