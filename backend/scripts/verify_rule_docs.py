"""Download official 2026 exchange rule documents and verify pending details.

P1 verification gate (docs/06 section 6). Read-only network fetch; files are
cached under data/reference/rules (gitignored, local evidence only).

Usage:
  .venv\\Scripts\\python.exe backend\\scripts\\verify_rule_docs.py
"""

from __future__ import annotations

import html
import io
import re
import sys
import zipfile
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "reference" / "rules"
OUT.mkdir(parents=True, exist_ok=True)

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) GlobalAIInvestor/0.1"}

DOCS = {
    "sse_2026_rule.docx": "https://www.sse.com.cn/lawandrules/sselawsrules2025/trade/universal/c/10816492/files/58bd5ce4dfc94b57a5391f60eb2719ab.docx",
    "szse_2026_rule.pdf": "http://docs.static.szse.cn/www/lawrules/rule/stock/trade/W020260424690713155663.pdf",
    "bse_2026_rule.html": "https://www.bse.cn/jygl_list/200028217.html",
}

PATTERNS = {
    "sse_2026_rule": [
        "44%", "36%", "200股", "100股", "102%", "98%", "0.1元",
        "15:05", "15:30", "申报数量", "风险警示", "涨跌幅限制", "市价申报",
    ],
    "szse_2026_rule": [
        "30万股", "15万股", "100万股", "200股", "102%", "98%",
        "15:05", "风险警示", "涨跌幅限制", "市价申报",
    ],
    "bse_2026_rule": [
        "30%", "100股", "105%", "95%", "15:05", "20万股", "盘后固定价格", "风险警示",
    ],
}


def download(name: str, url: str) -> Path:
    path = OUT / name
    if path.exists() and path.stat().st_size > 0:
        return path
    resp = httpx.get(url, headers=UA, timeout=120, follow_redirects=True)
    resp.raise_for_status()
    path.write_bytes(resp.content)
    print(f"downloaded {name} ({len(resp.content)} bytes)")
    return path


def docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        xml = zf.read("word/document.xml").decode("utf-8", errors="ignore")
    xml = xml.replace("</w:p>", "\n").replace("<w:tab/>", "\t")
    text = re.sub(r"<[^>]+>", "", xml)
    return html.unescape(text)


def pdf_text(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def html_text(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    raw = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    raw = re.sub(r"(?i)</(p|div|li|tr|h\d)>", "\n", raw)
    text = re.sub(r"<[^>]+>", " ", raw)
    return html.unescape(text)


def extract(name: str, path: Path) -> str:
    if name.endswith(".docx"):
        text = docx_text(path)
    elif name.endswith(".pdf"):
        text = pdf_text(path)
    else:
        text = html_text(path)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    txt_path = OUT / f"{name.rsplit('.', 1)[0]}.txt"
    txt_path.write_text(text, encoding="utf-8")
    print(f"extracted {txt_path.name}: {len(text)} chars")
    return text


def search(text: str, patterns: list[str], context: int = 70) -> list[str]:
    lines: list[str] = []
    for pat in patterns:
        matches = list(re.finditer(re.escape(pat), text))
        if not matches:
            lines.append(f"- [{pat}] NOT FOUND")
            continue
        lines.append(f"- [{pat}] {len(matches)} hit(s)")
        for m in matches[:3]:
            start = max(0, m.start() - context)
            end = min(len(text), m.end() + context)
            snippet = text[start:end].replace("\n", " ")
            lines.append(f"  - ...{snippet}...")
    return lines


def main() -> None:
    all_lines: list[str] = ["# 2026 规则原文核验摘要（自动生成）", ""]
    for name, url in DOCS.items():
        try:
            path = download(name, url)
            text = extract(name, path)
            print(f"--- {name} ---")
            lines = search(text, PATTERNS[name.rsplit(".", 1)[0]])
            all_lines.append(f"## {name}")
            all_lines.extend(lines)
            all_lines.append("")
            print("\n".join(lines))
        except Exception as exc:  # noqa: BLE001
            print(f"FAILED {name}: {type(exc).__name__}: {exc}", file=sys.stderr)
            all_lines.append(f"## {name}\n- FAILED: {type(exc).__name__}: {exc}\n")
    (OUT / "verify_summary.md").write_text("\n".join(all_lines), encoding="utf-8")
    print(f"summary written: {OUT / 'verify_summary.md'}")


if __name__ == "__main__":
    main()
