"""
Process pre-cleaned .txt rulebooks into structured chunks for RAG retrieval.

Reads .txt files from data/processed_rulebooks/<game>_*.txt, parses sections
using {Title} markers and numbered headers, enforces chunk-size bounds, and
writes one structured JSON file per game to data/chunks/<game>_rulebook_chunks.json.

No LLM calls — all processing is deterministic heuristics.

Usage:
    python src/process_rulebooks.py                  # process all games
    python src/process_rulebooks.py --game catan     # one game
    python src/process_rulebooks.py --dry-run        # list files only
    python src/process_rulebooks.py --verbose        # per-section detail
"""

import argparse
import json
import re
from pathlib import Path

from bgg_config import GAMES


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MIN_CHUNK_WORDS = 50     # was 100 — allow small self-contained sections
MAX_CHUNK_WORDS = 400    # was 500 — tighter chunks reduce noise for the generator
OVERLAP_WORDS = 0        # was 50  — no longer needed with semantic splitting

# Matches section titles that indicate the reference/almanac tier.
# [B-G]\.\s catches Root's appendix sections (B. Components, C. Variant Maps, etc.)
_REFERENCE_RE = re.compile(
    r'(?i)^(almanac|reference|appendix|glossary|index|[B-G]\.\s)'
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _word_count(text):
    return len(text.split())


# ---------------------------------------------------------------------------
# Stage 1: Section parsing
# ---------------------------------------------------------------------------

def classify_tier(title: str) -> str:
    """Return 'reference' or 'core_rules' based on the section title."""
    return 'reference' if _REFERENCE_RE.match(title) else 'core_rules'


def parse_sections(text: str) -> list:
    """
    Parse pre-formatted rulebook text into a list of section dicts.

    Recognized markers:
      [PAGE X]       — update current page; not added to body
      {Title}        — start a new section; title is the text inside braces
      N.N... Heading — numbered header (<=80 chars, no sentence continuation)
      blank line     — paragraph separator; preserved in body

    Tier is sticky: once a section triggers 'reference', all subsequent
    sections in the file are also 'reference'.

    Returns a list of dicts:
      {
          "section_title":     str,
          "source_tier":       str,   # "core_rules" or "reference"
          "body":              str,
          "page_start":        int,
          "page_end":          int,
          "has_explicit_title": bool,  # True if started by {Title}, False if numbered header
      }
    """
    lines = text.splitlines()
    sections = []

    current_title = 'Introduction'
    current_body = []
    current_page = 1
    page_start = 1
    current_tier = 'core_rules'
    current_has_explicit_title = False  # default intro section is not a {Title}
    first_heading_seen = False

    def _flush(end_page):
        body = '\n'.join(current_body).strip()
        # Skip the implicit Introduction if nothing appears before the first heading
        if not first_heading_seen and not body:
            return
        sections.append({
            'section_title': current_title,
            'source_tier': current_tier,
            'body': body,
            'page_start': page_start,
            'page_end': end_page,
            'has_explicit_title': current_has_explicit_title,
        })

    def _new_section(title, start_page, has_explicit_title):
        nonlocal current_title, current_body, page_start, current_tier
        nonlocal current_has_explicit_title, first_heading_seen
        first_heading_seen = True
        if classify_tier(title) == 'reference':
            current_tier = 'reference'
        current_title = title
        current_body = []
        page_start = start_page
        current_has_explicit_title = has_explicit_title

    for line in lines:
        stripped = line.strip()

        # [PAGE X] marker — update page, do not add to body
        page_match = re.match(r'^\[PAGE\s+(\d+)\]$', stripped)
        if page_match:
            current_page = int(page_match.group(1))
            continue

        # {Title} pattern — start a new section
        title_match = re.match(r'^\{(.+)\}$', stripped)
        if title_match:
            _flush(current_page)
            _new_section(title_match.group(1), current_page, has_explicit_title=True)
            continue

        # Numbered header: e.g. "1.1 Rules Conflicts"
        # Rejected if >80 chars or if the heading text continues as a sentence
        # (e.g. "1.5.1 Limits. Pieces are limited...").
        num_match = re.match(r'^(\d+\.[\d.]*)\s+(.+)$', stripped)
        if num_match and len(stripped) <= 80:
            rest = num_match.group(2)
            if not re.search(r'\.\s+[A-Z]', rest):
                _flush(current_page)
                _new_section(stripped, current_page, has_explicit_title=False)
                continue

        # Blank line or content line — append to current section body
        current_body.append(line.rstrip())

    # Flush the final section
    _flush(current_page)

    return sections


# ---------------------------------------------------------------------------
# Stage 2: Chunking
# ---------------------------------------------------------------------------

def _merge_small_sections(sections):
    """
    Forward-merge sections that are BOTH:
      - shorter than MIN_CHUNK_WORDS, AND
      - lack an explicit {Title} heading (has_explicit_title == False)

    Sections with explicit titles are never merged — they represent
    distinct rulebook topics that should remain separate chunks.
    """
    if not sections:
        return []

    result = []
    pending = None

    for section in sections:
        if pending is None:
            # Only merge candidates without explicit titles
            if (_word_count(section['body']) < MIN_CHUNK_WORDS
                    and not section.get('has_explicit_title', False)):
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
                'page_start': min(pending['page_start'], section['page_start']),
                'page_end': max(pending['page_end'], section['page_end']),
                'has_explicit_title': section.get('has_explicit_title', False),
            }
            pending = None
            if (_word_count(merged['body']) < MIN_CHUNK_WORDS
                    and not merged.get('has_explicit_title', False)):
                pending = merged
            else:
                result.append(merged)

    # Handle leftover pending
    if pending is not None:
        if result:
            prev = result[-1]
            merged_body = (prev['body'] + '\n\n' + pending['body']).strip()
            result[-1] = {
                'section_title': f"{prev['section_title']} / {pending['section_title']}",
                'source_tier': prev['source_tier'],
                'body': merged_body,
                'page_start': min(prev['page_start'], pending['page_start']),
                'page_end': max(prev['page_end'], pending['page_end']),
                'has_explicit_title': prev.get('has_explicit_title', False),
            }
        else:
            result.append(pending)

    return result


