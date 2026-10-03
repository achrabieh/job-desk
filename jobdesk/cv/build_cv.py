"""Build a one-page CV (DOCX + PDF) for anyone, from a structured spec.

Usage:
    python build_cv.py <spec.json> <output_dir> [--name Firstname_Lastname_CV]

No template file is needed: the layout is generated (single column, standard
headings, real bullets, tab-aligned dates) so applicant tracking systems and
AI screeners parse it cleanly. The PDF is exported by Microsoft Word when it is
installed (Windows); otherwise by LibreOffice if found. The script exits with
code 2 when the PDF runs past one page, so the caller can shorten and retry.

Spec:
{
  "name": "Firstname Lastname",
  "contact": ["City, Country", "email@example.com", "+000 00 000 0000"],
  "links": ["linkedin.com/in/you"],
  "summary": "Two to three lines.",
  "experience": [
    {"company": "Company, COUNTRY", "dates": "2023 – Present", "note": "optional italic line",
     "roles": [{"title": "Job title", "dates": "Mar 2026 – Present", "bullets": ["...", "..."]}]}
  ],
  "education": [
    {"school": "School, COUNTRY", "dates": "2022 – 2023", "degree": "MBA", "bullets": ["..."]}
  ],
  "skills": [["Languages:", "English (Native)"], ["Analytics:", "Excel, SQL"]],
  "style": {"font": "Calibri", "size": 9, "name_color": "0E2841", "band": "CAEDFB", "heading_fill": "F2F2F2",
            "margin_cm": 0.76, "surname_caps": true}   (optional; these are the defaults)
}
Exit codes: 0 ok (prints JSON with paths), 2 over one page, 1 error.
"""
import json
import os
import random
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import docx
from docx.enum.text import WD_TAB_ALIGNMENT, WD_PARAGRAPH_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor, Cm

# Default look ("classic"): navy name with the surname in capitals, grey contact line, letter-spaced
# section headings on a light-grey bar with a rule under them, light-blue employer bars with dates on
# the right, square bullets, justified text, narrow margins. Every value can be overridden in "style".
DEFAULT_STYLE = {"font": "Calibri", "size": 9, "name_color": "0E2841", "contact_color": "5A5A5A", "link_color": "467886",
                 "heading_fill": "F2F2F2", "heading_color": "000000", "band": "CAEDFB", "margin_cm": 0.76,
                 "surname_caps": True}


def style_of(spec):
    st = dict(DEFAULT_STYLE, **spec.get("style", {}))
    if "accent" in spec.get("style", {}) and "name_color" not in spec.get("style", {}):
        st["name_color"] = st["accent"]  # older specs
    return st


def display_name(name, st):
    parts = (name or "").split()
    if st.get("surname_caps") and len(parts) > 1:
        return " ".join(parts[:-1] + [parts[-1].upper()])
    return name or ""


def _shade(paragraph, hex_fill):
    ppr = paragraph._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_fill)
    ppr.append(shd)


def _bottom_border(paragraph, hex_color, sz="4"):
    ppr = paragraph._p.get_or_add_pPr()
    bdr = OxmlElement("w:pBdr")
    b = OxmlElement("w:bottom")
    for k, v in (("val", "single"), ("sz", sz), ("space", "1"), ("color", hex_color)):
        b.set(qn("w:" + k), v)
    bdr.append(b)
    ppr.append(bdr)


def _spacing(p, before=0, after=0, line=1.0):
    pf = p.paragraph_format
    pf.space_before, pf.space_after, pf.line_spacing = Pt(before), Pt(after), line


def _run(p, text, size, bold=False, italic=False, color=None, caps=False, spacing=None, underline=False):
    r = p.add_run(text)
    r.font.size = Pt(size)
    r.bold, r.italic = bold, italic
    if underline:
        r.underline = True
    if color:
        r.font.color.rgb = RGBColor.from_string(color)
    if caps:
        r.font.all_caps = True
    if spacing:
        rpr = r._r.get_or_add_rPr()
        sp = OxmlElement("w:spacing")
        sp.set(qn("w:val"), str(spacing))
        rpr.append(sp)
    return r


