import unittest
from pathlib import Path

from cime import CimeDownloaderError, build_output_path, ensure_mp4_filename, validate_page_url


class CimeValidationTests(unittest.TestCase):
    def test_validate_page_url_accepts_ci_me_vod(self) -> None:
        result = validate_page_url("https://ci.me/@creator/vods/12345#fragment")
        self.assertEqual(result, "https://ci.me/@creator/vods/12345")

    def test_validate_page_url_rejects_other_host(self) -> None:
        with self.assertRaises(CimeDownloaderError):
            validate_page_url("https://example.com/@creator/vods/12345")

    def test_validate_page_url_requires_vod_path(self) -> None:
        with self.assertRaises(CimeDownloaderError):
            validate_page_url("https://ci.me/@creator")

    def test_ensure_mp4_filename_rejects_path_parts(self) -> None:
        with self.assertRaises(CimeDownloaderError):
            ensure_mp4_filename("../escape.mp4")

    def test_ensure_mp4_filename_normalizes_extension(self) -> None:
        self.assertEqual(ensure_mp4_filename(" preview.mov "), "preview.mp4")

    def test_ensure_mp4_filename_rejects_windows_reserved_name(self) -> None:
        with self.assertRaises(CimeDownloaderError):
            ensure_mp4_filename("CON")

    def test_build_output_path_stays_inside_selected_directory(self) -> None:
        temp_dir = Path("staging") / "test-output"
        temp_dir.mkdir(parents=True, exist_ok=True)
        output_path = build_output_path(temp_dir, "episode")
        self.assertEqual(output_path.parent.resolve(), temp_dir.resolve())
        self.assertEqual(output_path.name, "episode.mp4")


if __name__ == "__main__":
    unittest.main()
