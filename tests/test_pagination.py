"""Tests for pagination."""

import re

import pytest

import app as app_module
from pagination import page_window, paginate


@pytest.fixture
def two_per_page(monkeypatch):
    """Show only 2 students per page so 5 students make 3 pages."""
    monkeypatch.setattr(app_module, "STUDENTS_PER_PAGE", 2)


# The sample students are listed by grade, section, then name:
#   page 1: Abebe (9 A), Meron (9 B)
#   page 2: Selam (10 B), Dawit (11 A)
#   page 3: Hana (12 C)


# ------------------------------------------------------------ paginate()


def test_paginate_first_page():
    pager = paginate(total=5, page=1, per_page=2)
    assert pager["pages"] == 3
    assert pager["offset"] == 0
    assert (pager["first"], pager["last"]) == (1, 2)
    assert pager["has_prev"] is False
    assert pager["has_next"] is True


def test_paginate_last_page_is_partial():
    pager = paginate(total=5, page=3, per_page=2)
    assert pager["offset"] == 4
    assert (pager["first"], pager["last"]) == (5, 5)
    assert pager["has_prev"] is True
    assert pager["has_next"] is False


def test_paginate_exact_multiple_has_no_empty_page():
    pager = paginate(total=4, page=2, per_page=2)
    assert pager["pages"] == 2
    assert pager["last"] == 4


def test_paginate_empty_list():
    pager = paginate(total=0, page=1, per_page=20)
    assert pager["pages"] == 1
    assert (pager["first"], pager["last"]) == (0, 0)
    assert pager["has_prev"] is False
    assert pager["has_next"] is False


def test_paginate_clamps_page_numbers():
    assert paginate(5, 99, 2)["page"] == 3
    assert paginate(5, 0, 2)["page"] == 1
    assert paginate(5, -4, 2)["page"] == 1


# ------------------------------------------------------------ page_window()


def test_page_window_single_page():
    assert page_window(1, 1) == [1]


def test_page_window_shows_every_page_when_few():
    assert page_window(1, 3) == [1, 2, 3]


def test_page_window_marks_gaps():
    assert page_window(10, 20) == [1, None, 8, 9, 10, 11, 12, None, 20]


def test_page_window_fills_a_one_page_gap():
    assert page_window(5, 10) == [1, 2, 3, 4, 5, 6, 7, None, 10]


# ------------------------------------------------------------ student list


def test_first_page_shows_first_students(auth_client, two_per_page):
    response = auth_client.get("/students")
    assert b"Abebe Kebede" in response.data
    assert b"Meron Bekele" in response.data
    assert b"Selam Tadesse" not in response.data
    assert b"of 5 students" in response.data


def test_second_page_shows_next_students(auth_client, two_per_page):
    response = auth_client.get("/students?page=2")
    assert b"Selam Tadesse" in response.data
    assert b"Dawit Alemu" in response.data
    assert b"Abebe Kebede" not in response.data
    assert b"Hana Girma" not in response.data


def test_last_page_shows_remaining_student(auth_client, two_per_page):
    response = auth_client.get("/students?page=3")
    assert b"Hana Girma" in response.data
    assert b"Dawit Alemu" not in response.data


def test_page_number_too_high_shows_last_page(auth_client, two_per_page):
    response = auth_client.get("/students?page=99")
    assert response.status_code == 200
    assert b"Hana Girma" in response.data


@pytest.mark.parametrize("bad_page", ["abc", "0", "-3", ""])
def test_bad_page_number_shows_first_page(auth_client, two_per_page, bad_page):
    response = auth_client.get(f"/students?page={bad_page}")
    assert response.status_code == 200
    assert b"Abebe Kebede" in response.data


def test_filter_is_kept_in_page_links(auth_client, monkeypatch):
    monkeypatch.setattr(app_module, "STUDENTS_PER_PAGE", 1)

    response = auth_client.get("/students?grade=9")

    link = re.search(rb'href="([^"]*page=2[^"]*)"', response.data)
    assert link is not None
    assert b"grade=9" in link.group(1)


def test_filtered_second_page(auth_client, monkeypatch):
    monkeypatch.setattr(app_module, "STUDENTS_PER_PAGE", 1)

    response = auth_client.get("/students?grade=9&page=2")

    assert b"Meron Bekele" in response.data
    assert b"Abebe Kebede" not in response.data
    assert b"Selam Tadesse" not in response.data


def test_single_page_has_no_page_links(auth_client, monkeypatch):
    monkeypatch.setattr(app_module, "STUDENTS_PER_PAGE", 20)

    response = auth_client.get("/students")

    assert b'<nav class="pagination"' not in response.data
    assert b"5 students" in response.data


def test_search_with_one_result_has_no_page_links(auth_client, two_per_page):
    response = auth_client.get("/students?q=selam")

    assert b"Selam Tadesse" in response.data
    assert b"Abebe Kebede" not in response.data
    assert b'<nav class="pagination"' not in response.data


def test_csv_export_includes_every_page(auth_client, two_per_page):
    response = auth_client.get("/students/export.csv")
    text = response.data.decode("utf-8-sig")

    assert "Abebe Kebede" in text
    assert "Hana Girma" in text


def test_pagination_stays_inside_your_school(two_schools, two_per_page):
    alice, bob = two_schools
    # Bob has his own 5 students, so he sees 5 (not 10) in total.
    assert b"of 5 students" in bob.get("/students").data


def test_default_page_size_is_reasonable():
    # Guards against leaving a tiny test value in place before deploying.
    assert 10 <= app_module.STUDENTS_PER_PAGE <= 100
