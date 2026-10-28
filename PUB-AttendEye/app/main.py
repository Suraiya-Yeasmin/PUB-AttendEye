"""PUB AttendEye - FastAPI application entry point."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import config
from .cv.service import face_service
from .database import SessionLocal, init_db
from .routers import (attendance, auth, classes, dashboard, enrollment, evaluation, recognition, reports,
                      review, settings, students)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("attendeye")

@asynccontextmanager
async def lifespan(_):
    init_db()
    with SessionLocal() as db:
        try:
            out = settings.apply_retention(db)
            log.info("Retention applied: %s", out)
        except Exception:  # noqa: BLE001
            log.exception("Retention job failed")
    st = face_service.status()
    log.info("Face service available=%s %s", st["available"], st["error"] or "")
    yield


app = FastAPI(title=config.APP_NAME, version=config.APP_VERSION, docs_url=None, redoc_url=None,
              openapi_url=None, lifespan=lifespan)


@app.middleware("http")
async def security_headers_and_csrf(request: Request, call_next):
    # CSRF defence in depth (cookie is SameSite=Strict): state-changing calls must carry a custom header.
    if request.url.path.startswith("/api/") and request.method not in ("GET", "HEAD", "OPTIONS"):
        if request.headers.get(config.CSRF_HEADER) != config.CSRF_VALUE:
            return JSONResponse({"detail": "Missing request header."}, status_code=403)
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    resp.headers.setdefault("Permissions-Policy", "camera=(self), microphone=()")
    resp.headers.setdefault("Content-Security-Policy",
                            "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
                            "media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'")
    if request.url.path.startswith("/api/"):
        resp.headers.setdefault("Cache-Control", "no-store")
    return resp


@app.exception_handler(StarletteHTTPException)
async def http_error(_, exc: StarletteHTTPException):
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error(_, exc: RequestValidationError):
    fields = {}
    for e in exc.errors():
        loc = [str(x) for x in e["loc"] if x not in ("body", "query")]
        fields[".".join(loc) or "request"] = e["msg"].replace("Value error, ", "")
    first = next(iter(fields.values()), "Invalid request.")
    return JSONResponse({"detail": {"message": first, "fields": fields}}, status_code=422)


@app.exception_handler(Exception)
async def unexpected(_, exc: Exception):
    log.exception("Unhandled error")  # message only; no request bodies (may contain face frames)
    return JSONResponse({"detail": "Unexpected server error. See the server log."}, status_code=500)


@app.get("/api/health")
def health():
    st = face_service.status()
    return {"status": "ok", "app": config.APP_NAME, "cv_available": st["available"], "cv_error": st["error"], "version": config.APP_VERSION}


for r in (auth, students, enrollment, classes, recognition, attendance, review, reports, evaluation,
          settings, dashboard):
    app.include_router(r.router)

app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(config.STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})