def _square_bullets(d):
    """Make the List Bullet style use a small square (Wingdings), like the classic CV."""
    numbering = d.part.numbering_part.element
    num_id = d.styles["List Bullet"].element.pPr.numPr.numId.val
    abs_id = None
    for num in numbering.findall(qn("w:num")):
        if num.get(qn("w:numId")) == str(num_id):
            abs_id = num.find(qn("w:abstractNumId")).get(qn("w:val"))
    for an in numbering.findall(qn("w:abstractNum")):
        if an.get(qn("w:abstractNumId")) != abs_id:
            continue
        lvl = an.find(qn("w:lvl"))
        lvl.find(qn("w:lvlText")).set(qn("w:val"), "\uf0a7")
        rpr = lvl.find(qn("w:rPr"))
        if rpr is None:
            rpr = OxmlElement("w:rPr")
            lvl.append(rpr)
        fonts = rpr.find(qn("w:rFonts"))
        if fonts is None:
            fonts = OxmlElement("w:rFonts")
            rpr.append(fonts)
        for k in ("ascii", "hAnsi", "cs"):
            fonts.set(qn("w:" + k), "Wingdings")
        fonts.set(qn("w:hint"), "default")


def build_docx(spec, out_docx):
    st = style_of(spec)
    size = float(st["size"])
    d = docx.Document()
    sec = d.sections[0]
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
    for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(sec, side, Cm(float(st["margin_cm"])))
    usable = sec.page_width - sec.left_margin - sec.right_margin

    normal = d.styles["Normal"]
    normal.font.name = st["font"]
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), st["font"])
    normal.font.size = Pt(size)
    _square_bullets(d)

    def right_tab(p):
        p.paragraph_format.tab_stops.add_tab_stop(usable, WD_TAB_ALIGNMENT.RIGHT)

    # Header: name, then contact details and links on one grey line
    p = d.add_paragraph(); p.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER; _spacing(p, 0, 0)
    _run(p, display_name(spec["name"], st), size + 7, bold=True, color=st["name_color"], spacing=30)
    p = d.add_paragraph(); p.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER; _spacing(p, 0, 2)
    items = [(t, False) for t in spec.get("contact", [])] + [(t, True) for t in spec.get("links", [])]
    for i, (text, is_link) in enumerate(items):
        if i:
            _run(p, " | ", size + 2, color=st["contact_color"], spacing=15)
        _run(p, text, size + 2, color=st["link_color"] if is_link else st["contact_color"], spacing=15, underline=is_link)

    def section(title):
        p = d.add_paragraph(); _spacing(p, 3, 0); _shade(p, st["heading_fill"]); _bottom_border(p, "auto")
        p.paragraph_format.keep_with_next = True
        _run(p, title, size + 2, bold=True, color=st["heading_color"], caps=True, spacing=20)

    def band(left, right):
        p = d.add_paragraph(); _spacing(p, 2, 0); right_tab(p); _shade(p, st["band"])
        p.paragraph_format.keep_with_next = True
        _run(p, left, size + 1, bold=True, caps=True, spacing=20)
        if right:
            _run(p, "\t" + right, size + 1, bold=True, caps=True, spacing=20)

    def title_line(left, right):
        p = d.add_paragraph(); _spacing(p, 3, 0); right_tab(p)
        p.paragraph_format.keep_with_next = True
        _run(p, left, size, bold=True)
        if right:
            _run(p, "\t" + right, size, bold=True)

    def note_line(text):
        p = d.add_paragraph(); _spacing(p, 0, 0)
        _run(p, text, size - 1, italic=True, color="808080")

    def bullet(label, text=None):
        p = d.add_paragraph(style="List Bullet"); _spacing(p, 0, 0, 1.0)
        p.paragraph_format.left_indent = Cm(0.508)
        p.paragraph_format.first_line_indent = Cm(-0.508)
        p.alignment = WD_PARAGRAPH_ALIGNMENT.JUSTIFY
        if text is None:
            _run(p, label, size)
        else:
            _run(p, label, size, bold=True)
            _run(p, " " + text.strip(), size)

    if spec.get("summary"):
        section("Summary")
        p = d.add_paragraph(); _spacing(p, 0, 0); p.alignment = WD_PARAGRAPH_ALIGNMENT.JUSTIFY
        _run(p, spec["summary"], size)

    if spec.get("experience"):
        section("Professional Experience")
        for job in spec["experience"]:
            band(job["company"], job.get("dates", ""))
            if job.get("note"):
                note_line(job["note"])
            for role in job.get("roles", []):
                title_line(role["title"], role.get("dates", ""))
                for b in role.get("bullets", []):
                    bullet(b)

    if spec.get("education"):
        section("Education")
        for ed in spec["education"]:
            band(ed["school"], ed.get("dates", ""))
            if ed.get("degree"):
                title_line(ed["degree"], "")
            for b in ed.get("bullets", []):
                bullet(b)

    if spec.get("skills"):
        section("Skills")
        for label, text in spec["skills"]:
            bullet(label, text)

    set_properties(d, spec.get("name", "Candidate"))
    d.save(out_docx)


