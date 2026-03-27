"""
FastAPI entrypoint — Edge Data Center Feasibility Evaluator.

Phase 1 wires real geocoding (Nominatim) to mocked HIFLD / OSM-derived metrics so the team can
demo a full request path without external dataset dependencies blocking the clock.
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from geocode import GeocodeError, geocode_address
from schemas import EvaluateRequest, EvaluateResponse
from scoring import evaluate_site

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Reserved for startup/shutdown hooks (HTTP client pools, cache warmers) in Phase 2."""
    yield


app = FastAPI(
    title="Edge Data Center Feasibility API",
    version="0.1.0",
    description="Scores commercial parcels for edge DC viability vs. rooftop solar positioning.",
    lifespan=lifespan,
)

# Browser origins that may call the API directly (when not using Next rewrites).
# Regex covers LAN dev URLs (e.g. http://192.168.1.83:3000) which otherwise hit CORS.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1|192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3})(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    """Load-balancer friendly probe."""
    return {"status": "ok"}


@app.post("/evaluate", response_model=EvaluateResponse)
async def evaluate(payload: EvaluateRequest) -> EvaluateResponse:
    """
    Resolve coordinates (map pin if provided, otherwise Nominatim), then score the site.
    """
    started = time.perf_counter()

    if payload.latitude is not None and payload.longitude is not None:
        lat, lon = float(payload.latitude), float(payload.longitude)
        coordinate_source = "user_pin"
    else:
        try:
            lat, lon, _hit = await geocode_address(payload.address.strip())
        except GeocodeError as exc:
            logger.info("Geocode failed: %s", exc)
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 — surface upstream HTTP / timeout errors clearly
            logger.exception("Geocode unexpected error")
            raise HTTPException(status_code=502, detail="Geocoding service unavailable") from exc
        coordinate_source = "geocoded"

    result = await evaluate_site(lat, lon)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    raw_addr = payload.address.strip()
    display_address = (
        raw_addr
        if raw_addr
        else "Location from map pin (add an address anytime for your records)"
    )
    return EvaluateResponse(
        address=display_address,
        coordinate_source=coordinate_source,
        processing_time_ms=elapsed_ms,
        **result,
    )


# Convenience for `python main.py` during the hackathon
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
