# Setting up your profile

After setup, let Job Desk draft your profile from your current CV (about 5 minutes):
```
python jobdesk/cli.py onboard --home ~/JobDesk --cv ~/Documents/CV.pdf --goals "What you want: roles, cities, industries, minimum pay"
```
It fills the four profile files below, builds a preview CV in `profile\_preview`, writes `profile\LINKEDIN.md` (a LinkedIn headline, About and experience draft from your facts), and writes `profile\QUESTIONS.md` with the few things only you can answer (salary, notice period, work authorisation, anything unclear). Answer those in the files it names, check the preview, and you're ready. The four files, if you want to adjust them:

1. **`cv_spec.json`** — your default one-page CV as structured data (name, contact, summary, roles with bullets, education, skills). The format is documented at the top of `jobdesk/cv/build_cv.py`. Check it builds:
   `python jobdesk/cv/build_cv.py ~/JobDesk/profile/cv_spec.json ~/JobDesk/test`
2. **`fact_bank.md`** — every fact a tailored CV may use, plus approved alternate bullets for different kinds of roles and your style rules. Nothing outside this file ever reaches a CV.
3. **`criteria.md`** — what to search for: locations, level, pay bar, tracks, exclusions, watchlist, scoring.
4. **`application_answers.md`** — your standard form answers and salary rules.

## Daily use
1. Run `python jobdesk/cli.py start --home <your folder>` (or double-click **Job Desk** on Windows). The page opens and today's search starts (about 10 minutes).
2. Read each card. Press **Apply** or **Skip** with a reason.
3. Approved jobs get a tailored CV, cover note and answers in a few minutes. Open the posting, upload the CV, paste what's asked, submit, then press **I submitted it**.

4. When a company replies, press **Got an interview** on the Submitted tab. An interview prep pack is built in 5–10 minutes; open it with **Interview prep** on the card. Record offers and rejections too; that's how the search learns.

## Troubleshooting
- First step for any problem: `python jobdesk/cli.py doctor --home ~/JobDesk` checks Python, Claude Code, the PDF exporter, your profile files, your default CV and your company feeds, and says what to fix.
- Every run writes two logs in `logs`: `<name>.log` (the run's report) and `<name>.audit.log` (every file it read or wrote, every command it ran, every page it fetched). Check the audit log if anything looks off.
- Page doesn't load: run the start command again, or check `logs` in your data folder.
- A CV build failed: press **Retry CV** on the card; the log is `logs\tailor-<job>.log`.
- Rerun today's search: `scripts\run_daily.ps1 -Force`.

## Referral links
Add your schools and past employers to `config.json` and each card shows one-click LinkedIn people searches for that company:
```
"networks": ["Your University", "Your Business School", "Past Employer"]
```
They are plain links you open yourself; only the company and network names go into the search.

## Using your own CV template
If you already have a Word CV whose look you want to keep, you can plug in your own builder instead of the generic one. Add to `config.json` in your data folder:
```
"cv_builder": "cv/my_builder.py",
"cv_spec": "my_default_cv.json"
```
The builder must accept `<spec.json> <output_dir> --name <File_Name>`, write `<File_Name>.docx` and `.pdf` into the output folder, exit 0 when the PDF is one page and 2 when it is longer, and document its spec format at the top of the file. Paths are relative to your data folder.

## Opening the page from your phone (optional)
The page only answers on this computer by default. To reach it from your phone privately, use a private network such as Tailscale (never expose it to the public internet):
1. On the PC: `tailscale serve --bg 8765` (the page becomes reachable only inside your own tailnet, at `https://<pc-name>.<tailnet>.ts.net`).
2. In `config.json`, allow that name: `"allowed_hosts": ["<pc-name>.<tailnet>.ts.net"]`.
3. Open the address on your phone while signed in to the same tailnet.
Opening a CV folder only works on the PC itself.
