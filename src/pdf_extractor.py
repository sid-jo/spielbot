import pdfplumber
import json
import re
from pathlib import Path


def find_column_boundaries(page, min_gap_fraction=0.03):
    """
    Detect vertical column boundaries by finding horizontal gaps in word coverage.

    Builds a 1pt-resolution coverage array from word bounding boxes, then looks
    for runs of empty space in the interior of the page (ignoring outer margins).
    Returns a list of (x0, x1) tuples — one per detected column.
    """
    words = page.extract_words(x_tolerance=3, y_tolerance=3)
    if not words:
        return [(0.0, float(page.width))]

    page_width = float(page.width)
    n_slots = int(page_width) + 1
    covered = bytearray(n_slots)

    for word in words:
        lo = max(0, int(word["x0"]))
        hi = min(n_slots - 1, int(word["x1"]) + 1)
        for i in range(lo, hi):
            covered[i] = 1

    # Only look for gaps in the inner 84 % of the page width (skip margins)
    left_margin = int(page_width * 0.08)
    right_margin = int(page_width * 0.92)
    min_gap = max(4, int(page_width * min_gap_fraction))

    split_points = []
    in_gap = False
    gap_start = 0

    for x in range(left_margin, right_margin + 1):
        is_empty = (x >= n_slots) or (covered[x] == 0)
        if is_empty and not in_gap:
            in_gap = True
            gap_start = x
        elif not is_empty and in_gap:
            gap_width = x - gap_start
            if gap_width >= min_gap:
                # Use the midpoint of the gap as the split x-coordinate
                split_points.append((gap_start + x) / 2.0)
            in_gap = False

    if not split_points:
        return [(0.0, page_width)]

    boundaries = [0.0] + split_points + [page_width]
    return [(boundaries[i], boundaries[i + 1]) for i in range(len(boundaries) - 1)]


def extract_page_text(page):
    """
    Extract text from a single page, preserving correct reading order.

    Steps:
    1. Deduplicate overlapping characters (fixes bold/shadow double-rendering).
    2. Detect column layout via horizontal gap analysis.
    3. For multi-column pages, crop to each column and extract independently,
       then concatenate columns left-to-right.
    """
    page = page.dedupe_chars(tolerance=1)
    columns = find_column_boundaries(page)

    if len(columns) == 1:
        return page.extract_text(x_tolerance=3, y_tolerance=3) or ""

    parts = []
    for x0, x1 in columns:
        col = page.crop((x0, 0, x1, page.height))
        text = col.extract_text(x_tolerance=3, y_tolerance=3)
        if text and text.strip():
            parts.append(text.strip())

    return "\n\n".join(parts)


def clean_text(text):
    """
    Light post-extraction cleanup that doesn't remove real content.

    - Strip (cid:XX) unmapped-glyph placeholders produced when the PDF font
      lacks a ToUnicode table.
    - Collapse runs of blank lines down to a single blank line.
    - Strip trailing whitespace from every line.
    """
    # Remove CID placeholders like (cid:7), (cid:31), etc.
    text = re.sub(r"\(cid:\d+\)", "", text)

    # Strip trailing whitespace per line and collapse 3+ blank lines to 2
    lines = [line.rstrip() for line in text.splitlines()]
    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))

    return cleaned.strip()


def extract_text_from_pdf(pdf_path):
    """Extract text from a PDF file, handling multi-column layouts."""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            pages_text = []
            for page in pdf.pages:
                page_text = extract_page_text(page)
                if page_text:
                    pages_text.append(page_text)
            raw = "\n\n".join(pages_text)
            return clean_text(raw)
    except Exception as e:
        print(f"Error extracting text from {pdf_path}: {e}")
        return None


def extract_all_rulebooks(rulebooks_dir, output_dir):
    """Extract text from all PDFs in the rulebooks directory."""
    rulebooks_path = Path(rulebooks_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    extracted_data = {}

    for game_dir in rulebooks_path.iterdir():
        if not game_dir.is_dir():
            continue

        game_name = game_dir.name
        extracted_data[game_name] = {}
        print(f"\nProcessing {game_name}...")

        for pdf_file in game_dir.glob("*.pdf"):
            print(f"  Extracting: {pdf_file.name}")
            text = extract_text_from_pdf(pdf_file)

            if text:
                rulebook_name = pdf_file.stem
                extracted_data[game_name][rulebook_name] = text

                txt_output = output_path / f"{game_name}_{rulebook_name}.txt"
                with open(txt_output, "w", encoding="utf-8") as f:
                    f.write(text)
                print(f"    Saved to {txt_output}")

    json_output = output_path / "all_rulebooks.json"
    with open(json_output, "w", encoding="utf-8") as f:
        json.dump(extracted_data, f, indent=2, ensure_ascii=False)
    print(f"\nAll data saved to {json_output}")

    return extracted_data


if __name__ == "__main__":
    script_dir = Path(__file__).parent
    project_root = script_dir.parent

    rulebooks_dir = project_root / "data" / "rulebooks"
    output_dir = project_root / "data" / "processed_rulebooks"

    print(f"Extracting PDFs from: {rulebooks_dir}")
    print(f"Output directory: {output_dir}")

    extracted_data = extract_all_rulebooks(rulebooks_dir, output_dir)

    print(f"\nExtraction complete!")
    print(f"  Games processed: {len(extracted_data)}")
    total_books = sum(len(books) for books in extracted_data.values())
    print(f"  Total rulebooks: {total_books}")
