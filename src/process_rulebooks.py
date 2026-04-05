"""
Process raw .txt rulebook extractions into structured chunks for RAG retrieval.

Reads .txt files from data/processed_rulebooks/<game>_*.txt, applies cleaning
and section-detection heuristics, enforces chunk-size bounds, and writes one
structured JSON file per game to data/chunks/<game>_rulebook_chunks.json.

No LLM calls — all processing is deterministic heuristics.

Usage:
    python src/process_rulebooks.py                  # process all games
    python src/process_rulebooks.py --game catan     # one game
    python src/process_rulebooks.py --dry-run        # list files, don't process
    python src/process_rulebooks.py --verbose        # print section-level detail
"""

import argparse
import json
import re
from pathlib import Path

from bgg_config import GAMES


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MIN_CHUNK_WORDS = 100
MAX_CHUNK_WORDS = 500
OVERLAP_WORDS = 50

# Lines starting with these words mark the start of the reference tier.
TIER_BOUNDARY_RE = re.compile(
    r'(?i)^(almanac|reference|appendix|glossary|index)\b'
)


# ---------------------------------------------------------------------------
# Stage 1: Cleaning
# ---------------------------------------------------------------------------

def remove_watermarks(lines):
    """
    Strip reversed/garbled publisher watermarks and copyright footers.

    Patterns targeted:
    - "HbmG natC 5102 ©" and similar reversed Catan GmbH strings
    - Lines that are only "=" (column-separator artifacts)
    """
    watermark_re = re.compile(r'(?i)(HbmG|natC|nataC|Ctan GmbH)')
    equals_re = re.compile(r'^\s*=\s*$')
    return [
        line for line in lines
        if not watermark_re.search(line) and not equals_re.match(line)
    ]


def remove_garbled_blocks(lines):
    """
    Remove two families of extraction failures.

    1. Long lines (>80 chars) with high space-to-char ratio (>0.4) AND high
       uppercase-to-alpha ratio (>0.3) — these are interleaved multi-column
       garble that ended up on a single line.

    2. Runs of 5+ consecutive very-short lines (≤3 non-whitespace chars each)
       that are vertically-shredded individual letters or punctuation marks.
    """
    # Pass 1 — remove garbled long lines
    after_long = []
    for line in lines:
        stripped = line.strip()
        if len(stripped) > 80:
            total = len(stripped)
            spaces = stripped.count(' ')
            alpha = sum(1 for c in stripped if c.isalpha())
            uppers = sum(1 for c in stripped if c.isupper())
            space_ratio = spaces / total
            upper_ratio = (uppers / alpha) if alpha > 0 else 0.0
            if space_ratio > 0.4 and upper_ratio > 0.3:
                continue
        after_long.append(line)

    # Pass 2 — remove runs of 5+ very-short lines
    result = []
    i = 0
    n = len(after_long)
    while i < n:
        non_ws = len(re.sub(r'\s', '', after_long[i].strip()))
        if non_ws <= 3:
            # Measure the length of this short-line run
            j = i
            while j < n and len(re.sub(r'\s', '', after_long[j].strip())) <= 3:
                j += 1
            if j - i >= 5:
                i = j  # skip the whole run
                continue
        result.append(after_long[i])
        i += 1

    return result


def remove_noise_lines(lines):
    """
    Drop lines that carry no rules content.

    Removes:
    - Standalone page numbers  (only digits + optional whitespace)
    - Pip / bullet sequences   (only •, spaces, and digits — e.g. "••• • ••••")
    - Stray characters         (≤2 non-whitespace chars)
    """
    cleaned = []
    for line in lines:
        stripped = line.strip()

        if not stripped:
            cleaned.append('')
            continue

        # Standalone page number
        if re.match(r'^\d+$', stripped):
            continue

        # Pip / bullet sequence (only bullets, digits, and spaces)
        if re.match(r'^[\s•\d]+$', stripped):
            continue

        # Stray line with ≤2 meaningful characters
        non_ws = re.sub(r'\s', '', stripped)
        if len(non_ws) <= 2:
            continue

        cleaned.append(line)

    return cleaned


