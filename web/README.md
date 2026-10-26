# NordTech HR web app

Chat interface for the HR onboarding agent. Next.js (App Router, Cache Components), TypeScript and Tailwind CSS.

```bash
npm install
npm run dev   # http://localhost:3000
```

The app calls `/api/*`, which `next.config.ts` proxies to the FastAPI backend (`HR_API_URL`, default `http://localhost:8010`). Start the API first — see the root README.

## Structure

- `src/app/page.tsx` — new chat
- `src/app/c/[sessionId]/page.tsx` — an existing chat; history is loaded from the API
- `src/components/` — sidebar, chat view, messages and sources, composer
- `src/lib/api.ts` — API client
- `src/lib/app-state.tsx` — session list and office, stored in the browser until there is login

## Design

Cool "Baltic light" palette defined as Tailwind theme tokens in `src/app/globals.css`. Familjen Grotesk for the interface and Source Serif 4 for the assistant's answers, so policy answers read like the documents they come from. Amber is reserved for questions sent to HR.
