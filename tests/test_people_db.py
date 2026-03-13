"""Tests for people table CRUD operations in megaphone.db."""

import os
import tempfile

import pytest

from megaphone import db


@pytest.fixture
def test_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = db.init_db(path)
    yield conn
    conn.close()
    os.unlink(path)


class TestPeopleTable:
    def test_people_table_exists(self, test_db):
        tables = test_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='people'"
        ).fetchall()
        assert len(tables) == 1

    def test_insert_and_get_person(self, test_db):
        pid = db.insert_person(test_db, "Alice Smith", company="Acme Corp")
        assert pid == 1

        person = db.get_person(test_db, pid)
        assert person is not None
        assert person["name"] == "Alice Smith"
        assert person["company"] == "Acme Corp"
        assert person["is_watchlisted"] == 0
        assert person["is_followed_linkedin"] == 0
        assert person["is_followed_bluesky"] == 0

    def test_insert_person_full_fields(self, test_db):
        pid = db.insert_person(
            test_db, "Bob Jones", company="BigCo",
            linkedin_url="https://linkedin.com/in/bobjones",
            bluesky_handle="bob.bsky.social",
            is_watchlisted=1, notes="Key influencer"
        )
        person = db.get_person(test_db, pid)
        assert person["linkedin_url"] == "https://linkedin.com/in/bobjones"
        assert person["bluesky_handle"] == "bob.bsky.social"
        assert person["is_watchlisted"] == 1
        assert person["notes"] == "Key influencer"

    def test_get_person_not_found(self, test_db):
        assert db.get_person(test_db, 999) is None

    def test_get_people_all(self, test_db):
        db.insert_person(test_db, "Alice", company="A")
        db.insert_person(test_db, "Bob", company="B")
        people = db.get_people(test_db)
        assert len(people) == 2

    def test_get_people_watchlisted_filter(self, test_db):
        db.insert_person(test_db, "Alice", company="A", is_watchlisted=1)
        db.insert_person(test_db, "Bob", company="B", is_watchlisted=0)

        watched = db.get_people(test_db, watchlisted=True)
        assert len(watched) == 1
        assert watched[0]["name"] == "Alice"

        not_watched = db.get_people(test_db, watchlisted=False)
        assert len(not_watched) == 1
        assert not_watched[0]["name"] == "Bob"

    def test_get_watchlisted_people(self, test_db):
        db.insert_person(test_db, "Alice", company="A", is_watchlisted=1)
        db.insert_person(test_db, "Bob", company="B", is_watchlisted=0)
        db.insert_person(test_db, "Carol", company="C", is_watchlisted=1)

        watched = db.get_watchlisted_people(test_db)
        assert len(watched) == 2
        names = {p["name"] for p in watched}
        assert names == {"Alice", "Carol"}

    def test_update_person(self, test_db):
        pid = db.insert_person(test_db, "Alice", company="A")
        db.update_person(test_db, pid, name="Alice Smith", company="Acme",
                         is_watchlisted=1)

        person = db.get_person(test_db, pid)
        assert person["name"] == "Alice Smith"
        assert person["company"] == "Acme"
        assert person["is_watchlisted"] == 1

    def test_update_person_follow_status(self, test_db):
        pid = db.insert_person(test_db, "Alice", company="A")
        db.update_person(test_db, pid, is_followed_bluesky=1)

        person = db.get_person(test_db, pid)
        assert person["is_followed_bluesky"] == 1
        assert person["is_followed_linkedin"] == 0

    def test_update_person_no_changes(self, test_db):
        pid = db.insert_person(test_db, "Alice", company="A")
        # Should not error with no kwargs
        db.update_person(test_db, pid)
        person = db.get_person(test_db, pid)
        assert person["name"] == "Alice"

    def test_update_person_ignores_invalid_fields(self, test_db):
        pid = db.insert_person(test_db, "Alice", company="A")
        db.update_person(test_db, pid, name="Bob", bogus_field="hack")
        person = db.get_person(test_db, pid)
        assert person["name"] == "Bob"

    def test_delete_person(self, test_db):
        pid = db.insert_person(test_db, "Alice", company="A")
        db.delete_person(test_db, pid)
        assert db.get_person(test_db, pid) is None
        assert len(db.get_people(test_db)) == 0

    def test_person_exists_by_linkedin(self, test_db):
        pid = db.insert_person(test_db, "Alice", company="A",
                               linkedin_url="https://linkedin.com/in/alice")
        found = db.person_exists(test_db, linkedin_url="https://linkedin.com/in/alice")
        assert found == pid

    def test_person_exists_by_bluesky(self, test_db):
        pid = db.insert_person(test_db, "Alice", company="A",
                               bluesky_handle="alice.bsky.social")
        found = db.person_exists(test_db, bluesky_handle="alice.bsky.social")
        assert found == pid

    def test_person_exists_by_name_company(self, test_db):
        pid = db.insert_person(test_db, "Alice Smith", company="Acme")
        found = db.person_exists(test_db, name="Alice Smith", company="Acme")
        assert found == pid

    def test_person_exists_not_found(self, test_db):
        db.insert_person(test_db, "Alice", company="A")
        assert db.person_exists(test_db, name="Bob", company="B") is None
        assert db.person_exists(test_db, linkedin_url="https://nope.com") is None
        assert db.person_exists(test_db, bluesky_handle="nope.bsky.social") is None

    def test_person_exists_name_only_not_enough(self, test_db):
        """Name alone without company should not match."""
        db.insert_person(test_db, "Alice", company="A")
        assert db.person_exists(test_db, name="Alice") is None

    def test_timestamps_set(self, test_db):
        pid = db.insert_person(test_db, "Alice", company="A")
        person = db.get_person(test_db, pid)
        assert person["created_at"] is not None
        assert person["updated_at"] is not None
        assert "T" in person["created_at"]  # ISO 8601 format


