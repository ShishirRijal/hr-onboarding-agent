# NordTech HR web app

Chat interface for the HR onboarding agent. Next.js (App Router, Cache Components), TypeScript and Tailwind CSS.

```bash
npm install
npm run dev   # http://localhost:3000
```

The app calls `/api/*`, which `next.config.ts` proxies to the FastAPI backend (`HR_API_URL`, default `http://localhost:8010`). Start the API first — see the root README.

## Structure

- `src/app/sign-in/page.tsx` — sign-in; everything else needs a signed-in session
- `src/app/(employee)/page.tsx` — new chat
- `src/app/(employee)/c/[sessionId]/page.tsx` — an existing chat; history is loaded from the API
- `src/app/(employee)/profile/page.tsx` — the signed-in employee's profile
- `src/app/hr/` — the HR platform, for the HR team only: inbox with overview, one question with the answer form, answered questions, the anonymous answer review, and the Usage page
- `src/proxy.ts` — sends visitors without a session cookie to sign-in; the API checks the session itself
- `src/components/` — app shell and sidebars, chat view, messages with numbered citations and feedback, source panel, composer, HR inbox, question, review and usage views
- `src/lib/api.ts` — API client; a `401` from the API goes to sign-in
- `src/lib/session.tsx` — the signed-in user, loaded once per area
- `src/lib/app-state.tsx` — the user's chat list from the API, refreshed on focus and every minute so HR replies show up
- `src/lib/citations.ts` — finds the `[1]`, `[2]` citations in an answer, and strips them for previews

## Design

White and green palette defined as Tailwind theme tokens in `src/app/globals.css`, with neutral token names (`canvas`, `surface`, `muted`, `line`, `brand`) so the theme can change without touching components. Solid green (`brand`) is used for actions and links; the brighter green (`brand-bright`) only for decoration such as the assistant mark, progress and highlights, because white text on it is too low in contrast. Inter throughout, pill-shaped buttons. Orange is reserved for questions sent to HR.
