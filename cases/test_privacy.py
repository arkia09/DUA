"""Cases belong to the visitor who filed them, and are wiped when the server starts."""
import io
import json
from unittest import mock

from django.core.management import call_command
from django.test import Client, TestCase, override_settings

from . import demo
from .middleware import FreshStartMiddleware
from .models import Case
from .ollama import OllamaTimeout
from .wipe import wipe_cases


def file_sample(client, department="pending", index=0):
    text, opts = demo.example_inputs(department)[index]
    resp = client.post("/api/requests/", json.dumps({"department": department, "statement": text, "options": opts}),
                       content_type="application/json")
    assert resp.status_code == 201, resp.content
    return resp.json()["case"]["number"]


@override_settings(DEMO_MODE=True)
class IsolationTests(TestCase):
    def setUp(self):
        self.alice, self.bob = Client(), Client()
        self.number = file_sample(self.alice)

    def test_the_owner_can_use_every_endpoint(self):
        n = self.number
        self.assertEqual(self.alice.get(f"/api/cases/{n}/").status_code, 200)
        self.assertEqual(self.alice.get(f"/files/{n}/").status_code, 200)
        self.assertEqual(self.alice.get(f"/api/cases/{n}/export/md/").status_code, 200)
        self.assertEqual(self.alice.get(f"/api/cases/{n}/export/ics/").status_code, 200)
        self.assertEqual(self.alice.post(f"/api/cases/{n}/tasks/0/", '{"done": true}',
                                         content_type="application/json").status_code, 200)
        self.assertEqual([c["number"] for c in self.alice.get("/api/cases/").json()["cases"]], [n])

    def test_another_visitor_sees_nothing(self):
        n = self.number
        self.assertEqual(self.bob.get("/api/cases/").json()["cases"], [])
        for method, url in [("get", f"/api/cases/{n}/"), ("get", f"/files/{n}/"),
                            ("get", f"/api/cases/{n}/export/md/"), ("get", f"/api/cases/{n}/export/ics/"),
                            ("post", f"/api/cases/{n}/retry/"), ("post", f"/api/cases/{n}/shred/"),
                            ("post", f"/api/cases/{n}/carry-over/"), ("post", f"/api/cases/{n}/tasks/0/")]:
            with self.subTest(url=url):
                self.assertEqual(getattr(self.bob, method)(url).status_code, 404)
        self.assertTrue(Case.objects.filter(number=n).exists())     # and the shred attempt did nothing

    def test_a_visitor_with_no_session_sees_nothing(self):
        self.assertEqual(Client().get("/api/cases/").json()["cases"], [])
        self.assertEqual(Client().get(f"/api/cases/{self.number}/").status_code, 404)

    def test_each_visitor_lists_only_their_own(self):
        other = file_sample(self.bob, "tribunal")
        self.assertEqual([c["number"] for c in self.alice.get("/api/cases/").json()["cases"]], [self.number])
        self.assertEqual([c["number"] for c in self.bob.get("/api/cases/").json()["cases"]], [other])

    def test_shredding_your_own_case_works(self):
        self.assertEqual(self.alice.post(f"/api/cases/{self.number}/shred/").status_code, 200)
        self.assertFalse(Case.objects.exists())

    def test_the_owner_is_never_sent_to_the_browser(self):
        body = self.alice.get(f"/api/cases/{self.number}/").content.decode()
        self.assertNotIn(Case.objects.get().owner, body)


class FailedFirstRequestTests(TestCase):
    @mock.patch("cases.views.ask", side_effect=OllamaTimeout("x"))
    def test_a_new_visitor_keeps_access_to_a_case_whose_review_failed(self, _):
        """Django drops the session cookie on 5xx responses. The visitor must still get it."""
        client = Client()
        resp = client.post("/api/requests/", json.dumps({"department": "correspondence", "statement": "hello there"}),
                           content_type="application/json")
        self.assertEqual(resp.status_code, 504)
        self.assertIn("sessionid", client.cookies)
        number = resp.json()["case"]["number"]
        self.assertEqual(client.get(f"/api/cases/{number}/").status_code, 200)


class WipeTests(TestCase):
    def make(self, n=3):
        for i in range(n):
            Case.objects.create(department="pending", statement=f"s{i}", owner="someone")

    def test_wipe_deletes_everything_and_restarts_numbering(self):
        self.make()
        wipe_cases()
        self.assertEqual(Case.objects.count(), 0)
        self.assertEqual(Case.objects.create(department="pending", statement="x").number, "BA-2048")

    def test_wipe_command(self):
        self.make()
        out = io.StringIO()
        call_command("wipe_cases", stdout=out)
        self.assertEqual(Case.objects.count(), 0)
        self.assertIn("deleted", out.getvalue())

    @override_settings(WIPE_ON_START=True)
    def test_the_first_request_wipes_once_and_later_requests_do_not(self):
        self.make()
        FreshStartMiddleware.wiped = False
        try:
            self.client.get("/")
            self.assertEqual(Case.objects.count(), 0)
            self.make(1)
            self.client.get("/")
            self.assertEqual(Case.objects.count(), 1)
        finally:
            FreshStartMiddleware.wiped = False

    @override_settings(WIPE_ON_START=False)
    def test_wipe_can_be_switched_off(self):
        self.make()
        FreshStartMiddleware.wiped = False
        self.client.get("/")
        self.assertEqual(Case.objects.count(), 3)
