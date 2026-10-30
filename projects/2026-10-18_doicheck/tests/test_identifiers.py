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

    def test_forbidden_del_character(self):
        # DEL (0x7F) is an ASCII control character and not printable, so
        # Handbook 2.5.1 excludes it from the suffix.
        r = validate_doi("10.1000/foo\x7fbar")
        self.assertFalse(r.ok)
        self.assertEqual(r.reason, "forbidden-char")

    def test_forbidden_c1_control_low(self):
        # 0x80 is the first C1 control; also not printable.
        r = validate_doi("10.1000/foo\x80bar")
        self.assertFalse(r.ok)
        self.assertEqual(r.reason, "forbidden-char")

    def test_forbidden_c1_control_high(self):
        # 0x9F is the last C1 control; boundary of the forbidden range.
        r = validate_doi("10.1000/foo\x9fbar")
        self.assertFalse(r.ok)
        self.assertEqual(r.reason, "forbidden-char")

    def test_printable_non_ascii_allowed(self):
        # Printable non-ASCII (e.g. U+00E9) is NOT whitespace and NOT a
        # control character, so the handbook permits it in the suffix.
        self.assertTrue(validate_doi("10.1000/café").ok)

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

    def test_pre_2015_rejects_5digit_number(self):
        # Regression: before this guard, "1412.12345" (Dec 2014, 5-digit)
        # was accepted even though arXiv zero-padded to 4 digits until
        # 2014-12 inclusive per info.arxiv.org/help/arxiv_identifier.html.
        r = validate_arxiv_id("1412.12345")
        self.assertFalse(r.ok)
        self.assertEqual(r.reason, "bad-ndigits-for-era")

    def test_pre_2015_rejects_5digit_at_start_of_new_style(self):
        # April 2007 is the first new-style month and was 4-digit.
        r = validate_arxiv_id("0704.00001")
        self.assertFalse(r.ok)
        self.assertEqual(r.reason, "bad-ndigits-for-era")

    def test_post_2015_rejects_4digit_number(self):
        # Regression: before this guard, "1501.1234" (Jan 2015, 4-digit)
        # was accepted even though arXiv switched to 5-digit numbers
        # beginning 2015-01 per the identifier-scheme page.
        r = validate_arxiv_id("1501.1234")
        self.assertFalse(r.ok)
        self.assertEqual(r.reason, "bad-ndigits-for-era")

    def test_post_2015_rejects_4digit_version_suffixed(self):
        # The digit-count check runs before the version check so a
        # version suffix cannot mask a wrong-era digit count.
        r = validate_arxiv_id("1812.9999v2")
        self.assertFalse(r.ok)
        self.assertEqual(r.reason, "bad-ndigits-for-era")

    def test_pre_2015_4digit_still_valid(self):
        # Guard against over-eager rejection: 4-digit numbers in the
        # pre-2015 era remain valid.
        self.assertTrue(validate_arxiv_id("0704.0001").ok)
        self.assertTrue(validate_arxiv_id("1412.9999").ok)

    def test_post_2015_5digit_still_valid(self):
        # Guard: 5-digit numbers in the 2015-onward era remain valid.
        self.assertTrue(validate_arxiv_id("1501.00001").ok)
        self.assertTrue(validate_arxiv_id("2301.12345").ok)

    def test_pre_2007_still_takes_precedence_over_digit_count(self):
        # The pre-2007-new-style check must still fire first, even on
        # strings whose digit count would otherwise be wrong for either
        # era. "0612.00001" (Dec 2006, 5-digit) is pre-2007 and has the
        # wrong digit count for pre-2015, but the stabler pre-2007
        # reason is the one callers rely on.
        r = validate_arxiv_id("0612.00001", current_year=2026)
        self.assertFalse(r.ok)
        self.assertEqual(r.reason, "pre-2007-new-style")


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

    def test_isbn13_rejects_non_bookland_prefix(self):
        # Regression: before this guard, a 13-digit string with a
        # correct Mod-10 checksum but a non-978/979 prefix was accepted
        # as a valid ISBN. ISO 2108 reserves only 978 and 979 for the
        # ISBN agency; '9220000000003' is a well-formed EAN-13 but not
        # an ISBN. Hand-computed: digits 9,2,2,0,...,0,3 give weighted
        # sum 9 + 3*2 + 2 + 3*0 + 0 + ... + 3 = 20, which is 0 mod 10.
        r = validate_isbn("9220000000003")
        self.assertFalse(r.ok)
        self.assertEqual(r.reason, "bad-isbn13-prefix")

    def test_isbn13_rejects_zero_prefix_even_if_checksum_ok(self):
        # A 13-digit all-zero string has a trivial zero checksum but a
        # '000' prefix - plainly not an ISBN.
        r = validate_isbn("0000000000000")
        self.assertFalse(r.ok)
        self.assertEqual(r.reason, "bad-isbn13-prefix")

    def test_valid_isbn13_with_979_prefix(self):
        # Guard against over-eager prefix rejection. 979-11-85304-71-7
        # is a published ISBN-13 under the 979 Bookland range: digits
        # 9,7,9,1,1,8,5,3,0,4,7,1,7 sum to 110 weighted, which is 0
        # mod 10, and the 979 prefix is reserved by ISO 2108 for the
        # ISBN agency alongside 978.
        self.assertTrue(validate_isbn("979-11-85304-71-7").ok)
        self.assertTrue(validate_isbn("9791185304717").ok)

    def test_bad_isbn13_checksum_still_prefers_checksum_reason(self):
        # When the prefix is valid (978 or 979) but the checksum is
        # wrong, the original 'bad-isbn13-checksum' reason must still
        # fire - this guards the ordering of the two checks.
        r = validate_isbn("978-0-13-468599-0")
        self.assertFalse(r.ok)
        self.assertEqual(r.reason, "bad-isbn13-checksum")


if __name__ == "__main__":
    unittest.main()
