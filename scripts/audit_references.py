#!/usr/bin/env python3
"""Check active TeX citations against the database and actual ACM BBL/AUX.

This is local identity/presentation consistency, not DOI resolution or a claim
that cited original texts support the manuscript. Unpresented database records
are reserves, not missing citations or printed bibliography errors.
"""
from pathlib import Path
import collections
import csv
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from bibliography_tools import parse_bib


def uncomment(text):
    return re.sub(r'(?<!\\)%[^\n]*', '', text)


def argument(text, start):
    """Read a balanced braced argument, retaining accents and inner groups."""
    start += len(text[start:]) - len(text[start:].lstrip())
    if start >= len(text) or text[start] != '{':
        raise ValueError('expected braced bibliography argument')
    depth, pos = 1, start + 1
    while pos < len(text):
        if text[pos] == '\\':
            pos += 2
            continue
        if text[pos] == '{': depth += 1
        if text[pos] == '}': depth -= 1
        if depth == 0: return text[start + 1:pos]
        pos += 1
    raise ValueError('unclosed bibliography argument')


def values(text, pattern):
    return [argument(text, m.end()) for m in re.finditer(pattern, text)]


def normalized(text):
    # Ignore grouping, nonbreaking spaces and wrapping, not spelling, author
    # order, accents, punctuation or title case.
    return ' '.join(text.replace('{', '').replace('}', '').replace('~', ' ').split())


def active_sources(paper):
    """Follow this manuscript's literal input/include graph from main.tex."""
    pending, sources = [paper / 'main.tex'], {}
    while pending:
        path = pending.pop().resolve()
        if path in sources: continue
        if not path.is_relative_to(paper.resolve()):
            raise ValueError('TeX input outside the paper tree')
        text = uncomment(path.read_text(encoding='utf-8'))
        sources[path] = text
        for name in re.findall(r'\\(?:input|include)\s*\{([^}]+)\}', text):
            child = paper / name
            if not child.suffix: child = child.with_suffix('.tex')
            pending.append(child)
    return sources


def bbl_items(text):
    text = uncomment(text)
    items = list(re.finditer(r'\\bibitem(?:\[[^\]]*\])?\s*\{([^}]+)\}', text))
    return [(m[1], text[m.end():items[i + 1].start() if i + 1 < len(items) else len(text)]) for i, m in enumerate(items)]


def replay_bbl(paper):
    """Apply the actual bundled style to current inputs, without changing them.

    BibTeX name parsing/formatting need not reproduce database punctuation
    literally (e.g. Ken-ichi is rendered as Ken ichi by this style/toolchain).
    Replaying avoids accepting arbitrary spelling/punctuation normalization.
    """
    engine = shutil.which('bibtex8') or shutil.which('bibtex')
    if not engine: raise RuntimeError('BibTeX is required for current BBL identity checking')
    with tempfile.TemporaryDirectory(prefix='tidemark-bbl-check-') as temp:
        scratch = Path(temp)
        for name in ('main.aux', 'references.bib', 'ACM-Reference-Format.bst'):
            shutil.copy2(paper / name, scratch / name)
        proc = subprocess.run([engine, 'main'], cwd=scratch, capture_output=True, text=True)
        if proc.returncode or 'Warning--' in (scratch / 'main.blg').read_text(errors='replace'):
            raise RuntimeError('Current BBL replay failed: ' + proc.stdout + proc.stderr)
        return (scratch / 'main.bbl').read_text(encoding='utf-8')


