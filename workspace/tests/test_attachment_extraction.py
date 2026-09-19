import importlib.util
import pathlib
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "bsc-data-sync.py"
spec = importlib.util.spec_from_file_location("bsc_data_sync", SCRIPT)
assert spec and spec.loader
bsc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bsc)


class AttachmentExtractionTests(unittest.TestCase):
    def test_extract_attachment_reports_missing_pymupdf_dependency_for_pdf(self):
        tmp = ROOT / "tmp" / "test-sample.pdf"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(b"%PDF-1.4\n%%EOF\n")
        try:
            text, links, method = bsc._extract_attachment(tmp, "application/pdf")
            self.assertIsNone(text)
            self.assertIsNone(links)
            self.assertTrue(method.startswith("failed:"), method)
            self.assertTrue("pymupdf" in method or "fitz" in method, method)
        finally:
            tmp.unlink(missing_ok=True)

    def test_extract_attachment_reports_missing_tesseract_for_image(self):
        tmp = ROOT / "tmp" / "test-sample.png"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(b"not a real png")
        try:
            with mock.patch.object(bsc.shutil, "which", lambda name: None if name == "tesseract" else "/bin/true"):
                text, links, method = bsc._extract_attachment(tmp, "image/png")
            self.assertIsNone(text)
            self.assertIsNone(links)
            self.assertEqual(method, "failed:missing_tesseract")
        finally:
            tmp.unlink(missing_ok=True)

    def test_extract_attachment_reports_unsupported_mime(self):
        tmp = ROOT / "tmp" / "test-sample.bin"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(b"abc")
        try:
            text, links, method = bsc._extract_attachment(tmp, "application/octet-stream")
            self.assertIsNone(text)
            self.assertIsNone(links)
            self.assertEqual(method, "unsupported")
        finally:
            tmp.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
