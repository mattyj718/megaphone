"""Tests for megaphone.sources module."""

import os
import tempfile
import pytest
from megaphone import db
from megaphone.sources import ingest_rss, strip_html, extract_urls


SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <link>https://example.com</link>
    <item>
      <title>First Post</title>
      <link>https://example.com/post-1</link>
      <description>&lt;p&gt;This is the &lt;b&gt;first&lt;/b&gt; post.&lt;/p&gt;</description>
    </item>
    <item>
      <title>Second Post</title>
      <link>https://example.com/post-2</link>
      <description>Plain text summary of second post.</description>
    </item>
    <item>
      <title>No Link Post</title>
      <description>This entry has no link and should be skipped.</description>
    </item>
  </channel>
</rss>"""

SAMPLE_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Test Atom Feed</title>
  <entry>
    <title>Atom Entry</title>
    <link href="https://example.com/atom-1"/>
    <content type="html">&lt;p&gt;Atom content here&lt;/p&gt;</content>
  </entry>
</feed>"""


@pytest.fixture
def test_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = db.init_db(path)
    yield conn
    conn.close()
    os.unlink(path)


class TestStripHtml:
    def test_basic(self):
        assert strip_html("<p>Hello <b>world</b></p>") == "Hello world"

    def test_scripts_removed(self):
        html = "<p>Before</p><script>alert('xss')</script><p>After</p>"
        text = strip_html(html)
        assert "alert" not in text
        assert "Before" in text
        assert "After" in text

    def test_empty(self):
        assert strip_html("") == ""
        assert strip_html(None) == ""

    def test_plain_text(self):
        assert strip_html("just plain text") == "just plain text"


class TestExtractUrls:
    def test_basic(self):
        html = '<a href="https://example.com">link</a>'
        assert extract_urls(html) == ["https://example.com"]

    def test_filters_non_http(self):
        html = '<a href="mailto:test@test.com">mail</a> <a href="https://x.com">x</a>'
        assert extract_urls(html) == ["https://x.com"]


class TestIngestRss:
    def test_ingest_rss(self, test_db, tmp_path):
        # Write sample RSS to a file and use file:// URL
        feed_file = tmp_path / "feed.xml"
        feed_file.write_text(SAMPLE_RSS)

        source_id = db.upsert_source(
            test_db, "Test Feed", "rss", {"url": f"file://{feed_file}"}
        )
        source = db.get_sources(test_db)[0]

        new_ids = ingest_rss(source, test_db)
        # Should get 2 items (third has no link)
        assert len(new_ids) == 2

        items = db.get_content_items(test_db)
        assert len(items) == 2
        titles = {i["title"] for i in items}
        assert "First Post" in titles
        assert "Second Post" in titles

    def test_dedup(self, test_db, tmp_path):
        feed_file = tmp_path / "feed.xml"
        feed_file.write_text(SAMPLE_RSS)

        source_id = db.upsert_source(
            test_db, "Test Feed", "rss", {"url": f"file://{feed_file}"}
        )
        source = db.get_sources(test_db)[0]

        # Ingest twice
        first = ingest_rss(source, test_db)
        second = ingest_rss(source, test_db)

        assert len(first) == 2
        assert len(second) == 0  # All deduped

    def test_atom_feed(self, test_db, tmp_path):
        feed_file = tmp_path / "atom.xml"
        feed_file.write_text(SAMPLE_ATOM)

        db.upsert_source(
            test_db, "Atom Feed", "rss", {"url": f"file://{feed_file}"}
        )
        source = db.get_sources(test_db)[0]

        new_ids = ingest_rss(source, test_db)
        assert len(new_ids) == 1

        item = db.get_content_item(test_db, new_ids[0])
        assert item["title"] == "Atom Entry"
        assert "Atom content here" in item["body"]

    def test_missing_url_config(self, test_db):
        db.upsert_source(test_db, "Bad Feed", "rss", {})
        source = db.get_sources(test_db)[0]
        new_ids = ingest_rss(source, test_db)
        assert new_ids == []

    def test_html_stripped_from_body(self, test_db, tmp_path):
        feed_file = tmp_path / "feed.xml"
        feed_file.write_text(SAMPLE_RSS)

        db.upsert_source(
            test_db, "Test Feed", "rss", {"url": f"file://{feed_file}"}
        )
        source = db.get_sources(test_db)[0]
        ingest_rss(source, test_db)

        items = db.get_content_items(test_db)
        first = [i for i in items if i["title"] == "First Post"][0]
        assert "<p>" not in first["body"]
        assert "<b>" not in first["body"]
        assert "first" in first["body"]