def check_bibliography(entries, used, bbl, aux, nocited=(), minimum=60, expected_bbl=None):
    database = {e['key']: e for e in entries}
    doi = [e.get('doi', '').lower() for e in entries]
    items = bbl_items(bbl)
    rendered = [key for key, _ in items]
    replay = dict(bbl_items(expected_bbl)) if expected_bbl is not None else None
    expected = set(database) if '*' in nocited else set(used) | set(nocited)
    identity_errors = []
    for key, block in items:
        if key not in database: continue
        entry = database[key]
        authors = values(block, r'\\bibfield\{author\}')
        people = values(authors[0], r'\\bibinfo\{person\}') if len(authors) == 1 else []
        titles = values(block, r'\\showarticletitle\b')
        years = values(block, r'\\bibinfo\{year\}')
        dois = values(block, r'\\nolinkurl\b')
        expected_people = [normalized(a) for a in re.split(r'\s+and\s+', entry.get('author', ''))]
        if replay is not None:
            expected_authors = values(replay.get(key, ''), r'\\bibfield\{author\}')
            expected_people = [normalized(a) for a in values(expected_authors[0], r'\\bibinfo\{person\}')] if len(expected_authors) == 1 else []
        for field, valid in (
            ('author', bool(entry.get('author')) and bool(expected_people) and [normalized(a) for a in people] == expected_people),
            ('title', bool(entry.get('title')) and [normalized(t) for t in titles] == [normalized(entry['title'])]),
            ('year', bool(years) and all(normalized(y) == entry.get('year') for y in years)),
            ('doi', bool(entry.get('doi')) and entry['doi'].lower() in [normalized(d).lower() for d in dois]),
        ):
            if not valid: identity_errors.append({'key': key, 'field': field})
    number_rows = re.findall(r'\\bibcite\{([^}]+)\}\{\{(\d+)\}', uncomment(aux))
    number_map = dict(number_rows)
    number_errors = sorted(k for i, k in enumerate(rendered, 1) if number_map.get(k) != str(i))
    aux_cited = {k.strip() for row in re.findall(r'\\citation\{([^}]+)\}', uncomment(aux)) for k in row.split(',')}
    if '*' in aux_cited: aux_cited = (aux_cited - {'*'}) | set(database)
    duplicates = lambda xs: sorted(k for k, count in collections.Counter(xs).items() if count > 1)
    result = {
        'schema': 'tidemark-current-reference-consistency-2',
        'bibliography_entries': len(entries), 'rendered_bibliography_entries': len(rendered),
        'minimum_requested': minimum, 'meets_reference_floor': len(rendered) >= minimum,
        'unique_dois': len(set(doi)), 'missing_dois': [e['key'] for e in entries if not e.get('doi')],
        'duplicate_database_keys': duplicates(e['key'] for e in entries),
        'duplicate_database_dois': duplicates(doi),
        'undefined_citations': sorted(set(used) - set(database)),
        'undefined_nocite_keys': sorted(set(nocited) - {'*'} - set(database)),
        'current_citation_keys': sorted(used), 'unique_cited_keys': len(used),
        'rendered_keys_in_order': rendered,
        'explicit_bibliography_only_keys': sorted(expected - set(used)),
        'unpresented_database_keys': sorted(set(database) - set(rendered)),
        'bbl_missing_keys': sorted(expected - set(rendered)),
        'bbl_unexpected_keys': sorted(set(rendered) - expected),
        'bbl_unknown_keys': sorted(set(rendered) - set(database)),
        'bbl_duplicate_keys': duplicates(rendered), 'bbl_identity_errors': identity_errors,
        'bbl_replay_mismatch': expected_bbl is not None and bbl != expected_bbl,
        'aux_number_errors': number_errors,
        'aux_bibcite_key_difference': sorted(set(number_map) ^ set(rendered)),
        'aux_duplicate_bibcite_keys': duplicates(k for k, _ in number_rows),
        'aux_citation_key_difference': sorted(aux_cited ^ expected),
        'online_checks_executed_by_this_script': False, 'full_text_research_correctness_certified': False,
    }
    failures = ('missing_dois', 'duplicate_database_keys', 'duplicate_database_dois',
                'undefined_citations', 'undefined_nocite_keys', 'bbl_missing_keys',
                'bbl_unexpected_keys', 'bbl_unknown_keys', 'bbl_duplicate_keys',
                'bbl_identity_errors', 'bbl_replay_mismatch', 'aux_number_errors', 'aux_bibcite_key_difference',
                'aux_duplicate_bibcite_keys', 'aux_citation_key_difference')
    result['all_local_checks_passed'] = result['meets_reference_floor'] and not any(result[k] for k in failures)
    return result, number_map