def _split_para_by_sentences(para):
    """Split a paragraph on sentence boundaries, each <= MAX_CHUNK_WORDS."""
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


# Regex patterns for sub-topic detection in _split_section_semantically
_CALLOUT_RE = re.compile(
    r'^(?:Important|Note|Hint|Tip|Special Case|Reminder|Example)\s*:', re.IGNORECASE
)
_NUMBERED_ITEM_RE = re.compile(
    r'^(?:\(\d+\)|\d+\.|[a-d]\)|Step\s+\d+)', re.IGNORECASE
)
_CONCEPT_INTRO_RE = re.compile(
    r'^[A-Z][A-Za-z\s]+(?:\([^)]*\))?\s*[:.]'  # e.g. "Generic Harbor (3:1):" or "Road Building."
)


def _split_section_semantically(section):
    """
    Split a large section at sub-topic boundaries.

    Strategy:
      1. Attach callouts (Important:/Note:/etc.) to the preceding paragraph.
      2. Identify sub-topic boundaries (numbered items, concept introductions).
      3. Pack sub-topics into chunks up to MAX_CHUNK_WORDS.
      4. Fall back to sentence-level splitting for oversized sub-topics.
      5. No overlap — semantic boundaries make it unnecessary.

    Returns a list of section-like dicts.
    """
    raw_paragraphs = [p.strip() for p in re.split(r'\n\s*\n', section['body']) if p.strip()]
    if not raw_paragraphs:
        return [section]

    # Step 1: Attach callouts to preceding paragraph
    merged_paras = []
    for para in raw_paragraphs:
        if merged_paras and _CALLOUT_RE.match(para):
            merged_paras[-1] = merged_paras[-1] + '\n\n' + para
        else:
            merged_paras.append(para)

    # Step 2: Group into sub-topics at boundary paragraphs
    sub_topics = []       # each is a list of paragraphs
    current_group = []

    for i, para in enumerate(merged_paras):
        excerpt = para[:60] if len(para) > 60 else para
        is_boundary = (
            i > 0  # first paragraph is never a boundary
            and (
                _NUMBERED_ITEM_RE.match(para)
                or _CONCEPT_INTRO_RE.match(excerpt)
            )
        )
        if is_boundary and current_group:
            sub_topics.append(current_group)
            current_group = [para]
        else:
            current_group.append(para)

    if current_group:
        sub_topics.append(current_group)

    # Step 3: Pack sub-topics into chunks up to MAX_CHUNK_WORDS
    chunks = []
    current_paras = []
    current_wc = 0
    part_num = 1

    def _flush_chunk():
        nonlocal part_num
        body = '\n\n'.join(current_paras)
        title = (
            f"{section['section_title']} (Part {part_num})"
            if part_num > 1 or len(sub_topics) > 1
            else section['section_title']
        )
        chunks.append({
            'section_title': title,
            'source_tier': section['source_tier'],
            'body': body.strip(),
            'page_start': section['page_start'],
            'page_end': section['page_end'],
            'has_explicit_title': section.get('has_explicit_title', False),
        })
        part_num += 1

    for sub_topic in sub_topics:
        sub_text = '\n\n'.join(sub_topic)
        sub_wc = _word_count(sub_text)

        # If this single sub-topic is too large, split it by sentences
        if sub_wc > MAX_CHUNK_WORDS:
            if current_paras:
                _flush_chunk()
                current_paras = []
                current_wc = 0
            for piece in _split_para_by_sentences(sub_text):
                current_paras = [piece]
                current_wc = _word_count(piece)
                _flush_chunk()
                current_paras = []
                current_wc = 0
            continue

        # Would adding this sub-topic exceed the limit?
        if current_paras and current_wc + sub_wc > MAX_CHUNK_WORDS:
            _flush_chunk()
            current_paras = []
            current_wc = 0

        current_paras.extend(sub_topic)
        current_wc += sub_wc

    if current_paras:
        _flush_chunk()

    # If everything fit in one chunk, restore the original title (no Part suffix)
    if len(chunks) == 1:
        chunks[0]['section_title'] = section['section_title']

    return chunks if chunks else [section]


