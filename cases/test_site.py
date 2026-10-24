"""Site-level tests: hidden pages, themed 404, field order, CSRF on every write, environment-based configuration."""
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import Client, SimpleTestCase, TestCase

from .models import Case
from .offices import pending
from .test_core import own


class HiddenPageTests(TestCase):
    def test_hidden_pages_exist_and_unlock_their_secret(self):
        for url, secret in (("/break-room/", "break"), ("/complaints/", "complaints")):
            with self.subTest(url=url):
                resp = self.client.get(url)
                self.assertEqual(resp.status_code, 200)
                self.assertContains(resp, f'data-unlock="{secret}"')
                self.assertContains(resp, 'id="sloth"')                   # still the same Department

    def test_hidden_pages_are_not_linked_from_the_navigation(self):
        home = self.client.get("/").content.decode()
        nav = home.split('aria-label="Departments"')[1].split("</nav>")[0]
        self.assertNotIn("break-room", nav)
        self.assertNotIn("complaints", nav)

    def test_robots_txt_leaks_exactly_the_break_room_clue(self):
        resp = self.client.get("/robots.txt")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp["Content-Type"].startswith("text/plain"))
        self.assertIn("Disallow: /break-room/", resp.content.decode())
        self.assertNotIn("complaints", resp.content.decode())

    def test_every_page_loads_the_fun_script_and_the_button(self):
        for url in ("/", "/pending/", "/documents/", "/break-room/", "/files/"):
            with self.subTest(url=url):
                resp = self.client.get(url)
                self.assertContains(resp, "cases/fun.js")
                self.assertContains(resp, 'id="dnc"')
                self.assertContains(resp, 'id="clearance"')

    def test_front_desk_has_the_staff_record(self):
        self.assertContains(self.client.get("/"), 'id="recordBody"')

    def test_fun_script_exists_and_only_writes_text(self):
        js = Path(finders.find("cases/fun.js")).read_text(encoding="utf-8")
        self.assertNotIn("innerHTML", js)
        self.assertNotIn("eval(", js)
        self.assertNotIn("fetch(", js)               # the record and the complaints never leave the browser
        self.assertIn("prefers-reduced-motion", js)
        self.assertIn("dua.record.v1", js)


class ThemedNotFoundTests(TestCase):
    def test_unknown_department_gets_the_permit_with_a_404_status(self):
        resp = self.client.get("/nonsense/")
        self.assertEqual(resp.status_code, 404)
        self.assertContains(resp, "Permit to Not Exist", status_code=404)
        self.assertContains(resp, 'data-unlock="lost"', status_code=404)
        self.assertContains(resp, "/complaints/", status_code=404)

    def test_unknown_case_page_and_unknown_path_get_it_too(self):
        for url in ("/files/NOPE-1/", "/a/b/c/d/"):
            with self.subTest(url=url):
                self.assertContains(self.client.get(url), "Permit to Not Exist", status_code=404)

    def test_requested_path_is_escaped_not_executed(self):
        resp = self.client.get("/files/%3Cscript%3Ealert(1)%3C/script%3E/")
        body = resp.content.decode()
        self.assertEqual(resp.status_code, 404)
        self.assertNotIn("<script>alert(1)", body)

    def test_api_not_found_stays_json(self):
        resp = self.client.get("/api/cases/NOPE-1/")
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json(), {"error": "Case not found"})


class FieldOrderTests(SimpleTestCase):
    def test_task_fields_read_in_a_useful_order_and_why_is_renamed(self):
        js = Path(finders.find("cases/app.js")).read_text(encoding="utf-8")
        order = [js.index(f'row(dl, "{label}"') for label in (
            "Next step (under 5 minutes)", "Deadline (as you stated)", "Minimum effort to be done",
            "Why it ranks here", "Do these first")]
        self.assertEqual(order, sorted(order))
        self.assertNotIn('row(dl, "Why",', js)

    def test_prompt_asks_for_a_reason_that_is_not_a_restatement(self):
        self.assertIn("why the\n   task ranks where it does", pending.PENDING_SYSTEM)
        self.assertIn("Do not\n   merely repeat the deadline", pending.PENDING_SYSTEM)
        self.assertIn("starting with a verb", pending.PENDING_SYSTEM)


class CsrfEverywhereTests(TestCase):
    def test_writes_are_refused_without_a_token(self):
        strict = Client(enforce_csrf_checks=True)
        body = json.dumps({"department": "pending", "statement": "do taxes by friday"})
        self.assertEqual(strict.post("/api/requests/", body, content_type="application/json").status_code, 403)
        case = Case.objects.create(owner=own(self.client), department="pending", statement="x", status="failed")
        self.assertEqual(strict.post(f"/api/cases/{case.number}/retry/").status_code, 403)
        self.assertEqual(Case.objects.count(), 1)

    @mock.patch("cases.views.ask")
    def test_a_token_from_the_page_is_accepted(self, ask_mock):
        from .test_offices import good_ruling
        ask_mock.return_value = good_ruling()
        strict = Client(enforce_csrf_checks=True)
        strict.get("/tribunal/")
        token = strict.cookies["csrftoken"].value
        resp = strict.post("/api/requests/", json.dumps({"department": "tribunal", "statement": "Pizza or sushi?"}),
                           content_type="application/json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(resp.status_code, 201)

    def test_page_script_sends_the_token_on_every_post(self):
        js = Path(finders.find("cases/app.js")).read_text(encoding="utf-8")
        self.assertNotIn('fetch(url, {method: "POST", headers: {"Content-Type"', js)   # the old, token-less call
        self.assertIn("X-CSRFToken", js)


class EnvironmentConfigTests(SimpleTestCase):
    def run_check(self, **env):
        base = {k: v for k, v in os.environ.items() if not k.startswith("DJANGO_")}
        base.update(env)
        return subprocess.run([sys.executable, "manage.py", "check"], cwd=settings.BASE_DIR, env=base,
                              capture_output=True, text=True, timeout=60)

    def test_local_defaults_still_work(self):
        self.assertEqual(self.run_check().returncode, 0)

    def test_refuses_to_start_without_a_secret_key_when_debug_is_off(self):
        r = self.run_check(DJANGO_DEBUG="false")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("DJANGO_SECRET_KEY", r.stderr)

    def test_production_style_settings_are_accepted(self):
        r = self.run_check(DJANGO_DEBUG="false", DJANGO_SECRET_KEY="k" * 50, DJANGO_ALLOWED_HOSTS="example.com")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_no_hardcoded_production_secret_remains(self):
        text = (Path(settings.BASE_DIR) / "dua" / "settings.py").read_text(encoding="utf-8")
        self.assertNotIn("6cmv2w7", text)