def normalize(lines):
    """
    Collapse 3+ consecutive blank lines to 2 and strip trailing whitespace
    from every line.  Returns a single cleaned string.
    """
    result = []
    blank_run = 0
    for line in lines:
        if line.strip() == '':
            blank_run += 1
            if blank_run <= 2:
                result.append('')
        else:
            blank_run = 0
            result.append(line.rstrip())
    return '\n'.join(result).strip()


def clean_text(text):
    """
    Apply all four cleaning passes to raw extracted .txt content and return
    the cleaned string.  Passes are applied in order:
      1. Watermark removal
      2. Garbled-block removal
      3. Noise-line removal
      4. Whitespace normalization
    """
    lines = text.splitlines()
    lines = remove_watermarks(lines)
    lines = remove_garbled_blocks(lines)
    lines = remove_noise_lines(lines)
    return normalize(lines)


# ---------------------------------------------------------------------------
# Stage 2: Section detection
# ---------------------------------------------------------------------------

def _mid_word_upper_count(words):
    """Count uppercase letters that appear mid-word (not word-initial).

    All-uppercase words (e.g. GAME, RULES, SPACE) are skipped — they are
    normal emphasis or acronyms, not stylized headings like Catan's 'lonGest'.
    """
    count = 0
    for word in words:
        bare = word.lstrip('("\'')
        alpha = [c for c in bare if c.isalpha()]
        # Skip words that are entirely uppercase (acronyms / emphasis)
        if alpha and all(c.isupper() for c in alpha):
            continue
        for i, ch in enumerate(bare):
            if i > 0 and ch.isupper():
                count += 1
    return count


# Characters that, if trailing, indicate a line is a sentence not a heading.
_SENTENCE_ENDERS = set('.,:;!?\u201d\u2019\u00bb"\'')


def is_heading(line, prev_is_blank):
    """
    Return True if *line* should be treated as a section heading.

    Rules (any match qualifies):
      1. ALL-CAPS short line   -- matches ^[A-Z][A-Z\\s&,/()\"'-]{2,59}$, <=8 words
      2. Stylized mixed caps   -- >=2 mid-word uppercase letters, <=8 words
                                  (e.g. Catan's "lonGest Road", "distanCe rule")
      3. Numbered header       -- digit(s) + dot + optional sub-levels + space + Capital
                                  AND no inline sentence continuation after the title
      4. Lettered sub-header   -- ^[a-d])\\s+[A-Z]
      5. Short title-case line -- <=8 words, starts capital, no trailing sentence-ending
                                  punctuation, preceded by blank line

    Guards that disqualify a candidate:
      - Line is longer than 60 characters (likely a sentence, not a heading)
      - Not preceded by a blank line (except rules 3 & 4, which are structural)
    """
    stripped = line.strip()
    if not stripped:
        return False

    # Lines > 60 chars are sentences, not headings
    if len(stripped) > 60:
        return False

    words = stripped.split()

    # Rule 1 — ALL CAPS (<=8 words)
    if re.match(r'^[A-Z][A-Z\s&,/()"\'\-]{2,59}$', stripped) and len(words) <= 8:
        return True

    # Rule 2 — Stylized mixed caps such as Catan's heading style (2–8 words).
    # Requires at least 2 words so single garbled tokens don't trigger.
    if 2 <= len(words) <= 8 and _mid_word_upper_count(words) >= 2:
        return True

    # Rules 3 & 4 are positional/structural — no blank-line requirement.

    # Rule 3 — Numbered header: requires at least one dot after the leading
    # digit(s) to avoid matching bare "2 Victory Points" etc.
    # Also rejects lines like "1.1.1 Precedence. If a card..." where content
    # follows inline (detected by ". Capital" after stripping the number prefix).
    if re.match(r'^\d+\.\d*(\.\d+)*\s+[A-Z]', stripped):
        rest = re.sub(r'^\d+[\d.]*\s+', '', stripped)
        if not re.search(r'\.\s+[A-Z]', rest):
            return True

    # Rule 4 — Lettered sub-header a)–d)
    if re.match(r'^[a-d]\)\s+[A-Z]', stripped):
        return True

    # Rule 5 — Short title-case line; must be preceded by a blank line.
    # Exclude lines ending with sentence punctuation or closing quote marks.
    if (prev_is_blank
            and len(words) <= 8
            and stripped[0].isupper()
            and stripped[-1] not in _SENTENCE_ENDERS):
        return True

    return False


