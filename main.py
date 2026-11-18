"""Telemetry Sentinel FastAPI sunucusu.

Çalıştırma:  uvicorn main:app --reload
Arayüz:      http://localhost:8000
API belgesi: http://localhost:8000/docs
"""

import os
import time
from pathlib import Path

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from src.decision_engine import analyze, summarize
from src.parser import CsvFormatError, FleetError, load_fleet, parse_csv

BASE_DIR = Path(__file__).resolve().parent
FLEET_PATH = Path(os.environ.get("FILO_DOSYASI", BASE_DIR / "filo.json"))
MAX_UPLOAD_BYTES = 5 * 1024 * 1024

app = FastAPI(
    title="Telemetry Sentinel",
    description="Otobüs ile ana istasyon arasındaki veri kesintilerinin kaynağını bulur.",
    version="1.0.0",
)


def error_response(status_code, *messages, total=None):
    """Arayüzün tek biçimde gösterebileceği hata cevabı."""
    body = {"ok": False, "errors": list(messages)}
    body["total_errors"] = total if total is not None else len(messages)
    return JSONResponse(status_code=status_code, content=body)


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    """Beklenmeyen hatalarda kullanıcıya teknik döküm (stack trace) gösterilmez."""
    return error_response(500, "Beklenmeyen bir hata oluştu. Lütfen tekrar deneyin.")


def decode_upload(raw):
    """Yüklenen baytları metne çevirir; metin olmayan dosyaları reddeder."""
    if b"\x00" in raw:
        raise ValueError("Dosya metin (CSV) dosyası değil.")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        # Türkçe Windows/Excel varsayılan kodlaması
        return raw.decode("cp1254", errors="replace")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(BASE_DIR / "index.html")


@app.get("/ornek.csv", include_in_schema=False)
def sample_csv():
    return FileResponse(BASE_DIR / "ornek.csv", media_type="text/csv", filename="ornek.csv")


@app.get("/api/fleet")
def fleet_info():
    """filo.json içeriğini döndürür (arayüz otobüs ve sensör kartlarını buna göre çizer)."""
    try:
        fleet = load_fleet(FLEET_PATH)
    except FleetError as exc:
        return error_response(500, str(exc))
    return {"otobusler": list(fleet.buses), "sensorler": list(fleet.sensors)}


@app.post("/api/analyze")
async def analyze_csv(file: UploadFile = File(...)):
    """Kesinti CSV'sini analiz edip her kesinti parçası için arıza kaynağını döndürür."""
    if Path(file.filename or "").suffix.lower() != ".csv":
        return error_response(415, "Yalnızca .csv uzantılı dosyalar kabul edilir.")

    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        return error_response(413, "Dosya 5 MB sınırını aşıyor.")

    try:
        text = decode_upload(raw)
        fleet = load_fleet(FLEET_PATH)
    except (ValueError, FleetError) as exc:
        return error_response(400, str(exc))

    started = time.perf_counter()
    try:
        outages = parse_csv(text, fleet)
    except CsvFormatError as exc:
        return error_response(422, *(str(e) for e in exc.errors), total=exc.total)
    findings = analyze(outages, fleet)
    elapsed_ms = (time.perf_counter() - started) * 1000

    return {
        "ok": True,
        "record_count": len(outages),
        "elapsed_ms": round(elapsed_ms, 2),
        "summary": summarize(findings),
        "findings": [finding.to_dict() for finding in findings],
        "message": None if findings else "Kesinti bulunamadı.",
    }
