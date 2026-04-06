import pdfplumber
import json
import re
from pathlib import Path


def find_column_boundaries(page, min_gap_fraction=0.03):
    """
    Detect vertical column boundaries by finding horizontal gaps in word coverage.

    Two strategies are tried in order:

    1. Page-wide coverage gap: build a 1pt-resolution coverage array from all word
       bounding boxes and look for clear runs of empty space in the interior.
       Works well when columns are separated by whitespace that spans the full page
       height (no full-width content to fill in the gap).

    2. Per-row gap voting (fallback): group words into rows and, for each row, record
       the position of any large gap in the middle of the page.  If enough rows agree
       on a gap position, that position is used as the column split.  This handles
       pages where some rows contain full-width content that would otherwise mask the
       column gap in the aggregate coverage array.

    Returns a list of (x0, x1) tuples — one per detected column.
    """
    words = page.extract_words(x_tolerance=3, y_tolerance=3)
    if not words:
        return [(0.0, float(page.width))]

    page_width = float(page.width)
    left_margin = int(page_width * 0.08)
    right_margin = int(page_width * 0.92)
    min_gap = max(4, int(page_width * min_gap_fraction))

    # --- Strategy 1: page-wide coverage gap ---
    n_slots = int(page_width) + 1
    covered = bytearray(n_slots)
    for word in words:
        lo = max(0, int(word["x0"]))
        hi = min(n_slots - 1, int(word["x1"]) + 1)
        for i in range(lo, hi):
            covered[i] = 1

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
                split_points.append((gap_start + x) / 2.0)
            in_gap = False

    if split_points:
        boundaries = [0.0] + split_points + [page_width]
        return [(boundaries[i], boundaries[i + 1]) for i in range(len(boundaries) - 1)]

    # --- Strategy 2: per-row gap voting ---
    # Group words into rows (y within 3pt).
    rows = {}
    for w in words:
        row_key = round(w["top"] / 3) * 3
        rows.setdefault(row_key, []).append(w)

    # For each row find the largest gap that falls in the middle of the page.
    interior_left = page_width * 0.25
    interior_right = page_width * 0.75
    vote_bucket_size = 10  # px — resolution of gap position votes

    gap_votes: dict[int, int] = {}
    for row_words in rows.values():
        row_sorted = sorted(row_words, key=lambda w: w["x0"])
        for j in range(len(row_sorted) - 1):
            gap_start_x = row_sorted[j]["x1"]
            gap_end_x = row_sorted[j + 1]["x0"]
            gap_size = gap_end_x - gap_start_x
            gap_mid = (gap_start_x + gap_end_x) / 2.0
            if gap_size >= min_gap and interior_left <= gap_mid <= interior_right:
                bucket = round(gap_mid / vote_bucket_size) * vote_bucket_size
                gap_votes[bucket] = gap_votes.get(bucket, 0) + 1

    if not gap_votes:
        return [(0.0, page_width)]

    best_pos, best_votes = max(gap_votes.items(), key=lambda kv: kv[1])

    # Require at least 3 rows to agree before treating this as a real column split.
    if best_votes < 3:
        return [(0.0, page_width)]

    split_x = float(best_pos)
    return [(0.0, split_x), (split_x, page_width)]


def _words_to_text(words):
    """
    Reconstruct plain text from a list of pdfplumber word dicts.

    Words are grouped into lines by their `top` (y) coordinate (within 6pt) and
    sorted left-to-right within each line.  Lines are joined with newlines.
    """
    if not words:
        return ""

    rows: dict[int, list] = {}
    for w in words:
        row_key = round(w["top"] / 6) * 6
        rows.setdefault(row_key, []).append(w)

    lines = []
    for y in sorted(rows.keys()):
        row_words = sorted(rows[y], key=lambda w: w["x0"])
        lines.append(" ".join(w["text"] for w in row_words))

    return "\n".join(lines)


def extract_page_text(page):
    """
    Extract text from a single page, preserving correct reading order.

    Steps:
    1. Deduplicate overlapping characters (fixes bold/shadow double-rendering).
    2. Detect column layout via horizontal gap analysis.
    3. Single-column pages: use pdfplumber's built-in extract_text.
    4. Multi-column pages: assign each word to a column by its left edge (x0),
       reconstruct text per column, then concatenate columns left-to-right.
       Using x0-based assignment (rather than crop) avoids clipping words whose
       bounding boxes straddle the column boundary.
    """
    page = page.dedupe_chars(tolerance=1)
    columns = find_column_boundaries(page)

    if len(columns) == 1:
        return page.extract_text(x_tolerance=3, y_tolerance=3) or ""

    all_words = page.extract_words(x_tolerance=3, y_tolerance=3)

    parts = []
    for col_x0, col_x1 in columns:
        col_words = [w for w in all_words if col_x0 <= w["x0"] < col_x1]
        text = _words_to_text(col_words)
        if text.strip():
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
