# backend/utils/

Report generation utilities — produces the downloadable artifacts that accompany every agent answer.

## Files

| File | Purpose |
|---|---|
| `pdf_generator.py` | Renders a Markdown answer to a styled PDF using `fpdf2` |
| `excel_generator.py` | Exports a list of records (or a dict of named sheets) to `.xlsx` using `openpyxl` |
| `fonts/DejaVuSans.ttf` | Unicode-safe font for PDF (supports ₹, %, em-dash, and other financial glyphs) |
| `fonts/DejaVuSans-Bold.ttf` | Bold weight of the same font |

## PDF generation

`generate_pdf_report(answer: str, filename: str) → str`

- Converts Markdown to plain text with basic formatting (headings, bold, bullet points)
- Uses DejaVu Sans fonts to correctly render Unicode characters (₹, %, –, etc.)
- Outputs to `data/exports/<filename>`
- Returns the file path

## Excel generation

`generate_excel(data: list[dict] | dict[str, list[dict]], filename: str) → str`

- Accepts either a single list of records (→ one sheet named `Sheet1`) or a dict mapping sheet names to record lists (→ multiple sheets)
- Applies header formatting (bold, coloured header row)
- Outputs to `data/exports/<filename>`
- Returns the file path

## Why DejaVu fonts?

Python's default font in fpdf2 lacks Unicode glyph coverage. Financial text contains the Rupee symbol `₹`, en-dashes in date ranges, and percentage signs that would render as `?` without a Unicode-complete font. DejaVu Sans covers the full Latin Extended set needed for Infosys FY26 documents.
