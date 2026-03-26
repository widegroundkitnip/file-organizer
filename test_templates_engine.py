#!/usr/bin/env python3
import unittest

from planner.templates import TemplateEngine, explain_template, validate_template
from scanner.manifest import ScannedFile


class TemplateEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = TemplateEngine()

    def test_required_variables_render(self):
        file_data = {
            "name": "report.pdf",
            "ext": ".pdf",
            "size_bytes": 12345,
            "modified_ts": "2026-02-03T04:05:06",
            "mime_type": "application/pdf",
            "hash": "abcdef123456",
        }
        out = self.engine.render(
            "{year}/{month}/{name}.{ext}-{size}-{date}-{mime_cat}-{hash}-{counter}-{original}",
            file_data,
            counter=7,
        )
        self.assertEqual(
            out,
            "2026/02/report.pdf-tiny-2026-02-03-application-abcdef12-007-report.pdf",
        )

    def test_single_fallback_literal(self):
        file_data = {"name": "notes", "ext": "", "size_bytes": 10}
        out = self.engine.render("{year|Unknown}/{name|untitled}.{ext|bin}", file_data)
        self.assertEqual(out, "Unknown/notes.bin")

    def test_sanitization_and_traversal_protection(self):
        file_data = {"name": 'bad<name>:?"*|', "ext": "txt"}
        out = self.engine.render("../../{name}.{ext}", file_data)
        self.assertNotIn("..", out)
        self.assertEqual(out, "bad_name______.txt")

    def test_replace_spaces_with_underscores_option(self):
        file_data = {"name": "my report", "ext": "txt"}
        out_default = self.engine.render("{name}.{ext}", file_data)
        out_under = TemplateEngine(replace_spaces_with_underscores=True).render("{name}.{ext}", file_data)
        self.assertEqual(out_default, "my report.txt")
        self.assertEqual(out_under, "my_report.txt")

    def test_truncation_preserves_extension(self):
        long_name = "a" * 260 + ".txt"
        file_data = {"name": long_name, "ext": "txt"}
        out = self.engine.render("{original}", file_data)
        self.assertTrue(out.endswith(".txt"))
        self.assertLessEqual(len(out.split("/")[-1]), 200)

    def test_validate_template_reports_warnings(self):
        issues_unknown = validate_template("{name}.{not_a_var}")
        issues_unsafe = validate_template("../../etc/passwd")
        self.assertTrue(any("unknown template variable" in msg.lower() for msg in issues_unknown))
        self.assertTrue(any("unsafe traversal" in msg.lower() for msg in issues_unsafe))

    def test_explain_template_returns_preview(self):
        preview = explain_template("{name}.{ext}", {"name": "doc.txt", "ext": ".txt"})
        self.assertIn("->", preview)
        self.assertIn("doc.txt", preview)

    def test_size_counter_hash_defaults(self):
        file_data = {"name": "file.txt", "ext": "txt", "size_bytes": 1234, "hash": "abcdef1234567890"}
        self.assertEqual(self.engine.render("{size}", file_data), "tiny")
        self.assertEqual(self.engine.render("{counter}", file_data), "001")
        self.assertEqual(self.engine.render("{counter}", file_data, counter=2), "002")
        self.assertEqual(self.engine.render("{hash}", file_data), "abcdef12")

    def test_scanned_file_input(self):
        scanned = ScannedFile(
            path="/tmp/img.jpg",
            relative_path="img.jpg",
            parent_tree="tmp",
            name="img.jpg",
            ext=".jpg",
            size_bytes=50,
            modified_ts="2026-01-01T10:11:12",
            mime_type="image/jpeg",
            hash=None,
            exif_date_taken=None,
        )
        out = self.engine.render("{year}/{month}/{name}.{ext}", scanned)
        self.assertEqual(out, "2026/01/img.jpg")


if __name__ == "__main__":
    unittest.main()
