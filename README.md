# Edge Data Center Feasibility Evaluator

Hackathon MVP: compare **edge data center** viability vs **rooftop solar** for commercial properties. Sales-facing UI with transparent scoring.

## Stack

- **Frontend:** Next.js 15, TypeScript, Tailwind (`frontend/`)
- **Backend:** FastAPI (`backend/`)
- **Data:** Nominatim (geocode), HIFLD substations (ArcGIS), OSM Overpass (residential + schools in 500 m)

## Quick start

**Backend**

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

**Frontend**

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). The app proxies `/api/backend` to the API (see `frontend/next.config.ts`).

## License

Project hackathon code — use and adapt as needed.
