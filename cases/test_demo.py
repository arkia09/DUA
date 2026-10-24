"""Demo mode: no model, only the built-in samples. The model is replaced by a mock that fails the test if it is called."""
import io
import json
import tempfile
from pathlib import Path
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase, override_settings

from . import demo
from .departments import PAGES, VALIDATORS, clean_options
from .models import Case
from .offices.tribunal import CRISIS_NOTICE

NO_MODEL = mock.patch("cases.views.ask", side_effect=AssertionError("the model must not be called in demo mode"))


def payload(department, text, options):
    return {"department": department, "statement": text, "options": options}


def post(client, body):
    return client.post("/api/requests/", json.dumps(body), content_type="application/json")


class SampleDataTests(SimpleTestCase):
    """The data files must stay in step with the example buttons, and survive the real validators untouched."""

    def test_every_example_button_has_a_sample(self):
        for department in demo.DEPARTMENTS:
            for text, opts in demo.example_inputs(department):
                with self.subTest(department=department, text=text[:30]):
                    options, _ = clean_options(department, opts)
                    self.assertTrue(demo.has_sample(department, text, options))

    def test_no_sample_without_an_example_button(self):
        buttons = {demo.key(d, t, o) for d in demo.DEPARTMENTS for t, o in demo.example_inputs(d)}
        self.assertEqual(set(demo.samples()), buttons)

    def test_every_sample_passes_the_validators_with_nothing_dropped(self):
        for department in demo.DEPARTMENTS:
            for text, opts in demo.example_inputs(department):
                with self.subTest(department=department, text=text[:30]):
                    options, _ = clean_options(department, opts)
                    result = VALIDATORS[department](demo.answer(department, text, options), text, options)
                    body = next(v for k, v in result.items() if k != "notice")
                    for k, v in body.items():
                        if k.startswith("dropped"):
                            self.assertEqual(v, 0, k)

    def test_matching_ignores_case_spacing_and_punctuation(self):
        text, _ = demo.example_inputs("pending")[0]
        self.assertTrue(demo.has_sample("pending", "  " + text.upper().replace(",", " ,") + "\n\n", {}))

    def test_a_different_input_is_a_miss(self):
        self.assertFalse(demo.has_sample("pending", "Do my taxes", {}))
        with self.assertRaises(demo.DemoMiss):
            demo.answer("pending", "Do my taxes", {})

    def test_reply_and_preferences_are_part_of_the_match(self):
        text, opts = demo.example_inputs("correspondence")[2]
        self.assertTrue(demo.has_sample("correspondence", text, opts))
        self.assertFalse(demo.has_sample("correspondence", text, {}))
        text, opts = demo.example_inputs("tribunal")[0]
        self.assertFalse(demo.has_sample("tribunal", text, {"preferences": "expensive"}))

    def test_answers_are_copies(self):
        text, _ = demo.example_inputs("pending")[0]
        demo.answer("pending", text, {})["tasks"].clear()
        self.assertTrue(demo.answer("pending", text, {})["tasks"])


@override_settings(DEMO_MODE=True)
class DemoRequestTests(TestCase):
    def test_every_example_resolves_without_the_model(self):
        for department in demo.DEPARTMENTS:
            for text, opts in demo.example_inputs(department):
                with self.subTest(department=department, text=text[:30]), NO_MODEL:
                    resp = post(self.client, payload(department, text, opts))
                    self.assertEqual(resp.status_code, 201, resp.content)
                    case = resp.json()["case"]
                    self.assertEqual(case["status"], "resolved")
                    export = self.client.get(f"/api/cases/{case['number']}/export/md/")
                    self.assertEqual(export.status_code, 200)

    def test_tone_is_ignored(self):
        text, opts = demo.example_inputs("correspondence")[0]
        with NO_MODEL:
            resp = post(self.client, payload("correspondence", text, {**opts, "tone": "firm"}))
        self.assertEqual(resp.status_code, 201)

    def test_unknown_input_is_refused_and_no_case_is_created(self):
        with NO_MODEL:
            resp = post(self.client, payload("pending", "Do my taxes by Friday", {}))
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["error_code"], "demo_sample_only")
        self.assertIn("Try", resp.json()["error"])
        self.assertEqual(Case.objects.count(), 0)

    def test_a_crisis_message_still_gets_the_fixed_kind_reply(self):
        with NO_MODEL:
            resp = post(self.client, payload("tribunal", "Should I just end my life?", {}))
        self.assertEqual(resp.status_code, 201)
        ruling = resp.json()["case"]["result"]
        self.assertTrue(ruling["ruling"]["crisis"])
        self.assertEqual(ruling["notice"]["serious_notice"], CRISIS_NOTICE)

    def test_uploading_a_sample_document_works_and_anything_else_is_refused(self):
        text, _ = demo.example_inputs("documents")[0]
        with NO_MODEL:
            ok = self.client.post("/api/requests/upload/", {
                "department": "documents", "file": SimpleUploadedFile("notice.txt", text.encode())})
            other = self.client.post("/api/requests/upload/", {
                "department": "documents", "file": SimpleUploadedFile("mine.txt", b"A long private letter. " * 10)})
        self.assertEqual(ok.status_code, 201, ok.content)
        self.assertEqual(other.status_code, 422)
        self.assertEqual(Case.objects.count(), 1)

    def test_carry_over_is_refused_because_it_would_need_a_model(self):
        text, _ = demo.example_inputs("pending")[0]
        with NO_MODEL:
            number = post(self.client, payload("pending", text, {})).json()["case"]["number"]
            resp = self.client.post(f"/api/cases/{number}/carry-over/")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(Case.objects.count(), 1)

    def test_the_command_line_briefing_reports_a_miss_instead_of_crashing(self):
        with NO_MODEL, mock.patch("sys.stdin", io.StringIO("Pay rent. Call Sam. Buy milk.")), \
                self.assertLogs("cases.views", "WARNING"), self.assertRaises(CommandError) as ctx:
            call_command("briefing")
        self.assertIn("demo", str(ctx.exception).lower())


