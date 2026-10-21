import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.collector import (
    extract_links,
    matched,
    normalized,
    read_yaml,
)


def test_keyword_matching():
    hits = matched(
        "2026 도슨트 양성과정 교육생 모집",
        ["도슨트", "큐레이터", "교육생"],
    )
    assert "도슨트" in hits
    assert "교육생" in hits
    assert "큐레이터" not in hits


def test_link_extraction():
    html = """
    <html>
      <body>
        <a href="/notice/123">
          도슨트 양성과정 모집
        </a>
      </body>
    </html>
    """
    _, links = extract_links(
        html,
        "https://example.org/",
    )
    assert links[0]["url"] == (
        "https://example.org/notice/123"
    )
    assert "도슨트" in links[0]["title"]


def test_url_normalization():
    assert normalized(
        "https://example.org/notice/#section"
    ) == "https://example.org/notice"


def test_configuration():
    settings = read_yaml("config/settings.yaml")
    institutions = read_yaml(
        "config/institutions.yaml"
    )
    keywords = read_yaml("config/keywords.yaml")

    assert settings["collection"]["enabled"] is True
    assert len(institutions["institutions"]) >= 20
    assert "docent_training" in keywords["keyword_groups"]
