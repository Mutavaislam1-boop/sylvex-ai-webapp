"""Sales request (Store -> Contact sales): only the listed choices are kept,
the required fields are checked, and the admin reads the fields as text."""
import pytest

from services import notifications as service

GOOD = {"kind": "organization", "company": "  Northwind   Studio ", "team_size": "11–50", "website": "javascript:alert(1)",
        "needs": ["video", "voice", "mining"], "budget": "500-2000", "comment": "Launch videos",
        "name": "Anna", "email": "ANNA@northwind.studio", "phone": "@anna"}


def test_fields_are_cleaned_and_unknown_choices_dropped():
    kept = service.clean_sales_request(GOOD)
    assert kept["company"] == "Northwind Studio" and kept["website"] == ""
    assert kept["needs"] == ["video", "voice"] and kept["email"] == "anna@northwind.studio"


def test_a_private_person_keeps_no_organization_fields():
    kept = service.clean_sales_request(dict(GOOD, kind="private"))
    assert kept["company"] == "" and kept["team_size"] == "" and kept["website"] == ""


@pytest.mark.parametrize("change", [{"kind": "robot"}, {"company": ""}, {"needs": []}, {"name": " "}, {"email": "anna"}])
def test_missing_or_wrong_required_fields_are_refused(change):
    with pytest.raises(service.NotificationError):
        service.clean_sales_request(dict(GOOD, **change))


def test_the_admin_reads_the_request_as_text():
    text = service.sales_request_text(service.clean_sales_request(GOOD))
    assert text.splitlines()[:3] == ["Заявка в отдел продаж", "Заявитель: Организация", "Организация: Northwind Studio"]
    assert "Интересует: Видео, Голос и музыка" in text and "Бюджет в месяц: $500–2000" in text
    assert "Контакт: Anna · anna@northwind.studio · @anna" in text and text.endswith("Launch videos")