@override_settings(DEMO_MODE=True)
class DemoPageTests(TestCase):
    def test_banner_and_flag_are_shown(self):
        html = self.client.get("/pending/").content.decode()
        self.assertIn("demo-banner", html)
        self.assertIn('data-demo="1"', html)
        self.assertIn("Demo mode", html)

    def test_uploads_and_tone_are_switched_off(self):
        self.assertNotIn('id="file"', self.client.get("/documents/").content.decode())
        self.assertNotIn('id="tone"', self.client.get("/correspondence/").content.decode())

    def test_example_buttons_are_still_offered(self):
        html = self.client.get("/tribunal/").content.decode()
        self.assertIn("pizza or sushi", html)    # the examples travel in the page's JSON config


class LiveModePageTests(TestCase):
    def test_no_demo_banner_by_default(self):
        html = self.client.get("/pending/").content.decode()
        self.assertNotIn("demo-banner", html)
        self.assertNotIn('data-demo', html)
        self.assertIn('id="tone"', self.client.get("/correspondence/").content.decode())
        self.assertIn('id="file"', self.client.get("/documents/").content.decode())


class RecordDemoTests(SimpleTestCase):
    """record_demo rewrites the data files from whatever the (mocked) model returns."""

    def run_command(self, *args, model):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(demo, "DATA_DIR", Path(tmp)), \
                mock.patch("cases.management.commands.record_demo.ask", side_effect=model):
            try:
                call_command("record_demo", *args, stdout=io.StringIO(), stderr=io.StringIO())
            finally:
                demo.samples.cache_clear()
            return {p.name: json.loads(p.read_text()) for p in Path(tmp).iterdir()}

    def answering_from_the_samples(self):
        """A model stand-in that returns the shipped sample for whichever example it is asked about."""
        lookup = {}
        for department in demo.DEPARTMENTS:
            for text, opts in demo.example_inputs(department):
                options, _ = clean_options(department, opts)
                lookup[text] = demo.answer(department, text, options)

        def model(system, user, schema):
            for text, raw in lookup.items():
                if text in user:
                    return raw
            raise AssertionError("unexpected prompt")
        return model

    def test_records_one_office(self):
        files = self.run_command("pending", model=self.answering_from_the_samples())
        self.assertEqual(list(files), ["pending.json"])
        self.assertEqual(len(files["pending.json"]), len(PAGES["pending"]["examples"]))
        self.assertEqual(files["pending.json"][0]["text"], PAGES["pending"]["examples"][0])

    def test_nothing_is_written_when_the_model_keeps_failing(self):
        bad = mock.Mock(return_value={"tasks": []})
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(demo, "DATA_DIR", Path(tmp)), \
                mock.patch("cases.management.commands.record_demo.ask", bad):
            with self.assertRaises(CommandError):
                call_command("record_demo", "pending", "--tries", "2", stdout=io.StringIO(), stderr=io.StringIO())
            self.assertEqual(list(Path(tmp).iterdir()), [])
        self.assertEqual(bad.call_count, 2)

    @override_settings(DEMO_MODE=True)
    def test_refuses_to_run_in_demo_mode(self):
        with self.assertRaises(CommandError):
            call_command("record_demo", stdout=io.StringIO())

    def test_unknown_office_is_rejected(self):
        with self.assertRaises(CommandError):
            call_command("record_demo", "nonsense", stdout=io.StringIO())
