"""Unit tests for language detection and line count distribution."""

from pathlib import Path
import pytest

from codeagent.intelligence.language_detector import LanguageDetector, LanguageDistribution


def test_language_detector_multi_language(tmp_path: Path) -> None:
    """Verify language breakdown percentages and primary language detection."""
    proj = tmp_path / "mixed_proj"
    proj.mkdir()

    # Python: 60 lines
    (proj / "main.py").write_text("\n".join(["print('py')"] * 60), encoding="utf-8")
    # JavaScript: 30 lines
    (proj / "app.js").write_text("\n".join(["console.log('js');"] * 30), encoding="utf-8")
    # HTML: 10 lines
    (proj / "index.html").write_text("\n".join(["<div>test</div>"] * 10), encoding="utf-8")

    detector = LanguageDetector()
    dist = detector.detect_distribution(proj)

    assert dist.primary_language == "Python"
    assert dist.total_source_files == 3
    assert dist.total_source_lines == 100
    assert dist.percentages["Python"] == 60.0
    assert dist.percentages["JavaScript"] == 30.0
    assert dist.percentages["HTML"] == 10.0

