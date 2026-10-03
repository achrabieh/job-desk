# Hosted Job Desk — design (Stage 1)

Status: design only. Build it after the friends beta clears the bar in `docs/BETA.md`.

## What changes from the local version
| | Local (today) | Hosted |
|---|---|---|
| Finding jobs | Each user's agent browses the web | One shared daily ingestion into a jobs table; per-user matching is cheap |
| AI | User's own Claude plan via Claude Code | Claude API on our key, metered per user |
| CV PDF | Word or LibreOffice on the user's PC | Server-side HTML template to PDF (headless Chromium) |
| Review page | localhost | Web app (and phone) with sign-in |
| Data | User's own folder | Our database, per-user encryption at rest |

## Components
1. **Ingestion worker** (Python, daily cron). Reuses `jobdesk/ingest.py` over the feed directory, plus permitted regional feeds. Normalises, de-duplicates across companies, stores postings with full text. Marks closed when a posting leaves its feed.
2. **Matcher** (per user, daily). Hard filters from the user's criteria (location, level, exclusions, age) in SQL, then embeddings similarity against the user's profile to get the top ~30, then one LLM call ranks them and writes the card text (about, why it fits, gaps, pay estimate) for the top 5–6. Wildcard and radar are separate small queries.
3. **Tailoring service** (on Apply). The current tailoring prompt, run through the Claude API with tool use (read posting, read fact bank, build CV JSON). The fact check (`factcheck.py`) runs server-side before the pack is shown.
4. **Web app**. Next.js. Sign-in (email magic link or Google), onboarding (upload CV, the onboarding prompt drafts the profile, the user answers the questions in a form), daily review page (today's page, ported), settings (criteria, feeds, salary rules).
5. **Billing**. Stripe subscriptions once charging.

## Data model (Postgres)
- `users` (id, email, name, created_at, plan)
- `profiles` (user_id, cv_spec jsonb, fact_bank text, criteria jsonb, answers jsonb, updated_at)
- `feeds` (id, company, ats, slug, search, active, last_ok_at)
- `postings` (id, feed_id, url unique, title, company, location, country, posted_at, closed_at, description, embedding vector)
- `picks` (id, user_id, posting_id, date, rank, tag, about, why jsonb, gaps jsonb, pay_estimate, pay_flag, score)
- `decisions` (pick_id, status, skip_reason, submitted_at, outcome_at, followed_up_at)
- `packs` (pick_id, cv_pdf_path, cv_spec jsonb, cover_note, qa jsonb, factcheck jsonb, built_at)
- `usage` (user_id, date, tokens_in, tokens_out, cost_estimate) for unit economics

## Cost levers (measure in the beta before pricing)
- Ingestion is shared: its cost does not grow with users.
- Matching: SQL filters and embeddings do most of the narrowing; one ranking call per user per day on ~30 short candidates.
- Tailoring only on Apply (typically 1–3 per user per day) is the main per-user AI cost; cache the fact bank and base CV as a reusable prompt prefix.
- Cap daily picks and tailorings per plan.

## Privacy and compliance
- CVs and salary data are personal data: Saudi PDPL, UAE PDPL, GDPR for EU users. Publish a privacy policy, collect consent, support export and deletion.
- Host in a region acceptable for Gulf users; encrypt profile fields at rest; never use user data to train models; don't share one user's data with another.
- Only ingest sources that permit reuse; always link to the original posting to apply.
- Don't promise that CVs are "undetectable by AI"; promise truthful, well-targeted applications.

## Milestones
1. Ingestion service + postings table filled daily for the feed directory (1–2 weeks). *Local version done: `jobdesk/postings_index.py` keeps the same table in SQLite; moving it to Postgres is the hosted step.*
2. Matcher producing picks for 3 beta users from their local profiles, compared against their local Job Desk picks (1–2 weeks).
3. Web app: sign-in, onboarding, review page, tailoring (3–4 weeks).
4. Closed beta with 10–20 users, usage metering, cost per active user measured (2–4 weeks).
5. Pricing and billing.

## Open decisions for the owner
- Which entity owns and operates the hosted service.
- Hosting region and provider.
- Free tier or trial only.
- Whether to keep a "bring your own Claude plan" local mode for power users.
