"""When "How do you like SYLVEX?" shows, counted in successful generations
(services/reviews.py), against a small in-memory stand-in for the tables."""
import re

import pytest

from services import reviews


class Cursor:
    def __init__(self, generations=0, paid=False):
        self.generations = generations
        self.paid = paid
        self.prompts = {}
        self.reviews = []
        self._result = []

    def execute(self, sql, params=()):
        sql = " ".join(sql.split())
        self._result = []
        if "FROM prostudio_generation_jobs" in sql:
            self._result = [(self.generations,)]
        elif "FROM purchases" in sql:
            self._result = [(1,)] if self.paid else []
        elif "FROM subscriptions" in sql:
            self._result = []
        elif sql.startswith("SELECT status, next_at"):
            row = self.prompts.get(params[0])
            self._result = [(row["status"], row["next_at"], row["shows"], row["closes"], row["laters"])] if row else []
        elif sql.startswith("INSERT INTO review_prompts"):
            self.prompts.setdefault(params[0], {"status": "waiting", "next_at": None, "shows": 0, "closes": 0, "laters": 0})
        elif sql.startswith("UPDATE review_prompts SET"):
            row = self.prompts[params[0]]
            for column, expression in re.findall(r"(\w+) = ([^,]+?)(?:,|$)", sql.split(" SET ", 1)[1].split(" WHERE ")[0]):
                if column == "updated_at":
                    continue
                if expression.endswith("+ 1"):
                    row[column] += 1
                elif expression.startswith("'"):
                    row[column] = expression.strip("'")
                else:
                    row[column] = int(expression)
        elif sql.startswith("INSERT INTO project_reviews"):
            self.reviews.append(params)
            self._result = [(len(self.reviews),)]
        else:
            raise AssertionError(sql)

    def fetchone(self):
        return self._result[0] if self._result else None


PERSON = {"key": "a:42", "account_id": 42}


def test_first_after_five_successful_generations():
    cur = Cursor(generations=4)
    assert not reviews.is_due(cur, PERSON, 7)
    cur.generations = 5
    assert reviews.is_due(cur, PERSON, 7)


def test_after_a_purchase_from_two_generations():
    cur = Cursor(generations=1, paid=True)
    assert not reviews.is_due(cur, PERSON, 7)
    cur.generations = 2
    assert reviews.is_due(cur, PERSON, 7)


def test_close_comes_back_ten_generations_later_and_later_twenty_five():
    cur = Cursor(generations=5)
    reviews.record(cur, PERSON, 7, "shown")
    reviews.record(cur, PERSON, 7, "close")
    cur.generations = 14
    assert not reviews.is_due(cur, PERSON, 7)
    cur.generations = 15
    assert reviews.is_due(cur, PERSON, 7)
    reviews.record(cur, PERSON, 7, "later")
    cur.generations = 39
    assert not reviews.is_due(cur, PERSON, 7)
    cur.generations = 40
    assert reviews.is_due(cur, PERSON, 7)
    row = cur.prompts["a:42"]
    assert (row["shows"], row["closes"], row["laters"], row["status"]) == (1, 1, 1, "later")


def test_never_and_a_sent_review_end_it():
    cur = Cursor(generations=50)
    reviews.record(cur, PERSON, 7, "never")
    assert not reviews.is_due(cur, PERSON, 7)
    with pytest.raises(reviews.ReviewError):
        reviews.record(cur, PERSON, 7, "send", rating=5)

    other = {"key": "t:8", "account_id": None}
    assert reviews.record(cur, other, 8, "send", rating="4", text="  Nice   tools ", surface="website") == 1
    assert cur.reviews[0][3:6] == (4, "Nice tools", "website")
    assert not reviews.is_due(cur, other, 8)
    with pytest.raises(reviews.ReviewError) as again:
        reviews.record(cur, other, 8, "close")
    assert again.value.status == 409


@pytest.mark.parametrize("rating", [None, 0, 6, "x"])
def test_a_review_needs_one_to_five_stars(rating):
    with pytest.raises(reviews.ReviewError) as error:
        reviews.record(Cursor(generations=5), PERSON, 7, "send", rating=rating)
    assert error.value.code == "invalid_rating"


def test_long_text_and_unknown_actions_are_refused():
    with pytest.raises(reviews.ReviewError):
        reviews.record(Cursor(generations=5), PERSON, 7, "send", rating=5, text="x" * 1501)
    with pytest.raises(reviews.ReviewError):
        reviews.record(Cursor(generations=5), PERSON, 7, "delete")