def main():
    artifact = Path(__file__).resolve().parents[1]
    root, paper, output = artifact.parent, artifact.parent / 'paper', artifact / 'reference'
    if not paper.is_dir():
        raise SystemExit('Full-project input required: manuscript citation auditing needs the sibling paper tree.')
    output.mkdir(exist_ok=True)
    bib = paper / 'references.bib'
    entries = parse_bib(bib.read_text(encoding='utf-8'))
    database = {e['key']: e for e in entries}
    rows, multi, nocited = [], [], set()
    sources = active_sources(paper)
    cite_pattern = r'\\cite(?:t|p|alt|alp|author|yearpar|year)?\*?(?:\s*\[[^\]]*\]){0,2}\s*\{([^}]+)\}'
    for path, text in sorted(sources.items()):
        for group in re.findall(r'\\nocite\s*\{([^}]+)\}', text): nocited.update(k.strip() for k in group.split(','))
        for match in re.finditer(cite_pattern, text):
            keys = [k.strip() for k in match[1].split(',')]
            if len(keys) > 1: multi.append({'source': path.relative_to(root).as_posix(), 'line': text.count('\n', 0, match.start()) + 1, 'keys': keys})
            prefix = text[:match.start()]
            start = max(prefix.rfind('.  '), prefix.rfind('. '), prefix.rfind('\n\n'))
            claim = re.sub(r'\s+', ' ', text[start + 2:match.end()]).strip()
            for key in keys:
                entry = database.get(key, {})
                rows.append({'occurrence': len(rows) + 1, 'source': path.relative_to(root).as_posix(), 'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'line': text.count('\n', 0, match.start()) + 1, 'key': key, 'nearby_claim': claim, 'paper_title': entry.get('title', ''), 'doi': entry.get('doi', ''), 'review_scope': 'bounded nearby literature-positioning claim; see reference-review.md'})
    summary, number_map = check_bibliography(entries, {r['key'] for r in rows}, (paper / 'main.bbl').read_text(encoding='utf-8'), (paper / 'main.aux').read_text(encoding='utf-8'), nocited, expected_bbl=replay_bbl(paper))
    summary.update(bib_sha256=hashlib.sha256(bib.read_bytes()).hexdigest(), bbl_sha256=hashlib.sha256((paper / 'main.bbl').read_bytes()).hexdigest(), aux_sha256=hashlib.sha256((paper / 'main.aux').read_bytes()).hexdigest(), citation_occurrences=len(rows), multi_key_citations=multi, active_tex_inputs=[p.relative_to(root).as_posix() for p in sorted(sources)])
    summary['all_local_checks_passed'] = summary['all_local_checks_passed'] and not multi
    with (output / 'citation-support.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=['occurrence', 'source', 'source_sha256', 'line', 'key', 'nearby_claim', 'paper_title', 'doi', 'review_scope'])
        writer.writeheader(); writer.writerows(rows)
    fields = ['key', 'title', 'author', 'year', 'journal', 'booktitle', 'volume', 'number', 'pages', 'articleno', 'numpages', 'doi', 'primary_locator', 'current_bib_sha256', 'presentation_role']
    with (output / 'bibliography-current.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader()
        for entry in entries:
            role = 'cited' if entry['key'] in summary['current_citation_keys'] else 'explicit-bibliography-only' if entry['key'] in summary['explicit_bibliography_only_keys'] else 'unpresented-database-reserve'
            writer.writerow({**{k: entry.get(k, '') for k in fields}, 'primary_locator': 'https://doi.org/' + entry.get('doi', ''), 'current_bib_sha256': summary['bib_sha256'], 'presentation_role': role})
    (output / 'rendered-key-number-map.json').write_text(json.dumps(number_map, indent=2) + '\n', encoding='utf-8')
    (output / 'reference-consistency.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, indent=2))
    return 0 if summary['all_local_checks_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
