"""Build a one-page cover letter (DOCX + PDF) from a cover note.

Usage:
    python build_cover.py <cover_note.md> <output_dir> --name Firstname_Lastname_Cover_Letter
                          [--sender "Firstname Lastname"] [--contact "City | email | phone"] [--company "Acme"]

The note's text is used as is (it was already fact-checked). Output uses the
same PDF exporters and clean document properties as build_cv.py.
Exit codes: 0 ok, 2 longer than one page, 1 error.
"""
import argparse
import json
import os
import re
import sys
from datetime import date

import docx
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from docx.shared import Pt, Cm, RGBColor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_cv import _esc, _pdf_with_libreoffice, _pdf_with_word, html_to_pdf, set_properties  # noqa: E402


def build(note_text, out_docx, sender, contact, company, accent="1F4E79"):
    d = docx.Document()
    sec = d.sections[0]
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
    sec.left_margin = sec.right_margin = Cm(2.2)
    sec.top_margin = sec.bottom_margin = Cm(2.0)
    normal = d.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)

    def para(text="", size=11, bold=False, color=None, align=None, after=6):
        p = d.add_paragraph()
        p.paragraph_format.space_after = Pt(after)
        if align:
            p.alignment = align
        if text:
            r = p.add_run(text)
            r.font.size = Pt(size)
            r.bold = bold
            if color:
                r.font.color.rgb = RGBColor.from_string(color)
        return p

    if sender:
        para(sender, 20, True, accent, after=2)
    if contact:
        para(contact, 10, color="404040", after=18)
    para(date.today().strftime("%d %B %Y"), after=12)
    if company:
        para(f"Hiring Team, {company}", after=12)
    # Body: paragraphs separated by blank lines; strip markdown emphasis
    body = re.sub(r"[*_`#]+", "", note_text).strip()
    for chunk in re.split(r"\n\s*\n", body):
        text = " ".join(line.strip() for line in chunk.splitlines() if line.strip())
        if text:
            para(text, after=10).alignment = WD_PARAGRAPH_ALIGNMENT.LEFT
    set_properties(d, sender or "Candidate")
    d.core_properties.title = f"{sender} - Cover letter" if sender else "Cover letter"
    d.save(out_docx)


def render_html(note_text, sender, contact, company, accent="1F4E79"):
    body = re.sub(r"[*_`#]+", "", note_text).strip()
    paras = [" ".join(l.strip() for l in chunk.splitlines() if l.strip()) for chunk in re.split(r"\n\s*\n", body)]
    css = ("@page{size:A4;margin:20mm 22mm}body{font-family:Calibri,Carlito,Arial,sans-serif;font-size:11pt;color:#111;margin:0;line-height:1.3}"
           f"h1{{color:#{accent};font-size:20pt;margin:0 0 2pt}}.c{{color:#404040;font-size:10pt;margin:0 0 18pt}}p{{margin:0 0 10pt}}")
    head = f"<h1>{_esc(sender)}</h1><div class='c'>{_esc(contact)}</div>" if sender else ""
    to = f"<p>Hiring Team, {_esc(company)}</p>" if company else ""
    return (f"<!doctype html><html><head><meta charset='utf-8'><title>{_esc(sender or 'Cover')} - Cover letter</title><style>{css}</style></head><body>"
            + head + f"<p>{date.today().strftime('%d %B %Y')}</p>" + to + "".join(f"<p>{_esc(p)}</p>" for p in paras if p) + "</body></html>")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("note")
    ap.add_argument("out_dir")
    ap.add_argument("--name", default="Cover_Letter")
    ap.add_argument("--sender", default=os.environ.get("JOB_DESK_OWNER", ""))
    ap.add_argument("--contact", default="")
    ap.add_argument("--company", default="")
    a = ap.parse_args()
    name = re.sub(r"[^A-Za-z0-9_-]+", "_", a.name).strip("_")[:80] or "Cover_Letter"
    os.makedirs(a.out_dir, exist_ok=True)
    if "'" in os.path.abspath(a.out_dir):
        raise SystemExit("output directory must not contain an apostrophe")
    with open(a.note, encoding="utf-8-sig") as f:
        note = f.read()
    out_docx = os.path.abspath(os.path.join(a.out_dir, name + ".docx"))
    out_pdf = os.path.abspath(os.path.join(a.out_dir, name + ".pdf"))
    build(note, out_docx, a.sender, a.contact, a.company)
    pages = None if os.environ.get("JOB_DESK_PDF") in ("browser", "libreoffice") else _pdf_with_word(out_docx, out_pdf)
    if pages is None and os.environ.get("JOB_DESK_PDF") != "libreoffice":
        pages = html_to_pdf(render_html(note, a.sender, a.contact, a.company), out_pdf)
    if pages is None:
        pages = _pdf_with_libreoffice(out_docx, out_pdf)
    if pages is None:
        raise SystemExit("No PDF exporter found: Microsoft Edge, Chrome, Word or LibreOffice is needed")
    print(json.dumps({"docx": out_docx, "pdf": out_pdf, "pages": pages}))
    sys.exit(0 if pages == 1 else 2)


if __name__ == "__main__":
    main()
