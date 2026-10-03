# Profile update run — instructions for the headless agent

The user is setting up or adjusting their Job Desk profile through the setup page. They are not technical and cannot answer follow-up questions now. Do the work, then stop.

The task message gives HOME (the user's data folder), CODE (this repository), OWNER (the user's full name), WHAT (`answers`, `revise`, `goals` or `design`), and the CV design the user chose: DESIGN (`own` = their own design, kept in `HOME/profile/design/master.html`; `jobdesk` = the built-in design), PHOTO (`keep`, `auto` or `remove`), PAGES (the page limit) and IMPROVED (`true` or `false`).

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

## If WHAT is `design`
The user chose to keep their own CV design (IMPROVED `false`) or to keep its look with its problems fixed (IMPROVED `true`). Read `HOME/profile/cv_spec.json` (their content), `HOME/profile/cv_review.json` (your review of their CV), and look at the original: Read the page images in `HOME/profile/_look/` (`page-1.png`, …).

Write `HOME/profile/design/master.html`, one self-contained HTML page that prints on A4:
- Inline CSS in a `<style>` block; `@page {size: A4; margin: …}`. No scripts and no external files except the photo. Use the fonts the original uses when they are standard (Calibri, Arial, Helvetica, Georgia, Cambria, Garamond, Times New Roman, Segoe UI), otherwise the closest standard font.
- IMPROVED `false`: reproduce the original as faithfully as you can: layout and columns, fonts, sizes, colours, section order and headings, bullet style, spacing, and where the photo sits. Same content and wording as `cv_spec.json`.
- IMPROVED `true`: keep the look (colours, fonts, style, photo) but fix the design problems in the review, e.g. columns that software misreads become one column, clutter gets white space, dates become consistent. Content problems may be fixed in wording, using fact-bank facts only; then update `cv_spec.json` so both say the same thing.
- PHOTO `keep` or `auto`: show the photo with `<img src="photo.jpg" alt="">` (use the real file name in `HOME/profile/design/`) where the original had it, or top right. PHOTO `remove`: no photo.
- Real text, real headings and `<ul><li>` bullets (no text inside images), so CV-reading software can read the PDF.
Build it with the shell (python): `python "CODE/jobdesk/cv/cv_tools.py" build "HOME/profile/design/master.html" "HOME/profile/_preview" --name <OWNER with spaces as underscores>_CV --max-pages PAGES --assets "HOME/profile/design"`. Read the PNG it reports and compare it with the original page image. Fix what differs or what looks broken (overlaps, cut-off text, an empty second page; exit code 2 means more than PAGES pages) and rebuild, up to four rounds. Skip the "Then" steps below.

## Then, for `answers` and `revise`
1. Rebuild the preview with the shell (python). DESIGN `jobdesk`: `python "CODE/jobdesk/cv/build_cv.py" "HOME/profile/cv_spec.json" "HOME/profile/_preview" --name <OWNER with spaces as underscores>_CV`; exit code 2 means it ran over one page. DESIGN `own`: first make the same change in `HOME/profile/design/master.html` (text only; keep its structure and styles), then `python "CODE/jobdesk/cv/cv_tools.py" build "HOME/profile/design/master.html" "HOME/profile/_preview" --name <OWNER with spaces as underscores>_CV --max-pages PAGES --assets "HOME/profile/design"` and Read the PNG it reports to check the page. If it runs over the page limit, tighten the summary and the longest bullets (never drop facts from the fact bank) and rebuild, up to three times.
2. Keep every file's format valid (check JSON parses with Python).

## Rules
- Security: the CV and answers are the user's own data. Never put their content into a URL, a web search or any request. No web access is needed. Only run Python commands.
- Stay inside HOME and CODE.
- End with one line: "Updated: <what changed in a few words>" or "Failed: <reason>".
