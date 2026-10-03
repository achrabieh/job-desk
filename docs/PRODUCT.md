# Job Desk — product options and plan (29 Sep 2026)

## What exists today (v0.1)
A local tool: daily curated picks, human approval, truthful tailoring from a fact bank, drafted form answers, one-page CV builder with clean metadata. It runs on the user's own Claude plan, Windows and Word. It has been used for real applications (8 submitted or approved in the first four days).

## The three options
| | A. Share the repo | B. Desktop app (.exe) | C. Hosted web app |
|---|---|---|---|
| Who can use it | Technical friends | Anyone on Windows/Mac | Anyone, any device |
| Setup for a user | 30–60 min (Claude Code, Python, Word) | Install + sign in | Sign up |
| AI cost | Each user's own Claude plan | Theirs (bring-your-own key) or yours | Yours, per user |
| Revenue | None | Licence, hard to enforce | Subscription |
| Build effort | Done | 3–6 weeks | 8–12 weeks to a solid beta |
| Main risk | Friction | Packaging + support without revenue | Cost per user, data privacy, job-data sourcing |

**Recommendation: A now, C next, skip B.** A desktop app carries most of the cost of a web app without its reach or revenue. Use A to learn whether people keep using it, then build C once the answer is yes.

## Stage 0 — friends beta (now, 2–3 weeks)
- Give the repo to 3–5 friends. Help each set up their profile in one sitting.
- Measure per person per week: picks shown, approval rate, applications submitted, interviews, time spent.
- Success bar to move on: most testers still using it in week 3, and at least a couple of interviews credited to it.

## Stage 1 — hosted beta (after Stage 0, 8–12 weeks)
Full design: [docs/HOSTED.md](HOSTED.md). Beta process and bar: [docs/BETA.md](BETA.md).
The key design change: **search once, match many.** Today every user's agent browses the web separately, which is slow and too expensive to host. A hosted version should:
1. **Ingest jobs centrally** every day from public, permitted sources: company ATS boards with public JSON (Greenhouse, Lever, Ashby, Workable, SmartRecruiters), regional boards with APIs or feeds, and employer career pages. Store them in one database. Avoid LinkedIn and other sites whose terms forbid scraping.
2. **Match per user cheaply:** embeddings and filters narrow thousands of jobs to a few dozen, then an LLM ranks and writes the card for the top 5.
3. **Tailor on approval only** (as v0.1 does), using the Claude API.
4. **Build CVs without Word:** render from an HTML template to PDF (headless Chromium) so it runs on a server.

Suggested stack: Next.js front end; Supabase (Postgres, auth, file storage) or Firebase if you prefer its tooling (Postgres suits job data and matching better); Claude API for ranking, cards and tailoring; Python workers for ingestion on a daily schedule; Stripe when charging.

## Where it can win
- **GCC focus:** regional boards, Arabic postings, local salary norms (monthly all-in packages, housing and transport), nationalisation filters (Saudisation, Emiratisation), relocation within the Gulf. Global tools handle these poorly.
- **Truthful tailoring:** a fact bank plus automatic checks (no numbers or claims outside it). Many AI CV tools invent experience.
- **Curated, not spray-and-pray:** 4–5 good jobs a day with human approval, instead of mass auto-applying, which employers increasingly filter out.
- Competitors to study: Teal, Jobscan, Simplify, Huntr (tracking and tailoring); LazyApply and similar (auto-apply, low quality).

## Things to settle before charging anyone
1. **Owning entity.** Decide which legal entity owns and operates a hosted, paid service before charging anyone.
2. **Personal data.** CVs are personal data under Saudi PDPL, UAE data-protection law and GDPR (EU). Needs a privacy policy, consent, deletion on request, and careful choice of hosting region.
3. **Job-data rights.** Use only sources that allow reuse; link out to the original posting for applying.
4. **Unit economics.** Measure real AI cost per active user in Stage 1 before setting a price. Tailoring only on approval and central ingestion are the two big levers.
5. **No overclaiming.** Don't promise "undetectable by AI". Promise truthful, well-targeted applications.

## Near-term roadmap (repo)
- [x] Tailor only on approval; queue with retry
- [x] Clean document metadata
- [x] Generic CV builder and generic prompts
- [x] Profile onboarding assistant: turns an existing CV into the four profile files plus a short question list
- [x] Automatic fact check after every tailoring run (numbers and names must appear in the approved sources or the posting). Known limit: a name that appears anywhere in the fact bank passes even in a new context (e.g. "Google" when the bank only mentions a Google certificate).
- [x] Outcome tracking (interview, offer, rejected), funnel with interview rate
- [x] Follow-up reminders 7 days after applying or after the last follow-up
- [x] Learn from outcomes: favour tracks and companies that produced interviews, rest companies that rejected for 60 days
- [x] Public job-feed ingestion (`jobdesk/ingest.py`): Greenhouse, Lever, Ashby, Workable, SmartRecruiters; first step toward the hosted "search once, match many" index
- [x] Feed directory: `docs/feeds.json`, verified feeds with Gulf role counts
- [x] Teamtailor feeds (RSS)
- [x] Workday feeds (public search endpoint behind each career site; optional search term per board)
- [x] Cross-platform command line (`jobdesk/cli.py`); PDF via Word or LibreOffice
- [x] Automated tests and CI
