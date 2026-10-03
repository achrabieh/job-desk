"""Independent fact check for a tailored application pack.

Flags numbers and proper names in the tailored CV, cover note and answers that
appear neither in the user's approved sources (fact bank, default CV, standard
answers) nor, for cover notes and answers, in the job posting itself.

Salary answers are skipped (they follow the user's salary rules and are shown
for review anyway), as are question labels in application_qa.md.

Usage:
    python factcheck.py --sources <file> [<file> ...] --posting <posting.md>
                        --cv <cv_spec.json> --texts <cover_note.md> [<more> ...]
                        --out <factcheck.json>
Exit code 0 = clean, 3 = issues found (details in the JSON), 1 = error.
"""
import argparse
import json
import re
import sys

NUM = re.compile(r"(?<![\w.])(?:[$€£]|SAR|AED|USD|EUR|GBP)?\s?\d[\d,.]*\s?(?:%|k|K|M|B|bn|m)?(?![\w])")
NAME = re.compile(r"\b(?:[A-Z][a-z]+(?:['’]s)?|[A-Z]{2,}[a-z]?|[A-Z][a-z]*[A-Z]\w*)\b")
SALARY_Q = re.compile(r"salar|expect|compensation|package|\bpay\b|ctc", re.I)
BOUNDARY = set(".!?:;*-\n([\"'“•|#>")

COMMON = set("""
A An The And Or But If In On At Of For To From By With As Is Are Was Were Be Been Being It Its I My Me We Our You Your He She They Their
This That These Those There Here When Where While Which Who Whom Whose What Why How All Any Each Every Both Either Neither No Not
Dear Hiring Team Regards Kind Best Sincerely Thank Thanks Yes Per Monthly Annual Total Package Gross Negotiable Current Expected
Summary Experience Education Skills Languages Native Professional Fluent Based Open Available Notice Period Months Weeks Days Years
January February March April May June July August September October November December Jan Feb Mar Apr Jun Jul Aug Sep Sept Oct Nov Dec
Monday Tuesday Wednesday Thursday Friday Saturday Sunday Present Top Choice Manager Senior Lead Director Head Assistant Associate
Strategy Operations Product Business Program Programme Project Office CEO COO CFO CTO VP KPI OKR PMO CV MBA BRD HR AI ML SQL BI
Excel PowerPoint Word Python Power Query Automate Tableau Looker
""".split())


def numbers(text):
    out = set()
    for m in NUM.finditer(text):
        core = re.sub(r"[^\d.]", "", m.group(0).replace(",", "")).strip(".")
        if core and not re.fullmatch(r"0+", core):
            out.add(core)
    return out


def _normalise(w):
    w = re.sub(r"['’]s$", "", w)          # possessive: Moove's -> Moove
    if re.fullmatch(r"[A-Z]{2,}s", w):    # plural acronym: CEOs -> CEO
        w = w[:-1]
    return w


def names(text):
    out = set()
    for m in NAME.finditer(text):
        w = _normalise(m.group(0))
        if w in COMMON or len(w) < 2:
            continue
        # A Title-case word opening a sentence, bullet or line is an ordinary word, not a name
        j = m.start() - 1
        while j >= 0 and text[j] in " \t":
            j -= 1
        if (j < 0 or text[j] in BOUNDARY) and not w.isupper() and not re.search(r"[a-z][A-Z]", w):
            continue
        out.add(w)
    return out


def qa_answers(md):
    """application_qa.md -> answer text only, skipping salary answers."""
    parts = re.split(r"\*\*(.+?)\*\*", md)
    if len(parts) < 2:
        return md
    kept = []
    for i in range(1, len(parts), 2):
        q = parts[i]
        a = parts[i + 1] if i + 1 < len(parts) else ""
        if not SALARY_Q.search(q):
            kept.append(a)
    return "\n".join(kept)


def flatten(obj):
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        return " \n".join(flatten(v) for v in obj.values())
    if isinstance(obj, list):
        return " \n".join(flatten(v) for v in obj)
    return str(obj) if obj is not None else ""


def read(path):
    with open(path, encoding="utf-8-sig") as f:
        return f.read()


def context(text, token, width=60):
    i = text.find(token)
    if i < 0:
        return ""
    return text[max(0, i - width): i + len(token) + width].replace("\n", " ").strip()


def check(sources, posting, cv_path, text_paths):
    src_text = "\n".join(read(p) for p in sources)
    post_text = read(posting) if posting else ""
    src_nums, src_names = numbers(src_text), names(src_text)
    post_nums, post_names = numbers(post_text), names(post_text)
    src_lower, post_lower = src_text.lower(), post_text.lower()
    issues = []

    def scan(label, text, allow_posting):
        ok_nums = src_nums | (post_nums if allow_posting else set())
        ok_names = src_names | (post_names if allow_posting else set())
        for n in sorted(numbers(text) - ok_nums):
            issues.append({"file": label, "type": "number", "token": n, "context": context(text, n.split(".")[0])})
        for w in sorted(names(text) - ok_names):
            if w.lower() in src_lower or (allow_posting and w.lower() in post_lower):
                continue
            if not w.isupper() and re.search(r"\b" + re.escape(w.lower()) + r"\b", text):
                continue  # also used in lower case: an ordinary word
            issues.append({"file": label, "type": "name", "token": w, "context": context(text, w)})

    if cv_path:
        scan("CV", flatten(json.loads(read(cv_path))), allow_posting=False)
    for p in text_paths:
        body = read(p)
        label = p.replace("\\", "/").split("/")[-1]
        if p.lower().endswith(".json"):
            data = json.loads(body)
            if isinstance(data, dict) and isinstance(data.get("qa"), list):
                data["qa"] = [x.get("a", "") for x in data["qa"] if not SALARY_Q.search(x.get("q", ""))]
            data.pop("cv_file", None)
            data.pop("built_at", None)
            body = flatten(data)
        elif "qa" in label.lower() or "answer" in label.lower():
            body = qa_answers(body)
        scan(label, body, allow_posting=True)
    return issues


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", nargs="+", required=True)
    ap.add_argument("--posting")
    ap.add_argument("--cv")
    ap.add_argument("--texts", nargs="*", default=[])
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    issues = check(a.sources, a.posting, a.cv, a.texts)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump({"ok": not issues, "issues": issues}, f, indent=2, ensure_ascii=False)
    print(json.dumps({"ok": not issues, "count": len(issues)}))
    sys.exit(0 if not issues else 3)


if __name__ == "__main__":
    main()
