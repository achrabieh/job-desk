# Contributing

Thanks for helping. Job Desk is small on purpose: plain Python, one HTML page, prompts in Markdown.

## Ground rules
- **Truthful CVs only.** Never add features that invent experience, inflate numbers, or hide that a human applied. Tailoring may only reorder and reword facts from the user's fact bank.
- **No auto-applying and no scraping sites that forbid it.** Job Desk reads public job-board feeds and normal web pages; the user submits applications themselves.
- **No personal data in the repo.** Never commit a real CV, profile, picks or logs. Use the fictional examples in `profile.example/`.

## Development
```
python -m pip install -r requirements.txt pytest pyflakes
python -m pyflakes jobdesk tests
python -m pytest -q tests
```
Tests never start real AI runs (`JOB_DESK_NO_AGENTS=1`). CI runs on Windows, macOS and Linux.

## Good first contributions
- **New company feeds:** add verified entries to `docs/feeds.json` (company, ATS, slug). Check that the feed returns jobs with `python jobdesk/ingest.py`.
- **New ATS types:** add a parser to `jobdesk/ingest.py` with a fixture test in `tests/test_core.py`.
- **Closed-posting wording** for more job boards in `jobdesk/linkcheck.py`.
- **Translations** of the review page.

## Licence of contributions
By contributing you agree that your contribution is licensed under AGPL-3.0, and that the project maintainer may also offer the project, including your contribution, under other terms (for example to run a hosted version). This keeps the option of funding the project open while the code stays open source for everyone.

## Pull requests
One change per PR, with a test when the change has logic. Describe what a user will notice.
