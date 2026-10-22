"""Unit tests for the identifier validators."""

from __future__ import annotations

import unittest

from doicheck.identifiers import (
    validate_arxiv_id,
    validate_doi,
    validate_isbn,
    validate_orcid,
)


class DoiTests(unittest.TestCase):
    def test_valid_simple_doi(self):
        self.assertTrue(validate_doi("10.1000/xyz123").ok)

    def test_valid_dotted_registrant(self):
        # Some DOI prefixes include a dotted sub-registrant code.
        self.assertTrue(validate_doi("10.1038.sub/suffix").ok)
        self.assertTrue(validate_doi("10.1000.123/suffix").ok)

    def test_valid_doi_with_special_chars(self):
        # Printable non-whitespace is fine per Handbook 2.5.1.
        self.assertTrue(validate_doi("10.1093/comjnl/27.2.97").ok)

    def test_missing_slash(self):
        r = validate_doi("10.1000nothinghere")
        self.assertFalse(r.ok)
        self.assertEqual(r.reason, "no-slash")

    def test_empty_suffix(self):
        r = validate_doi("10.1000/")
        self.assertFalse(r.ok)
        self.assertEqual(r.reason, "empty-suffix")

    def test_bad_prefix_not_ten_dot(self):
        r = validate_doi("11.1000/suffix")
        self.assertFalse(r.ok)
        self.assertEqual(r.reason, "bad-prefix")

    def test_bad_prefix_letters(self):
        r = validate_doi("10.ab/suffix")
        self.assertFalse(r.ok)
        self.assertEqual(r.reason, "bad-prefix")

    def test_forbidden_whitespace(self):
        r = validate_doi("10.1000/with space")
        self.assertFalse(r.ok)
        self.assertEqual(r.reason, "forbidden-char")

    def test_empty_input(self):
        self.assertFalse(validate_doi("").ok)
        self.assertFalse(validate_doi(None).ok)


class ArxivTests(unittest.TestCase):
    def test_new_style_valid(self):
        self.assertTrue(validate_arxiv_id("1706.03762").ok)
        self.assertTrue(validate_arxiv_id("1706.03762v3").ok)

    def test_new_style_5digit_valid(self):
        # 5-digit NNNNN is valid from 2015-01 onward.
        self.assertTrue(validate_arxiv_id("1501.12345").ok)

    def test_arxiv_prefix_tolerated(self):
        self.assertTrue(validate_arxiv_id("arXiv:1706.03762").ok)
        self.assertTrue(validate_arxiv_id("ARXIV:1706.03762v2").ok)

    def test_old_style_valid(self):
        self.assertTrue(validate_arxiv_id("math.AG/0601001").ok)
        self.assertTrue(validate_arxiv_id("cond-mat/9709204v1").ok)

    def test_future_year(self):
        r = validate_arxiv_id("9912.03762", current_year=2026)
        self.assertFalse(r.ok)
        self.assertEqual(r.reason, "future-year")

    def test_pre_2007_new_style_rejected(self):
        # New-style IDs begin 2007-04; a claimed 2006-12 is a format error.
        r = validate_arxiv_id("0612.00001", current_year=2026)
        self.assertFalse(r.ok)
        self.assertEqual(r.reason, "pre-2007-new-style")

    def test_bad_month(self):
        r = validate_arxiv_id("1713.00001")
        self.assertFalse(r.ok)
        self.assertEqual(r.reason, "bad-month")

    def test_total_garbage(self):
        r = validate_arxiv_id("not-an-arxiv-id")
        self.assertFalse(r.ok)
        self.assertEqual(r.reason, "bad-format")

    def test_version_v0_rejected_new_style(self):
        # arXiv numbers revisions from v1 upward; v0 is malformed.
        r = validate_arxiv_id("1706.03762v0")
        self.assertFalse(r.ok)
        self.assertEqual(r.reason, "bad-version")

    def test_version_v0_rejected_old_style(self):
        r = validate_arxiv_id("cond-mat/9709204v0")
        self.assertFalse(r.ok)
        self.assertEqual(r.reason, "bad-version")

    def test_leading_zero_version_rejected(self):
        # "v01" has a leading zero; arXiv versions are not zero-padded.
        r = validate_arxiv_id("1706.03762v01")
        self.assertFalse(r.ok)
        self.assertEqual(r.reason, "bad-version")

    def test_version_v10_still_valid(self):
        # Guards against over-eager leading-zero rejection:
        # "v10" is well-formed (no leading zero on a two-digit number).
        self.assertTrue(validate_arxiv_id("1706.03762v10").ok)


class OrcidTests(unittest.TestCase):
    def test_valid_orcid(self):
        # 0000-0002-1825-0097 is a canonical example in the ORCID spec.
        self.assertTrue(validate_orcid("0000-0002-1825-0097").ok)

    def test_valid_orcid_with_url(self):
        self.assertTrue(validate_orcid(
            "https://orcid.org/0000-0002-1825-0097").ok)

    def test_valid_orcid_with_x_check(self):
        # Verified against the public ISO 7064 Mod 11,2 algorithm.
        # 0000-0002-9079-593X - total 2114, mod 11 = 2, check = 10 -> X.
        self.assertTrue(validate_orcid("0000-0002-9079-593X").ok)

    def test_bad_checksum(self):
        r = validate_orcid("0000-0002-1825-0098")
        self.assertFalse(r.ok)
        self.assertEqual(r.reason, "bad-checksum")

    def test_bad_shape(self):
        self.assertEqual(
            validate_orcid("0000-0002-1825").reason, "bad-shape")
        self.assertEqual(
            validate_orcid("0000:0002:1825:0097").reason, "bad-shape")
        # Final digit may be 'X' but no other letter.
        self.assertEqual(
            validate_orcid("0000-0002-1825-009A").reason, "bad-shape")


class IsbnTests(unittest.TestCase):
    def test_valid_isbn10(self):
        # 0-201-89683-4 is the canonical TAOCP vol 1 example.
        self.assertTrue(validate_isbn("0-201-89683-4").ok)
        self.assertTrue(validate_isbn("0201896834").ok)

    def test_valid_isbn10_with_x(self):
        # 0-306-40615-2 - replace with an X-ending canonical example.
        # 0-8044-2957-X is a widely-published ISBN-10 that ends in X.
        self.assertTrue(validate_isbn("0-8044-2957-X").ok)

    def test_bad_isbn10_checksum(self):
        r = validate_isbn("0-201-89683-5")
        self.assertFalse(r.ok)
        self.assertEqual(r.reason, "bad-isbn10-checksum")

    def test_valid_isbn13(self):
        # 978-0-13-468599-1 is a published ISBN-13 for TAOCP vol 4A.
        self.assertTrue(validate_isbn("978-0-13-468599-1").ok)
        self.assertTrue(validate_isbn("9780134685991").ok)

    def test_bad_isbn13_checksum(self):
        r = validate_isbn("978-0-13-468599-0")
        self.assertFalse(r.ok)
        self.assertEqual(r.reason, "bad-isbn13-checksum")

    def test_wrong_length(self):
        r = validate_isbn("123")
        self.assertFalse(r.ok)
        self.assertEqual(r.reason, "bad-length")

    def test_isbn_prefix_tolerated(self):
        self.assertTrue(validate_isbn("ISBN 0-201-89683-4").ok)
        self.assertTrue(validate_isbn("ISBN: 978-0-13-468599-1").ok)


if __name__ == "__main__":
    unittest.main()