def build_chunks(sections, game_name):
    """
    Apply size rules to sections and return final chunk dicts.
      1. Merge small sections forward (only non-{Title} sections below MIN_CHUNK_WORDS)
      2. Split large sections at semantic sub-topic boundaries (_split_section_semantically)
      3. Assign metadata (includes page_start / page_end for citation support)
    """
    merged = _merge_small_sections(sections)

    raw = []
    for section in merged:
        if _word_count(section['body']) > MAX_CHUNK_WORDS:
            raw.extend(_split_section_semantically(section))
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
            'page_start': item['page_start'],
            'page_end': item['page_end'],
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
    Parse and chunk a single pre-cleaned .txt rulebook file.
    Returns (list_of_chunks, n_sections_detected).
    """
    text = txt_path.read_text(encoding='utf-8')
    sections = parse_sections(text)

    if verbose:
        print(f'    Sections detected in {txt_path.name}:')
        for s in sections:
            wc = _word_count(s['body'])
            tier_tag = '[ref]' if s['source_tier'] == 'reference' else '     '
            print(f'      {tier_tag} {wc:>4}w  {s["section_title"]!r}')

    chunks = build_chunks(sections, game_name)
    return chunks, len(sections)


def process_game(game_name, input_dir, output_dir, verbose=False):
    """
    Find all .txt files for game_name, process each one, combine chunks,
    and write to output_dir/<game_name>_rulebook_chunks.json.
    """
    txt_files = sorted(input_dir.glob(f'{game_name}_*.txt'))
    if not txt_files:
        print(f'  No .txt files found matching {game_name}_*.txt -- skipping.')
        return

    all_chunks = []
    total_sections = 0

    for txt_path in txt_files:
        print(f'  Processing {txt_path.name} ...')
        chunks, n_sections = process_file(txt_path, game_name, verbose=verbose)
        total_sections += n_sections
        all_chunks.extend(chunks)
        print(f'    {n_sections} sections -> {len(chunks)} chunks')

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

    print(f'  Saved {grand_total} chunks ({total_sections} sections) -> {out_path}')


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Process rulebook .txt files into structured JSON chunks for RAG.'
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
    input_dir = project_root / 'data' / 'processed_rulebooks'
    output_dir = project_root / 'data' / 'chunks'

    games_to_process = {args.game: GAMES[args.game]} if args.game else GAMES

    if args.dry_run:
        print('Rulebook Processor -- dry run')
        print(f'Input:  {input_dir}\n')
        for game_name in games_to_process:
            txt_files = sorted(input_dir.glob(f'{game_name}_*.txt'))
            print(f'[{game_name}] {len(txt_files)} file(s):')
            for f in txt_files:
                print(f'    {f.name}')
        return

    print('Rulebook Processor')
    print(f'Input:  {input_dir}')
    print(f'Output: {output_dir}\n')

    for game_name in games_to_process:
        print(f'[{game_name}]')
        try:
            process_game(game_name, input_dir, output_dir, verbose=args.verbose)
        except Exception as e:
            print(f'  ERROR: {e}')
        print()


if __name__ == '__main__':
    main()
