"""Cited/rendered/database roles and strict local BBL identity consistency."""
import copy
from pathlib import Path
import runpy
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
with mock.patch.object(sys, 'path', [str(ROOT / 'scripts'), *sys.path]):
    audit = runpy.run_path(str(ROOT / 'scripts/audit_references.py'))
check = audit['check_bibliography']


def entry(key, author, title):
    return {'key': key, 'type': 'article', 'author': author,
            'title': '{' + title + '}', 'year': '2020', 'doi': '10.1234/' + key}


def item(record):
    people = ', '.join(r'\bibinfo{person}{' + p + '}' for p in record['author'].split(' and '))
    return (r'\bibitem[Authors(2020)]%' + '\n {' + record['key'] + '}\n' +
            r'\bibfield{author}{' + people + '}.\n' +
            r'\showarticletitle{' + record['title'] + '}\n' +
            r'\bibinfo{year}{2020}' + '\n' +
            r'\nolinkurl{' + record['doi'] + '}\n')


class ReferenceConsumerTests(unittest.TestCase):
    def setUp(self):
        self.entries = [entry('a', 'Alice Able and Bob Baker', 'Current Title'),
                        entry('spare', 'Carol Clark', 'Reserve Title')]
        self.bbl = item(self.entries[0])
        self.aux = r'\citation{a}' + '\n' + r'\bibcite{a}{{1}{2020}{{Able}}{{}}}'

    def checked(self, **changes):
        args = dict(entries=self.entries, used={'a'}, bbl=self.bbl, aux=self.aux,
                    minimum=1, expected_bbl=self.bbl)
        args.update(changes)
        return check(**args)[0]

    def test_unused_database_record_is_not_a_printed_bibliography_failure(self):
        result = self.checked()
        self.assertTrue(result['all_local_checks_passed'])
        self.assertEqual(result['unpresented_database_keys'], ['spare'])
        self.assertEqual(result['rendered_bibliography_entries'], 1)
        self.assertFalse(result['full_text_research_correctness_certified'])

    def test_current_citation_must_exist_in_database_and_bbl(self):
        result = self.checked(used={'a', 'missing'})
        self.assertFalse(result['all_local_checks_passed'])
        self.assertEqual(result['undefined_citations'], ['missing'])
        self.assertEqual(result['bbl_missing_keys'], ['missing'])
        result = self.checked(used={'a', 'spare'})
        self.assertFalse(result['all_local_checks_passed'])
        self.assertEqual(result['bbl_missing_keys'], ['spare'])

    def test_bbl_author_order_title_year_doi_and_key_mismatches_reject(self):
        changes = [('Alice Able', 'Alicia Able', 'author'),
                   ('Alice Able}, \\bibinfo{person}{Bob Baker', 'Bob Baker}, \\bibinfo{person}{Alice Able', 'author'),
                   ('Current Title', 'Different Title', 'title'),
                   ('{year}{2020}', '{year}{2021}', 'year'),
                   ('10.1234/a', '10.1234/other', 'doi')]
        for old, new, field in changes:
            with self.subTest(field=field, new=new):
                result = self.checked(bbl=self.bbl.replace(old, new))
                self.assertFalse(result['all_local_checks_passed'])
                self.assertIn({'key': 'a', 'field': field}, result['bbl_identity_errors'])
                self.assertTrue(result['bbl_replay_mismatch'])
        self.assertFalse(self.checked(bbl=self.bbl.replace('\n {a}', '\n {spare}'))['all_local_checks_passed'])

    def test_unknown_extra_duplicate_bbl_and_wrong_aux_mapping_reject(self):
        for bbl in (self.bbl + self.bbl, self.bbl + item(self.entries[1]),
                    self.bbl + item(entry('unknown', 'Dan Doe', 'Unknown Title'))):
            with self.subTest(bbl=bbl): self.assertFalse(self.checked(bbl=bbl)['all_local_checks_passed'])
        for aux in (self.aux.replace('{{1}', '{{2}'), self.aux + '\n' + self.aux,
                    self.aux.replace('citation{a}', 'citation{spare}')):
            with self.subTest(aux=aux): self.assertFalse(self.checked(aux=aux)['all_local_checks_passed'])

    def test_explicit_nocite_is_separate_from_citation_and_reserve_roles(self):
        bbl = self.bbl + item(self.entries[1])
        aux = self.aux + '\n' + r'\citation{spare}' + '\n' + r'\bibcite{spare}{{2}{2020}{{Clark}}{{}}}'
        result = self.checked(bbl=bbl, expected_bbl=bbl, aux=aux, nocited={'spare'})
        self.assertTrue(result['all_local_checks_passed'])
        self.assertEqual(result['current_citation_keys'], ['a'])
        self.assertEqual(result['explicit_bibliography_only_keys'], ['spare'])
        self.assertEqual(result['unpresented_database_keys'], [])

    def test_source_graph_excludes_unused_tex_and_comments(self):
        with tempfile.TemporaryDirectory() as td:
            paper = Path(td)
            (paper / 'main.tex').write_text(r'\input{active}' + '\n% \\input{unused}\n')
            (paper / 'active.tex').write_text(r'\cite{a}')
            (paper / 'unused.tex').write_text(r'\cite{spare}')
            sources = audit['active_sources'](paper)
            self.assertEqual({p.name for p in sources}, {'main.tex', 'active.tex'})

    def test_renderer_name_formatting_is_replayed_not_blanket_normalized(self):
        entries = [entry('a', 'Ken-ichi Matsumoto', 'Current Title')]
        expected = item(entries[0]).replace('Ken-ichi', 'Ken ichi')
        result = self.checked(entries=entries, bbl=expected, expected_bbl=expected)
        self.assertTrue(result['all_local_checks_passed'])
        self.assertFalse(self.checked(entries=entries, bbl=expected.replace('Matsumoto', 'Matsumota'), expected_bbl=expected)['all_local_checks_passed'])

    def test_reference_floor_duplicate_keys_and_dois_stay_enforced(self):
        self.assertFalse(self.checked(minimum=2)['all_local_checks_passed'])
        for field, value in (('key', 'a'), ('doi', '10.1234/a'), ('doi', '')):
            entries = copy.deepcopy(self.entries)
            entries[1][field] = value
            self.assertFalse(self.checked(entries=entries)['all_local_checks_passed'])

    def test_unclosed_bibliography_argument_fails_closed(self):
        with self.assertRaises(ValueError):
            self.checked(bbl=self.bbl.replace(r'\showarticletitle{{Current Title}}', r'\showarticletitle{{Current Title'))


if __name__ == '__main__':
    unittest.main()
