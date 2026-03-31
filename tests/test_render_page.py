import unittest

from main import _render_page


class RenderPageTests(unittest.TestCase):
    def test_render_page_contains_theme_toggle_and_formats(self) -> None:
        html = _render_page("abc-123", ["glb", "step", "stl"])
        self.assertIn('id="theme-toggle"', html)
        self.assertIn("cadagent-export-theme", html)
        self.assertIn('class="format-link"', html)
        self.assertIn('href="/exports/abc-123/glb"', html)
        self.assertIn('href="/exports/abc-123/step"', html)
        self.assertIn('href="/exports/abc-123/stl"', html)
        self.assertIn("model-viewer", html)


if __name__ == "__main__":
    unittest.main()