def detect_sections(text):
    """
    Walk the cleaned text line-by-line and split it into sections.

    Each section is a dict:
        section_title : str   — heading text (or "Introduction" if none found)
        source_tier   : str   — "core_rules" or "reference"
        body          : str   — all text under this heading

    The tier flips to "reference" when a line matches TIER_BOUNDARY_RE and
    stays "reference" for all subsequent sections.
    """
    lines = text.splitlines()
    sections = []
    current_title = 'Introduction'
    current_body = []
    current_tier = 'core_rules'
    prev_is_blank = True   # treat document start as preceded by blank

    for line in lines:
        stripped = line.strip()

        if not stripped:
            current_body.append('')
            prev_is_blank = True
            continue

        if is_heading(line, prev_is_blank):
            # Flush the current section (skip empty Introduction placeholder)
            body = '\n'.join(current_body).strip()
            if body:
                sections.append({
                    'section_title': current_title,
                    'source_tier': current_tier,
                    'body': body,
                })

            # Check for tier transition before updating current_title
            if TIER_BOUNDARY_RE.match(stripped):
                current_tier = 'reference'

            current_title = stripped
            current_body = []
        else:
            current_body.append(line.rstrip())

        prev_is_blank = False

    # Flush the final section
    body = '\n'.join(current_body).strip()
    if body:
        sections.append({
            'section_title': current_title,
            'source_tier': current_tier,
            'body': body,
        })

    return sections


# ---------------------------------------------------------------------------
# Stage 3: Chunking
# ---------------------------------------------------------------------------

def _word_count(text):
    return len(text.split())


def _merge_small_sections(sections):
    """
    Forward-merge sections shorter than MIN_CHUNK_WORDS words with the next
    section.  Combined titles use " / " as separator.  If the last section is
    still too small after exhausting forward candidates, it is merged backward
    into the previous section.
    """
    if not sections:
        return []

    result = []
    pending = None   # accumulated small sections not yet emitted

    for section in sections:
        if pending is None:
            if _word_count(section['body']) < MIN_CHUNK_WORDS:
                pending = dict(section)
            else:
                result.append(dict(section))
        else:
            # Merge pending into this section
            merged_body = (
                (pending['body'] + '\n\n' + section['body']).strip()
                if pending['body'] and section['body']
                else pending['body'] or section['body']
            )
            merged = {
                'section_title': f"{pending['section_title']} / {section['section_title']}",
                'source_tier': pending['source_tier'],
                'body': merged_body,
            }
            pending = None
            # The merged chunk may still be small — keep accumulating
            if _word_count(merged['body']) < MIN_CHUNK_WORDS:
                pending = merged
            else:
                result.append(merged)

    # Handle any leftover pending (last section was too small)
    if pending is not None:
        if result:
            prev = result[-1]
            merged_body = (prev['body'] + '\n\n' + pending['body']).strip()
            result[-1] = {
                'section_title': f"{prev['section_title']} / {pending['section_title']}",
                'source_tier': prev['source_tier'],
                'body': merged_body,
            }
        else:
            # Entire document was one tiny section — emit it as-is
            result.append(pending)

    return result


