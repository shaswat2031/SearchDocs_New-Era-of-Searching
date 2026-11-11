# SearchCore Frontend (Next.js + Tailwind CSS + Framer Motion)

Interactive search console and document management studio for the SearchCore FastAPI backend.

## Stack

- **Next.js 15** (App Router, configured for `output: "export"`)
- **React 19 + TypeScript**
- **Tailwind CSS v4** (`@tailwindcss/postcss`)
- **Framer Motion** (`layoutId` spring tabs/toggles, staggered KPI tiles & search results, inspector modal, toast notifications)
- **Lucide React** icons
- **Google Fonts** (`Plus Jakarta Sans`, `Inter`, `JetBrains Mono`) via `next/font/google`

## Development

1. Start the SearchCore Python backend from the repository root:
   ```bash
   uvicorn searchcore.api:app --reload
   ```
2. Start the Next.js dev server from `frontend/`:
   ```bash
   npm install
   npm run dev
   ```
3. Open `http://localhost:3000`.

By default on ports `3000` / `3001`, API calls and the `/docs` Swagger redirect target `http://127.0.0.1:8000`. To point at another backend URL, set `NEXT_PUBLIC_API_BASE`:

```bash
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000 npm run dev
```

## Static Export (Served Directly by FastAPI)

```bash
npm run build
```

This generates `frontend/out/`. When present, [`searchcore/api.py`](../searchcore/api.py) automatically mounts `/_next` and serves `frontend/out/index.html` at `http://127.0.0.1:8000/`.
