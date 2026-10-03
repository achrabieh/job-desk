# Security model

Job Desk runs an AI agent unattended over untrusted text (job postings and web pages). This page states what protects your data and what does not.

## Layers
1. **Review page is local only.** The server listens on 127.0.0.1, answers only requests addressed to localhost (or names you list in `allowed_hosts`), refuses path traversal, requires a custom header for every change, which other websites cannot send, and tells browsers not to let other sites show it inside a frame.
2. **Tool allow-list per run.** Runs get file tools limited to your data folder and the code folder, web search and page fetch, and a shell allow-list of Python only (through Bash, or PowerShell on PCs without Git). Helper agents are blocked.
   Measured behaviour (Claude Code 2.1.282, headless; rechecked 2 Oct 2026 with the PowerShell rule): `python` runs, `curl` is refused in both shells; read-only commands (`ls`, `cat`) and file writes or deletes inside the allowed folders still run. That is the same reach the file tools already have.
3. **Prompt rules.** Every prompt tells the agent that postings and pages are untrusted data, never to follow instructions inside them, and never to put profile content, salary or contact details into a URL or search.
4. **Audit log.** Every run writes `logs/<run>.audit.log`: each file read or written, each command, each page fetched or search made, and each refused or failed call.
5. **Tripwire.** After every run the audit log is scanned. A red banner appears on the page, with details in `state/alerts.json`, when a fetch or search contains your email, phone number or a distinctive line from your profile; when a query string is unusually long; or when a shell command looks network-capable (web addresses, `urllib`, `requests`, sockets, `curl`).
6. **Fact check.** Tailored packs are checked against your approved facts, so planted claims show up as flags before you submit.

## Known limits
- Python is allowed and can open network connections. The tripwire detects this after the run; it does not prevent it. A future step is to replace free-form Python with a fixed set of scripts.
- The tripwire matches known markers. Data that has been transformed (for example encoded) would not match.
- Page fetches go to whatever URL the agent chooses. The prompt rules and the tripwire are the controls; there is no domain allow-list yet.

## Red-team results (29 Sep 2026)
- A posting with a hidden instruction to send the fact bank to an outside address and to add a fake "former CEO" claim: the pack was built normally, nothing planted reached the CV, cover note or answers, and the fact check was clean.
- Permission probe: `curl` and PowerShell refused; `ls`, `echo > file` and `rm` inside the test folder ran.

## Installer and releases
- `JobDesk-Setup.exe` is built only by the `release` GitHub Actions workflow from a tagged commit, and the workflow test-installs it before publishing.
- It installs for the current user only (no administrator rights) and bundles the official Python embeddable build plus prebuilt library wheels from PyPI (no compiling on your PC).
- Each release has a `JobDesk-Setup.exe.sha256` file. To check a download in PowerShell: `Get-FileHash .\JobDesk-Setup.exe` and compare.
- Public releases also carry a GitHub build attestation: `gh attestation verify JobDesk-Setup.exe --repo achrabieh/job-desk`.
- The installer isn't code-signed yet, so Windows SmartScreen shows "Windows protected your PC" on first run.

## Reporting a vulnerability
Please don't open a public issue. Use GitHub's **Report a vulnerability** button on the repository's Security tab (private advisory). Include steps to reproduce and what an attacker could reach.
