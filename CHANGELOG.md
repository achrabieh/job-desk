# Changelog

## 0.6.0 — 29 Sep 2026
- Per-job notes (contacts, recruiter, dates), kept across status changes, searchable and exported.
- Gaps banner labels fixed for bullet-style answers.
- Onboarding also drafts a LinkedIn headline, About and experience section from the fact bank (`profile/LINKEDIN.md`).
- Cover letter as a one-page DOCX/PDF built from the fact-checked note (`jobdesk/cv/build_cover.py`); "Cover letter PDF" button on cards.

## 0.5.0 — 29 Sep 2026
- Feed tab: every role today's company feeds matched (not only the 4–5 picks), with one click to add any of them to your picks; duplicates of existing picks are hidden by company and title.

## 0.4.0 — 29 Sep 2026
- Desktop launchers on macOS and Linux; CI on Windows, Linux and macOS with pyflakes.
- Banner when the last search run failed or is still running.
- Postings index (`state/postings.db`, SQLite): every feed posting with first/last seen and closed dates; feed picks that leave their feed are marked closed without a page visit. Milestone 1 of docs/HOSTED.md, locally.
- `export` command: all picks and outcomes to an Excel workbook with a funnel sheet.
- Banner for standard answers left as placeholders; closed postings offer 'Skip (closed)' instead of Apply.

## 0.3.0 — 29 Sep 2026
- Settings tab: edit criteria, fact bank, standard answers and company feeds from the page (validated, with a .bak of the previous version); tabs can be opened by link (e.g. #settings).
- `doctor` command: checks the whole setup and says what to fix. Referral links per card. README screenshot.
- Interview prep packs: marking a job 'interview' researches the company and builds a pitch, likely questions with STAR outlines from the fact bank, gaps, numbers, salary position and questions to ask.
- Closed-posting detection before each daily run (HTTP 404/410, redirects to job lists, "no longer accepting" wording); cards labelled "Posting closed".
- Tripwire also flags network-capable shell commands; audit log records refused calls; `docs/SECURITY.md`.
- Same-day reruns write to their own batch folder; search box; optional `allowed_hosts` for private phone access.

## 0.2.0 — 29 Sep 2026
- Tailoring only when you press Apply (queue, retry, progress on the card).
- Fact check of every tailored pack against your approved facts; flags shown on the card.
- Outcome tracking: interview, offer, rejected; follow-up nudges; funnel; approvals that sit too long turn amber.
- Onboarding from an existing CV: drafts all profile files plus a short question list.
- Public job-feed ingestion: Greenhouse (US/EU), Lever, Ashby, Workable, SmartRecruiters, Teamtailor, Workday; 30-day filter; compact index; directory of 47 verified feeds.
- Cross-platform command line (`jobdesk/cli.py`): setup, onboard, start, daily, tailor, serve, stats.
- Pluggable CV builder so users can keep their own Word template.
- Security: localhost-only server, shell limited to Python, prompt-injection rules, per-run audit log, tripwire for personal data in outgoing requests.
- Tests and CI on Windows. Beta kit and hosted-version design.

## 0.1.0 — 29 Sep 2026
- Daily curated picks on a local review page, approval-triggered tailoring, generic one-page CV builder with clean document properties.
