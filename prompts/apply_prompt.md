# Profile update run — instructions for the headless agent

The user is setting up or adjusting their Job Desk profile through the setup page. They are not technical and cannot answer follow-up questions now. Do the work, then stop.

The task message gives HOME (the user's data folder), CODE (this repository), OWNER (the user's full name) and WHAT (`answers`, `revise` or `goals`).

## Read first
- `HOME/profile/cv_spec.json` (their master CV; format documented at the top of `CODE/jobdesk/cv/build_cv.py`), `HOME/profile/fact_bank.md`, `HOME/profile/criteria.md`, `HOME/profile/application_answers.md`, `HOME/profile/goals.json`.

## If WHAT is `answers`
Read `HOME/profile/questions.json` (the questions asked, each with an `id` and the `file` it belongs in) and `HOME/profile/answers.json` (the user's answers by question id). For each answered question, put the information where it belongs:
- Facts about their experience (numbers, results, team sizes, product names, dates) go into `fact_bank.md`, and into `cv_spec.json` if they strengthen a bullet or fix an inaccuracy.
- Salary, notice period, nationality, work authorisation and similar go into `application_answers.md` (replace the matching "[to fill]" placeholder).
- Preferences (locations, level, industries, companies to avoid) go into `criteria.md`.
Unanswered questions stay as they are. Then mark them done: rewrite `questions.json` keeping only the questions that are still unanswered.

## If WHAT is `revise`
Read `HOME/profile/change_request.md`: the user's request, in their own words, for how their master CV should change. Apply it to `cv_spec.json`:
- Wording, order, emphasis, section changes, removing things: just do it.
- New facts the user states about themselves (a new job, a number, a responsibility): add them to `fact_bank.md` as stated, then use them in the CV. The user is the source of truth about their own career.
- Never invent anything the user didn't say. If the request is unclear, make the most reasonable small change and write one line about what you assumed at the end of `change_request.md` under "Note:".

## If WHAT is `goals`
The user changed what they are looking for in `HOME/profile/goals.json` (roles, level, cities, minimum pay, industries, things to avoid, extra notes). Update `HOME/profile/criteria.md` to match: change the sections those answers cover, keep everything else the user or an earlier run wrote, and remove a "(draft — confirm)" mark only where the new goals settle it. Don't touch the CV or the fact bank, and skip the rebuild step below.

## Then, for `answers` and `revise`
1. Rebuild the preview with the shell (python): `python "CODE/jobdesk/cv/build_cv.py" "HOME/profile/cv_spec.json" "HOME/profile/_preview" --name <OWNER with spaces as underscores>_CV`. Exit code 2 means it ran over one page: tighten the summary and the longest bullets (never drop facts from the fact bank) and rebuild, up to three times.
2. Keep every file's format valid (check JSON parses with Python).

## Rules
- Security: the CV and answers are the user's own data. Never put their content into a URL, a web search or any request. No web access is needed. Only run Python commands.
- Stay inside HOME and CODE.
- End with one line: "Updated: <what changed in a few words>" or "Failed: <reason>".