def _split_para_by_sentences(para):
    """
    Fallback: split a paragraph that is itself larger than MAX_CHUNK_WORDS
    on sentence boundaries.  Returns a list of sentence-grouped strings,
    each ≤ MAX_CHUNK_WORDS words where possible.
    """
    # Split on '. ', '! ', '? ' followed by a capital or end of string
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', para)
    pieces = []
    current_sents = []
    current_wc = 0
    for sent in sentences:
        sw = _word_count(sent)
        if current_sents and current_wc + sw > MAX_CHUNK_WORDS:
            pieces.append(' '.join(current_sents))
            current_sents = [sent]
            current_wc = sw
        else:
            current_sents.append(sent)
            current_wc += sw
    if current_sents:
        pieces.append(' '.join(current_sents))
    return pieces if pieces else [para]


def _split_large_section(section):
    """
    Split a section exceeding MAX_CHUNK_WORDS words on paragraph boundaries.
    If a single paragraph itself exceeds MAX_CHUNK_WORDS, it is further split
    on sentence boundaries.  Each sub-chunk is prefixed with the last
    OVERLAP_WORDS words of the previous sub-chunk to preserve cross-boundary
    context.  Returns a list of section-like dicts with updated titles.
    """
    raw_paragraphs = [p.strip() for p in re.split(r'\n\s*\n', section['body']) if p.strip()]
    if not raw_paragraphs:
        return [section]

    # Expand any paragraph that is itself too large into sentence-groups
    paragraphs = []
    for p in raw_paragraphs:
        if _word_count(p) > MAX_CHUNK_WORDS:
            paragraphs.extend(_split_para_by_sentences(p))
        else:
            paragraphs.append(p)

    sub_chunks = []
    current_paras = []
    current_wc = 0
    overlap_prefix = ''
    part_num = 1

    def _flush():
        nonlocal overlap_prefix, part_num
        body = '\n\n'.join(current_paras)
        if overlap_prefix:
            body = overlap_prefix + '\n\n' + body
        sub_chunks.append({
            'section_title': f"{section['section_title']} (Part {part_num})",
            'source_tier': section['source_tier'],
            'body': body.strip(),
        })
        # Build overlap prefix from the last OVERLAP_WORDS words of this chunk
        all_words = '\n\n'.join(current_paras).split()
        overlap_prefix = ' '.join(all_words[-OVERLAP_WORDS:])
        part_num += 1

    for para in paragraphs:
        para_wc = _word_count(para)
        if current_paras and current_wc + para_wc > MAX_CHUNK_WORDS:
            _flush()
            current_paras = [para]
            current_wc = para_wc
        else:
            current_paras.append(para)
            current_wc += para_wc

    if current_paras:
        # If only one part was ever produced, drop the "(Part N)" suffix
        if part_num == 1:
            sub_chunks.append(section)
        else:
            _flush()

    return sub_chunks if sub_chunks else [section]


def build_chunks(sections, game_name):
    """
    Apply size rules to a list of sections and return final chunk dicts.

    Order of operations:
      1. Merge small sections (<MIN_CHUNK_WORDS) forward.
      2. Split large sections (>MAX_CHUNK_WORDS) on paragraph boundaries.
      3. Assign chunk_id, indices, and metadata fields.
    """
    merged = _merge_small_sections(sections)

    raw = []
    for section in merged:
        wc = _word_count(section['body'])
        if wc > MAX_CHUNK_WORDS:
            raw.extend(_split_large_section(section))
        else:
            raw.append(section)

    total = len(raw)
    chunks = []
    for i, item in enumerate(raw):
        chunks.append({
            'chunk_id': f'{game_name}_rulebook_{i:03d}',
            'source_type': 'rulebook',
            'game_name': game_name,
            'section_title': item['section_title'],
            'source_tier': item['source_tier'],
            'content': item['body'],
            'chunk_index': i,
            'total_chunks': total,
            'retrieval_priority': 1,
        })

    return chunks


