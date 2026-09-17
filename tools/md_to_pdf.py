#!/usr/bin/env python3
"""Markdown → A4 PDF for sharing docs with the team (WhatsApp shows .md as raw text).

    python3 tools/md_to_pdf.py docs/agent-spec.md out/KeepAlive_Voice_Agent_Spec.pdf

Handles the subset our docs use: headings, paragraphs, bullet and numbered
lists, tables, fenced code, inline code, bold and italic. Printed by Chromium
through Playwright, so tables and code look the way they do in a browser.
"""

import html
import re
import sys
from pathlib import Path

LIST = re.compile(r"^(\s*)([-*]|\d+\.)\s+(.*)")

CSS = """
@page { size: A4; margin: 16mm 14mm 18mm; }
* { box-sizing: border-box; }
/* explicit white: some previewers (sips, chat thumbnails) paint transparent areas black */
html, body { background: #fff; }
body { font: 10.3pt/1.5 -apple-system, "Helvetica Neue", Arial, sans-serif; color: #1b1f24; margin: 0; }
.cover { border-bottom: 3px solid #d7263d; padding-bottom: 10px; margin-bottom: 14px; }
.cover .tag { color: #d7263d; font-weight: 700; letter-spacing: .08em; font-size: 8.5pt; text-transform: uppercase; }
h1 { font-size: 22pt; margin: 4px 0 6px; line-height: 1.15; }
h2 { font-size: 13.5pt; margin: 20px 0 6px; padding-top: 8px; border-top: 1px solid #e3e6ea; break-after: avoid; }
h3 { font-size: 11.5pt; margin: 14px 0 4px; break-after: avoid; }
p { margin: 5px 0 8px; }
ul, ol { margin: 4px 0 10px; padding-left: 20px; }
li { margin: 3px 0; }
code { font: 8.8pt/1.4 "SF Mono", Menlo, Consolas, monospace; background: #f1f3f6; padding: 1px 4px; border-radius: 3px; }
pre { background: #0f1115; color: #e7e9ee; padding: 9px 11px; border-radius: 6px; white-space: pre-wrap;
      word-break: break-word; margin: 6px 0 12px; }
pre code { background: none; padding: 0; color: inherit; font-size: 8.2pt; line-height: 1.45; }
pre.text { background: #f7f8fa; color: #1b1f24; border: 1px solid #e3e6ea; }
table { border-collapse: collapse; width: 100%; margin: 6px 0 12px; font-size: 8.8pt; }
th, td { border: 1px solid #dfe3e8; padding: 4px 6px; vertical-align: top; text-align: left; background: #fff; }
th { background: #f1f3f6; font-weight: 650; }
tr { break-inside: avoid; }
td code, th code { font-size: 8pt; }
strong { font-weight: 650; }
"""


def inline(s):
    s = html.escape(s, quote=False)
    codes = []

    def stash(m):
        codes.append(m.group(1))
        return f"\x00{len(codes) - 1}\x00"

    s = re.sub(r"`([^`]+)`", stash, s)                        # protect code spans first
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)    # so bold can wrap code
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", s)
    return re.sub(r"\x00(\d+)\x00", lambda m: f"<code>{codes[int(m.group(1))]}</code>", s)


def cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def to_html(md):
    lines = md.splitlines()
    body, i = [], 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            lang = line[3:].strip()
            j, code = i + 1, []
            while j < len(lines) and not lines[j].startswith("```"):
                code.append(lines[j])
                j += 1
            body.append(f'<pre class="{lang}"><code>{html.escape(chr(10).join(code))}</code></pre>')
            i = j + 1
            continue
        m = re.match(r"^(#{1,4})\s+(.*)", line)
        if m:
            n = len(m.group(1))
            body.append(f"<h{n}>{inline(m.group(2))}</h{n}>")
            i += 1
            continue
        if line.strip() == "---":
            i += 1
            continue
        if line.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s\-:|]+\|$", lines[i + 1].strip()):
            head, rows, j = cells(line), [], i + 2
            while j < len(lines) and lines[j].startswith("|"):
                rows.append(cells(lines[j]))
                j += 1
            t = "<table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr></thead><tbody>"
            t += "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows)
            body.append(t + "</tbody></table>")
            i = j
            continue
        lm = LIST.match(line)
        if lm:
            ordered = lm.group(2)[0].isdigit()
            items, j = [], i
            while j < len(lines):
                mm = LIST.match(lines[j])
                if mm and mm.group(2)[0].isdigit() == ordered and not mm.group(1):
                    items.append(mm.group(3))
                    j += 1
                elif items and lines[j].strip() and re.match(r"^\s{2,}\S", lines[j]) and not lines[j].lstrip().startswith("```"):
                    items[-1] += " " + lines[j].strip()   # wrapped continuation line
                    j += 1
                else:
                    break
            tag = "ol" if ordered else "ul"
            body.append(f"<{tag}>" + "".join(f"<li>{inline(x)}</li>" for x in items) + f"</{tag}>")
            i = j
            continue
        if not line.strip():
            i += 1
            continue
        para, j = [line.strip()], i + 1
        while j < len(lines) and lines[j].strip() and not re.match(r"^(#|```|\||([-*]|\d+\.)\s|---$)", lines[j]):
            para.append(lines[j].strip())
            j += 1
        body.append(f"<p>{inline(' '.join(para))}</p>")
        i = j
    return "".join(body)


def main():
    if len(sys.argv) != 3:
        sys.exit("usage: md_to_pdf.py <input.md> <output.pdf>")
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    title = re.search(r"^#\s+(.*)", src.read_text(), re.M)
    doc = (f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title.group(1) if title else src.stem)}"
           f"</title><style>{CSS}</style></head><body><div class='cover'><div class='tag'>"
           f"AssemblyAI Voice Agent Hackathon · Team KeepAlive</div></div>{to_html(src.read_text())}</body></html>")

    from playwright.sync_api import sync_playwright

    out.parent.mkdir(parents=True, exist_ok=True)
    footer = (f'<div style="font:8px Helvetica;color:#8b91a0;width:100%;text-align:center">'
              f'KeepAlive · {html.escape(src.stem)} · <span class="pageNumber"></span>/<span class="totalPages"></span></div>')
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page()
        page.set_content(doc, wait_until="load")
        page.pdf(path=str(out), format="A4", print_background=True, prefer_css_page_size=True,
                 display_header_footer=True, header_template="<span></span>", footer_template=footer)
        b.close()
    print(f"{out} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
