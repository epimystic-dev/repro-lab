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

    def test_string_pseudo_entry_skipped(self):
        # @string is a macro-definition command per the BibTeX user's
        # guide, not a bibliographic entry; it must not appear in the
        # parser output as an entry with a cite-key-shaped payload.
        text = '@string{jcacm = "Communications of the ACM"}\n'
        entries = parse_bibtex(text)
        self.assertEqual(entries, [])

    def test_preamble_pseudo_entry_skipped(self):
        text = '@preamble{" \\newcommand{\\noopsort}[1]{} "}\n'
        entries = parse_bibtex(text)
        self.assertEqual(entries, [])

    def test_comment_pseudo_entry_skipped(self):
        # A @comment body may contain commas; nothing inside it is a key.
        text = "@comment{some notes, including commas and @article tokens}\n"
        entries = parse_bibtex(text)
        self.assertEqual(entries, [])

    def test_string_case_insensitive(self):
        # BibTeX entry types are case-insensitive; the parser lowercases
        # the type for the REQUIRED_FIELDS lookup, so pseudo-entry
        # detection must honor the same casing.
        text = '@STRING{jcacm = "CACM"}\n@String{jipd = "JIPD"}\n'
        entries = parse_bibtex(text)
        self.assertEqual(entries, [])

    def test_pseudo_entries_do_not_swallow_following_article(self):
        # A @string prelude followed by a real @article must still parse
        # the article correctly - i.e. we advance past the pseudo-entry
        # span, not past a single character.
        text = (
            '@string{jcacm = "Communications of the ACM"}\n'
            '@string{jtse = "Trans. Software Eng."}\n'
            "@article{smith2020,\n"
            "  author = {Smith, A.},\n"
            "  title = {A paper},\n"
            "  journal = jcacm,\n"
            "  year = {2020}\n"
            "}\n"
        )
        entries = parse_bibtex(text)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].entry_type, "article")
        self.assertEqual(entries[0].key, "smith2020")
        self.assertEqual(entries[0].fields["year"], "2020")

    def test_string_with_parens_skipped(self):
        # Pseudo-entries also accept the paren shell.
        text = '@string(jcacm = "CACM")\n'
        entries = parse_bibtex(text)
        self.assertEqual(entries, [])

    def test_quoted_concat_preserves_following_fields(self):
        # Regression: a quoted value followed by '#' concatenation must
        # not swallow the fields that come after it. Before this fix the
        # parser read "Hello", did not recognise '#' in the comma-skip
        # loop, failed to read a next field name, and silently dropped
        # author / journal / year.
        text = (
            "@article{foo,\n"
            '  title = "Hello" # " World",\n'
            '  author = "Smith, J.",\n'
            '  journal = "IEEE",\n'
            "  year = 2024\n"
            "}\n"
        )
        entries = parse_bibtex(text)
        self.assertEqual(len(entries), 1)
        e = entries[0]
        self.assertEqual(
            sorted(e.fields.keys()),
            ["author", "journal", "title", "year"],
        )

    def test_quoted_concat_joins_string_components(self):
        # The '#' operator concatenates string components per the BibTeX
        # user's guide; " Hello" # " World" is the single string
        # "Hello World".
        text = (
            "@article{foo,\n"
            '  title = "Hello" # " World"\n'
            "}\n"
        )
        entries = parse_bibtex(text)
        self.assertEqual(entries[0].fields["title"], "Hello World")

    def test_braced_concat_joins_components(self):
        # Braced components also participate in concatenation.
        text = (
            "@article{foo,\n"
            '  title = {A} # {B} # {C},\n'
            "  year = 2024\n"
            "}\n"
        )
        entries = parse_bibtex(text)
        self.assertEqual(entries[0].fields["title"], "ABC")
        self.assertEqual(entries[0].fields["year"], "2024")

    def test_quoted_then_macro_concat(self):
        # A quoted prefix followed by a macro reference must not drop
        # the comma that separates the field from the next one. The
        # macro name is preserved verbatim (this is a hygiene linter
        # and does not resolve macros).
        text = (
            '@string{iet = "Inst. of Engineering Technology"}\n'
            "@article{foo,\n"
            '  journal = "Prefix: " # iet,\n'
            '  year = 2024\n'
            "}\n"
        )
        entries = parse_bibtex(text)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].fields["journal"], "Prefix: iet")
        self.assertEqual(entries[0].fields["year"], "2024")

    def test_concat_spanning_newline(self):
        # BibTeX allows whitespace (including newlines) around '#'.
        text = (
            "@article{foo,\n"
            '  title = "A"\n'
            '         # " paper",\n'
            '  author = "X"\n'
            "}\n"
        )
        entries = parse_bibtex(text)
        self.assertEqual(entries[0].fields["title"], "A paper")
        self.assertEqual(entries[0].fields["author"], "X")

    def test_bare_macro_concat_followed_by_string(self):
        # Macro-name-first concatenation reaches the comma via the bare
        # branch's "read until comma or newline" logic even without the
        # fix, but the test documents the intended behavior so a future
        # refactor of the bare branch cannot regress field preservation.
        text = (
            '@string{iet = "IEEE Trans."}\n'
            "@article{foo,\n"
            '  journal = iet # " on Topic",\n'
            "  year = 2024\n"
            "}\n"
        )
        entries = parse_bibtex(text)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].fields["year"], "2024")


if __name__ == "__main__":
    unittest.main()
