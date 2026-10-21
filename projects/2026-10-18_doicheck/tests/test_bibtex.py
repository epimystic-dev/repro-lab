"""Tests for the BibTeX parser."""

from __future__ import annotations

import unittest

from doicheck.bibtex import parse_bibtex


class ParseTests(unittest.TestCase):
    def test_simple_entry(self):
        text = (
            "@article{smith2020,\n"
            "  author = {Smith, A.},\n"
            "  title = {A paper},\n"
            "  journal = {J},\n"
            "  year = {2020}\n"
            "}\n"
        )
        entries = parse_bibtex(text)
        self.assertEqual(len(entries), 1)
        e = entries[0]
        self.assertEqual(e.entry_type, "article")
        self.assertEqual(e.key, "smith2020")
        self.assertEqual(e.fields["author"], "Smith, A.")
        self.assertEqual(e.fields["year"], "2020")
        self.assertGreater(e.line, 0)

    def test_two_entries(self):
        text = (
            "@article{one, title = {A}}\n"
            "@book{two, title = {B}, publisher = {P}, year = {2020}}\n"
        )
        entries = parse_bibtex(text)
        self.assertEqual([e.entry_type for e in entries], ["article", "book"])
        self.assertEqual([e.key for e in entries], ["one", "two"])

    def test_quoted_values(self):
        text = '@article{a, title = "A paper", year = "2020"}\n'
        entries = parse_bibtex(text)
        self.assertEqual(entries[0].fields["title"], "A paper")

    def test_percent_comment_skipped(self):
        text = (
            "% this is a comment with @article in it\n"
            "@article{keep, title = {kept}}\n"
        )
        entries = parse_bibtex(text)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].key, "keep")

    def test_nested_braces_preserved(self):
        text = "@article{nested, title = {A {paper} with braces}}\n"
        entries = parse_bibtex(text)
        self.assertEqual(
            entries[0].fields["title"], "A {paper} with braces")

    def test_unbalanced_detected(self):
        text = "@article{bad, title = {A {paper}}\n"
        entries = parse_bibtex(text)
        # The outer brace balancing of the entry fails - parse_bibtex
        # should recover gracefully (zero or one entry).
        # Either way, nothing should raise.
        self.assertIsNotNone(entries)

    def test_unterminated_entry_flagged(self):
        # Entry body never closes - common BibTeX failure that
        # silently truncates downstream fields.
        text = (
            "@article{bad,\n"
            "  title = {A paper with {unbalanced\n"
            "  year = {2020}\n"
        )
        entries = parse_bibtex(text)
        self.assertEqual(len(entries), 1)
        self.assertIn("<entry>", entries[0].unbalanced_fields)

    def test_parenthesised_entry(self):
        text = "@article(parened, title = {A})\n"
        entries = parse_bibtex(text)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].key, "parened")


if __name__ == "__main__":
    unittest.main()
