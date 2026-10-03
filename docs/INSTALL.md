# Install Job Desk (Windows)

No technical skills needed. Allow about 15 minutes, most of it answering questions about yourself.

## What you need
- A Windows 10 or 11 PC that's on in the morning. A laptop is fine.
- A **Claude Pro or Max** plan (from claude.ai). Job Desk uses your own plan to read job posts and write your CVs. It doesn't charge you anything itself.
- Your current CV (PDF or Word).

## Steps
1. **Download** [JobDesk-Setup.exe](https://github.com/achrabieh/job-desk/releases/latest/download/JobDesk-Setup.exe).
2. **Open it.** Windows may show a blue box saying *"Windows protected your PC"*. That's because Job Desk is a free app without a paid publisher certificate. Click **More info**, then **Run anyway**.
3. Click **Install**. It needs no administrator password and installs only for you.
4. Job Desk opens in your web browser and walks you through the rest:
   - It installs Claude Code (one click) and asks you to sign in to your Claude account.
   - You upload your CV and say what job you want and where.
   - It reads your CV, asks a few questions, and builds a clean master CV for you to check.
   - You tick the companies you'd like to work for.
   - It runs your first search.

From then on, double-click **Job Desk** on your desktop whenever you want to see your picks. If you turn on the morning search in setup, new jobs are waiting each morning.

## Good to know
- **Your data stays on your PC**, in the *Job Desk* folder in your Documents. It's never uploaded anywhere except to Claude when it writes for you.
- **It never applies for you.** For each job you press Apply or Skip. Apply builds a tailored CV, a cover note and draft answers. You read them and submit on the company's site yourself.
- **Changing things later:** press **Profile & settings** at the top of Job Desk. You can upload a new CV, change what you're looking for or which companies to watch, switch Claude accounts, turn the morning search on or off, or start over.
- **Updating:** when a new version is out, Job Desk shows a banner. Press **Update now** and it installs itself and reopens. Your CV, settings and history are kept.
- **Uninstalling:** Windows Settings → Apps → Job Desk → Uninstall. This also stops the morning search. Your *Job Desk* folder in Documents is kept, so delete it yourself if you want everything gone.

## Something not working?
- **The page doesn't open:** double-click the Job Desk icon again, or go to http://127.0.0.1:8765 in your browser.
- **"Claude isn't signed in":** open Settings on the page and choose *Run the guided setup again*.
- Still stuck? Send the person who shared Job Desk with you the files in *Documents\Job Desk\logs*. They can include parts of your CV, so only send them to someone you trust.
