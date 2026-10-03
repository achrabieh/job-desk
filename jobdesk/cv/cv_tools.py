"""Tools Claude uses to work with a person's own CV design.

    python cv_tools.py look  <cv.pdf|cv.docx> <out_dir>
        Renders each page to out_dir/page-N.png (so Claude can see the design) and saves
        embedded pictures (a photo, a logo) as out_dir/image-N.<ext>. Prints JSON.
    python cv_tools.py build <cv.html> <out_dir> --name First_Last_CV [--max-pages N] [--assets DIR]
        Prints an HTML CV to out_dir/<name>.pdf with Edge or Chrome, and saves a picture of
        page 1 as out_dir/<name>.png to check the result. Local images (src="photo.jpg") are
        looked up next to the HTML file, then in --assets, and embedded. Exit code 2 when the
        PDF has more pages than --max-pages (default 1).
    python cv_tools.py text  <cv.html> <out.txt>
        Writes the visible text of an HTML CV (for the fact check).
"""
import base64
import html as htmllib
import json
import mimetypes
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def look(src, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    ext = os.path.splitext(src)[1].lower()
    result = {"file": src, "pages": None, "page_images": [], "images": [], "note": ""}
    pdf = src
    if ext in (".docx", ".doc"):
        result["images"] = _docx_images(src, out_dir) if ext == ".docx" else []
        import build_cv
        pdf = os.path.join(out_dir, "source.pdf")
        if not build_cv.export_pdf(os.path.abspath(src), os.path.abspath(pdf)):
            result["note"] = "Couldn't render the Word file to pictures (no Word or LibreOffice). Read its text instead."
            pdf = None
    elif ext != ".pdf":
        result["note"] = "Not a PDF or Word file: read it as text."
        pdf = None
    if pdf and os.path.isfile(pdf):
        import pymupdf
        doc = pymupdf.open(pdf)
        result["pages"] = len(doc)
        for i, page in enumerate(doc):
            if i >= 4:
                break
            p = os.path.join(out_dir, f"page-{i + 1}.png")
            page.get_pixmap(dpi=110).save(p)
            result["page_images"].append(p)
        if ext == ".pdf":
            n = 0
            for page in doc:
                for img in page.get_images(full=True):
                    info = doc.extract_image(img[0])
                    if not info or info.get("width", 0) < 80 or info.get("height", 0) < 80:
                        continue  # icons and bullets
                    n += 1
                    p = os.path.join(out_dir, f"image-{n}.{info.get('ext', 'png')}")
                    with open(p, "wb") as f:
                        f.write(info["image"])
                    result["images"].append(p)
    print(json.dumps(result, indent=2))
    return 0


def _docx_images(src, out_dir):
    import zipfile
    found = []
    with zipfile.ZipFile(src) as z:
        for i, name in enumerate(n for n in z.namelist() if n.startswith("word/media/")):
            data = z.read(name)
            if len(data) < 3000:
                continue  # icons
            p = os.path.join(out_dir, f"image-{i + 1}{os.path.splitext(name)[1].lower()}")
            with open(p, "wb") as f:
                f.write(data)
            found.append(p)
    return found


def _inline_images(html_text, base_dirs):
    def repl(m):
        src = m.group(2)
        if re.match(r"(data:|https?:)", src, re.I):
            return m.group(0)
        for d in base_dirs:
            p = os.path.join(d, src.replace("/", os.sep))
            if d and os.path.isfile(p):
                mime = mimetypes.guess_type(p)[0] or "image/png"
                data = base64.b64encode(open(p, "rb").read()).decode("ascii")
                return f"{m.group(1)}data:{mime};base64,{data}{m.group(3)}"
        return m.group(0)
    return re.sub(r"""(src=["'])([^"']+)(["'])""", repl, html_text)


def build(html_path, out_dir, name, max_pages=1, assets=None):
    import build_cv
    os.makedirs(out_dir, exist_ok=True)
    name = re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_")[:80] or "CV"
    with open(html_path, encoding="utf-8") as f:
        text = f.read()
    text = _inline_images(text, [os.path.dirname(os.path.abspath(html_path)), assets])
    pdf = os.path.abspath(os.path.join(out_dir, name + ".pdf"))
    pages = build_cv.html_to_pdf(text, pdf)
    png = None
    if pages:
        import pymupdf
        png = os.path.join(out_dir, name + ".png")
        pymupdf.open(pdf)[0].get_pixmap(dpi=90).save(png)
    print(json.dumps({"pdf": pdf if pages else None, "pages": pages, "png": png,
                      "error": None if pages else "Edge or Chrome is needed to make the PDF."}))
    if not pages:
        return 1
    return 2 if pages > max_pages else 0


def text_of(html_path, out_txt):
    with open(html_path, encoding="utf-8") as f:
        t = f.read()
    t = re.sub(r"(?is)<(script|style|head)[^>]*>.*?</\1>", " ", t)
    t = re.sub(r"(?i)<br\s*/?>|</(p|div|li|h[1-6]|tr)>", "\n", t)
    t = htmllib.unescape(re.sub(r"<[^>]+>", " ", t))
    t = "\n".join(re.sub(r"[ \t]+", " ", line).strip() for line in t.splitlines())
    t = re.sub(r"\n{2,}", "\n", t).strip()
    with open(out_txt, "w", encoding="utf-8") as f:
        f.write(t + "\n")
    print(json.dumps({"text": out_txt, "chars": len(t)}))
    return 0


def main():
    a = sys.argv[1:]
    if len(a) < 3 or a[0] not in ("look", "build", "text"):
        print(__doc__)
        return 1
    if a[0] == "look":
        return look(a[1], a[2])
    if a[0] == "text":
        return text_of(a[1], a[2])

    def opt(flag, default=None):
        return a[a.index(flag) + 1] if flag in a else default
    return build(a[1], a[2], opt("--name", "CV"), int(opt("--max-pages", "1")), opt("--assets"))


if __name__ == "__main__":
    sys.exit(main())