# ---------------------------------------------------------------------------
# Processing pipeline
# ---------------------------------------------------------------------------

def process_file(txt_path, game_name, verbose=False):
    """
    Run the full three-stage pipeline on a single .txt file.
    Returns (list_of_chunks, n_sections_detected).
    """
    text = txt_path.read_text(encoding='utf-8')

    # Stage 1 — clean
    cleaned = clean_text(text)

    # Stage 2 — section detection
    sections = detect_sections(cleaned)

    if verbose:
        print(f'    Sections detected in {txt_path.name}:')
        for s in sections:
            wc = _word_count(s['body'])
            tier_tag = '[ref]' if s['source_tier'] == 'reference' else '     '
            print(f'      {tier_tag} {wc:>4}w  {s["section_title"]!r}')

    # Stage 3 — chunk
    chunks = build_chunks(sections, game_name)

    return chunks, len(sections)


def process_game(game_name, extracted_dir, output_dir, verbose=False):
    """
    Find all .txt files for *game_name*, process each one, combine all chunks
    into a single output JSON at output_dir/<game_name>_rulebook_chunks.json.
    """
    txt_files = sorted(extracted_dir.glob(f'{game_name}_*.txt'))
    if not txt_files:
        print(f'  No .txt files found matching {game_name}_*.txt — skipping.')
        return

    all_chunks = []
    total_sections = 0

    for txt_path in txt_files:
        print(f'  Processing {txt_path.name} ...')
        chunks, n_sections = process_file(txt_path, game_name, verbose=verbose)
        total_sections += n_sections
        all_chunks.extend(chunks)
        print(f'    {n_sections} sections → {len(chunks)} chunks')

    # Re-sequence chunk_ids and indices across all source files
    grand_total = len(all_chunks)
    for i, chunk in enumerate(all_chunks):
        chunk['chunk_id'] = f'{game_name}_rulebook_{i:03d}'
        chunk['chunk_index'] = i
        chunk['total_chunks'] = grand_total

    source_files = [f.name for f in txt_files]
    output = {
        'game_name': game_name,
        'source_file': source_files[0] if len(source_files) == 1 else source_files,
        'total_chunks': grand_total,
        'chunks': all_chunks,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f'{game_name}_rulebook_chunks.json'
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f'  Saved {grand_total} chunks ({total_sections} sections) → {out_path}')


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Process rulebook .txt extractions into structured JSON chunks for RAG.'
    )
    parser.add_argument(
        '--game',
        type=str,
        default=None,
        help="Process a single game (e.g. 'catan'). Default: all games.",
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='List input files that would be processed without writing output.',
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Print per-section details (title, word count, tier) during processing.',
    )
    args = parser.parse_args()

    if args.game and args.game not in GAMES:
        parser.error(f"Unknown game '{args.game}'. Valid options: {', '.join(GAMES)}")

    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    extracted_dir = project_root / 'data' / 'processed_rulebooks'
    output_dir = project_root / 'data' / 'chunks'

    games_to_process = {args.game: GAMES[args.game]} if args.game else GAMES

    if args.dry_run:
        print(f'Rulebook Processor — dry run')
        print(f'Input:  {extracted_dir}\n')
        for game_name in games_to_process:
            txt_files = sorted(extracted_dir.glob(f'{game_name}_*.txt'))
            print(f'[{game_name}] {len(txt_files)} file(s):')
            for f in txt_files:
                print(f'    {f.name}')
        return

    print(f'Rulebook Processor')
    print(f'Input:  {extracted_dir}')
    print(f'Output: {output_dir}\n')

    for game_name in games_to_process:
        print(f'[{game_name}]')
        try:
            process_game(game_name, extracted_dir, output_dir, verbose=args.verbose)
        except Exception as e:
            print(f'  ERROR: {e}')
        print()

    print('Done!')


if __name__ == '__main__':
    main()