def set_properties(d, author):
    """Properties a CV saved by hand in Word would have: owner as author and
    last editor, a plain title, fresh dates, nothing else."""
    cp = d.core_properties
    now = datetime.now(timezone.utc).replace(microsecond=0)
    cp.author = cp.last_modified_by = author
    cp.title = f"{author} - CV"
    cp.subject = cp.keywords = cp.comments = cp.category = cp.content_status = ""
    cp.created = now - timedelta(minutes=random.randint(25, 90))
    cp.modified = now
    cp.revision = random.randint(3, 9)


def _pdf_with_word(docx_path, pdf_path):
    exe = shutil.which("pwsh") or shutil.which("powershell")
    if not exe:
        return None
    ps = f"""
$ErrorActionPreference = 'Stop'
$w = New-Object -ComObject Word.Application; $w.Visible = $false
try {{
  $d = $w.Documents.Open('{docx_path}', $false, $true); $d.Repaginate()
  $n = $d.ComputeStatistics(2)
  $d.ExportAsFixedFormat('{pdf_path}', 17, $false, 0, 0, 0, 0, 0, $true, $true, 0, $true, $true, $false); $d.Close($false)
  Write-Output $n
}} finally {{ $w.Quit() }}
"""
    r = subprocess.run([exe, "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        return None
    return int(r.stdout.strip().splitlines()[-1])


def _pdf_with_libreoffice(docx_path, pdf_path):
    exe = shutil.which("soffice") or shutil.which("libreoffice")
    if not exe:
        return None
    outdir = os.path.dirname(pdf_path)
    subprocess.run([exe, "--headless", "--convert-to", "pdf", "--outdir", outdir, docx_path], capture_output=True, timeout=180)
    produced = os.path.splitext(docx_path)[0] + ".pdf"
    if produced != pdf_path and os.path.exists(produced):
        os.replace(produced, pdf_path)
    try:
        import pymupdf
        return len(pymupdf.open(pdf_path))
    except Exception:
        return 1 if os.path.exists(pdf_path) else None


def browser_exe():
    """Edge (on every Windows 10/11 PC), Chrome or Chromium."""
    cands = [shutil.which(n) for n in ("msedge", "chrome", "google-chrome", "chromium", "chromium-browser")]
    cands += [os.path.expandvars(p) for p in (
        r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe", r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
        r"%ProgramFiles%\Google\Chrome\Application\chrome.exe", r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
        r"%LocalAppData%\Google\Chrome\Application\chrome.exe")]
    cands += ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"]
    return next((c for c in cands if c and os.path.isfile(c)), None)


def _esc(t):
    return (str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def render_html(spec):
    """The same one-page layout as the Word file, as HTML for printing."""
    st = style_of(spec)
    size, m = float(st["size"]), float(st["margin_cm"]) * 10
    css = f"""@page{{size:A4;margin:{m}mm}}
body{{font-family:'{st['font']}',Calibri,Carlito,Arial,sans-serif;font-size:{size}pt;color:#000;margin:0;line-height:1.17}}
h1{{text-align:center;color:#{st['name_color']};font-size:{size + 7}pt;margin:0;letter-spacing:1.5pt}}
.contact{{text-align:center;color:#{st['contact_color']};font-size:{size + 2}pt;letter-spacing:.75pt;margin:0 0 2pt}}
.contact u{{color:#{st['link_color']}}}
h2{{background:#{st['heading_fill']};color:#{st['heading_color']};font-size:{size + 2}pt;text-transform:uppercase;letter-spacing:1pt;border-bottom:.5pt solid #000;margin:3pt 0 0;padding:0 1pt;break-after:avoid}}
.band{{background:#{st['band']};font-weight:bold;text-transform:uppercase;letter-spacing:1pt;display:flex;justify-content:space-between;margin:2pt 0 0;padding:0 1pt;font-size:{size + 1}pt;break-after:avoid}}
.line{{display:flex;justify-content:space-between;margin-top:3pt;font-weight:bold;break-after:avoid}}
.note{{font-style:italic;color:#808080;font-size:{size - 1}pt}}
ul{{margin:0;padding-left:14.4pt;list-style:square}} li{{text-align:justify;margin:0}}
p{{margin:0;text-align:justify}}"""
    contact = [_esc(t) for t in spec.get("contact", [])] + [f"<u>{_esc(t)}</u>" for t in spec.get("links", [])]
    out = [f"<!doctype html><html><head><meta charset='utf-8'><title>{_esc(spec['name'])} - CV</title><style>{css}</style></head><body>",
           f"<h1>{_esc(display_name(spec['name'], st))}</h1>",
           f"<div class='contact'>{' | '.join(contact)}</div>"]
    if spec.get("summary"):
        out += ["<h2>Summary</h2>", f"<p>{_esc(spec['summary'])}</p>"]
    if spec.get("experience"):
        out.append("<h2>Professional Experience</h2>")
        for job in spec["experience"]:
            out.append(f"<div class='band'><span>{_esc(job['company'])}</span><span>{_esc(job.get('dates', ''))}</span></div>")
            if job.get("note"):
                out.append(f"<div class='note'>{_esc(job['note'])}</div>")
            for role in job.get("roles", []):
                out.append(f"<div class='line'><span>{_esc(role['title'])}</span><span>{_esc(role.get('dates', ''))}</span></div>")
                if role.get("bullets"):
                    out.append("<ul>" + "".join(f"<li>{_esc(b)}</li>" for b in role["bullets"]) + "</ul>")
    if spec.get("education"):
        out.append("<h2>Education</h2>")
        for ed in spec["education"]:
            out.append(f"<div class='band'><span>{_esc(ed['school'])}</span><span>{_esc(ed.get('dates', ''))}</span></div>")
            if ed.get("degree"):
                out.append(f"<div class='line'><span>{_esc(ed['degree'])}</span></div>")
            if ed.get("bullets"):
                out.append("<ul>" + "".join(f"<li>{_esc(b)}</li>" for b in ed["bullets"]) + "</ul>")
    if spec.get("skills"):
        out.append("<h2>Skills</h2><ul>" + "".join(f"<li><b>{_esc(l)}</b> {_esc(t.strip())}</li>" for l, t in spec["skills"]) + "</ul>")
    out.append("</body></html>")
    return "".join(out)


def _pdf_with_browser(spec, pdf_path):
    return html_to_pdf(render_html(spec), pdf_path) if spec is not None else None


def html_to_pdf(html_text, pdf_path):
    """Print an HTML document to PDF with the system browser; returns the page count or None."""
    exe = browser_exe()
    if not exe:
        return None
    import tempfile
    html = os.path.join(tempfile.mkdtemp(), "doc.html")
    with open(html, "w", encoding="utf-8") as f:
        f.write(html_text)
    profile = tempfile.mkdtemp()
    url = "file:///" + html.replace("\\", "/").lstrip("/")
    try:
        subprocess.run([exe, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--no-first-run",
                        f"--user-data-dir={profile}", f"--print-to-pdf={pdf_path}", url],
                       capture_output=True, timeout=120, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (subprocess.TimeoutExpired, OSError):
        return None
    if not os.path.isfile(pdf_path):
        return None
    try:
        import pymupdf
        return len(pymupdf.open(pdf_path))
    except Exception:  # noqa: BLE001
        return 1


def export_pdf(docx_path, pdf_path, spec=None):
    """Word if installed (identical to the .docx), else the system browser, else LibreOffice."""
    pages = None if os.environ.get("JOB_DESK_PDF") in ("browser", "libreoffice") else _pdf_with_word(docx_path, pdf_path)
    if pages is None and os.environ.get("JOB_DESK_PDF") != "libreoffice":
        pages = _pdf_with_browser(spec, pdf_path)
    if pages is None:
        pages = _pdf_with_libreoffice(docx_path, pdf_path)
    if pages is None:
        raise RuntimeError("No PDF exporter found: Microsoft Edge, Chrome, Word or LibreOffice is needed")
    return pages


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    spec_path, out_dir = sys.argv[1], sys.argv[2]
    with open(spec_path, encoding="utf-8") as f:
        spec = json.load(f)
    name = spec.get("name", "CV").replace(" ", "_") + "_CV"
    if "--name" in sys.argv:
        name = sys.argv[sys.argv.index("--name") + 1]
    name = re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_")[:80] or "CV"
    os.makedirs(out_dir, exist_ok=True)
    if "'" in os.path.abspath(out_dir):
        raise SystemExit("output directory must not contain an apostrophe")
    out_docx = os.path.abspath(os.path.join(out_dir, name + ".docx"))
    out_pdf = os.path.abspath(os.path.join(out_dir, name + ".pdf"))
    build_docx(spec, out_docx)
    pages = export_pdf(out_docx, out_pdf, spec)
    print(json.dumps({"docx": out_docx, "pdf": out_pdf, "pages": pages}))
    sys.exit(0 if pages == 1 else 2)


if __name__ == "__main__":
    main()