class TestCSVImport:
    def test_csv_import(self, test_db, tmp_path):
        csv_file = tmp_path / "people.csv"
        csv_file.write_text(
            "name,company,linkedin_url,bluesky_handle,watchlist,notes\n"
            "Alice Smith,Acme,https://linkedin.com/in/alice,alice.bsky.social,true,Key person\n"
            "Bob Jones,BigCo,,,false,\n"
            "Carol White,StartupX,,carol.bsky.social,1,Interesting\n"
        )

        import csv
        with open(csv_file, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row.get("name", "").strip()
                if not name:
                    continue
                company = row.get("company", "").strip()
                linkedin_url = row.get("linkedin_url", "").strip() or None
                bluesky_handle = row.get("bluesky_handle", "").strip() or None
                watchlist_val = row.get("watchlist", "").strip().lower()
                is_watchlisted = 1 if watchlist_val in ("1", "true", "yes") else 0
                notes = row.get("notes", "").strip()

                db.insert_person(
                    test_db, name=name, company=company,
                    linkedin_url=linkedin_url, bluesky_handle=bluesky_handle,
                    is_watchlisted=is_watchlisted, notes=notes
                )

        people = db.get_people(test_db)
        assert len(people) == 3

        alice = [p for p in people if p["name"] == "Alice Smith"][0]
        assert alice["company"] == "Acme"
        assert alice["linkedin_url"] == "https://linkedin.com/in/alice"
        assert alice["bluesky_handle"] == "alice.bsky.social"
        assert alice["is_watchlisted"] == 1
        assert alice["notes"] == "Key person"

        bob = [p for p in people if p["name"] == "Bob Jones"][0]
        assert bob["is_watchlisted"] == 0
        assert bob["linkedin_url"] is None

        carol = [p for p in people if p["name"] == "Carol White"][0]
        assert carol["is_watchlisted"] == 1

    def test_csv_import_dedup(self, test_db, tmp_path):
        db.insert_person(test_db, "Alice Smith", company="Acme",
                         linkedin_url="https://linkedin.com/in/alice")

        csv_file = tmp_path / "people.csv"
        csv_file.write_text(
            "name,company,linkedin_url,bluesky_handle,watchlist,notes\n"
            "Alice Smith,Acme,https://linkedin.com/in/alice,,true,\n"
            "Bob Jones,BigCo,,,false,\n"
        )

        import csv
        added = 0
        with open(csv_file, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row.get("name", "").strip()
                if not name:
                    continue
                company = row.get("company", "").strip()
                linkedin_url = row.get("linkedin_url", "").strip() or None
                bluesky_handle = row.get("bluesky_handle", "").strip() or None

                existing = db.person_exists(
                    test_db, name=name, company=company,
                    linkedin_url=linkedin_url, bluesky_handle=bluesky_handle
                )
                if existing:
                    continue

                db.insert_person(test_db, name=name, company=company,
                                 linkedin_url=linkedin_url, bluesky_handle=bluesky_handle)
                added += 1

        assert added == 1  # Only Bob, Alice was deduped
        assert len(db.get_people(test_db)) == 2
