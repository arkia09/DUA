import json
from unittest import mock

import requests
from django.test import SimpleTestCase, TestCase, override_settings

from .models import Case
from .ollama import (
    OllamaError, OllamaInvalidResponse, OllamaModelMissing, OllamaTimeout, OllamaUnavailable, ask,
)
from .validation import InvalidModelOutput, validate_pending

STATEMENT = "I have 3 assignments due Friday, an email to reply to, and my room is a mess."


def good_raw(**over):
    raw = {
        "tasks": [
            {"title": "Finish assignments", "urgency": "critical", "verdict": "do_now", "reason": "Due soon.",
             "deadline": "Friday", "depends_on": [], "next_step": "Open the first assignment.",
             "minimum_effort": "Submit a passable draft.", "status_remark": "Noted with alarm."},
            {"title": "Reply to email", "urgency": "medium", "verdict": "schedule", "reason": "Quick win.",
             "deadline": None, "depends_on": ["Finish assignments"], "next_step": "Write one line.",
             "minimum_effort": "Send one sentence.", "status_remark": "Pending."},
            {"title": "Clean room", "urgency": "low", "verdict": "deny", "reason": "No deadline mentioned.",
             "deadline": None, "depends_on": [], "next_step": "Close the door.",
             "minimum_effort": "None required.", "status_remark": "Request denied."},
        ],
        "clarifying_questions": ["Which email is it?"],
        "smallest_next_action": "Open the first assignment.",
        "official_notice": "The Bureau acknowledges your Friday.",
    }
    raw.update(over)
    return raw


def fake_response(status=200, body=None, text=None):
    r = mock.Mock()
    r.status_code = status
    r.ok = status < 400
    r.json.return_value = body
    return r


def chat_body(content):
    return {"message": {"role": "assistant", "content": content}}


class ValidationTests(SimpleTestCase):
    def test_valid_output_is_separated_into_plan_and_notice(self):
        out = validate_pending(good_raw(), STATEMENT)
        self.assertEqual(out["plan"]["tasks"][0]["deadline"], "Friday")
        self.assertNotIn("status_remark", out["plan"]["tasks"][0])
        self.assertEqual(out["notice"]["task_remarks"], ["Noted with alarm.", "Pending.", "Request denied."])
        self.assertEqual(out["plan"]["tasks"][1]["depends_on"], ["Finish assignments"])

    def test_verdicts_minimum_effort_and_questions(self):
        out = validate_pending(good_raw(), STATEMENT)["plan"]
        self.assertEqual([t["verdict"] for t in out["tasks"]], ["do_now", "schedule", "deny"])
        self.assertEqual(out["tasks"][2]["minimum_effort"], "None required.")
        self.assertEqual(out["clarifying_questions"], ["Which email is it?"])

    def test_cannot_deny_or_defer_deadline_or_high_stakes_tasks(self):
        raw = good_raw()
        raw["tasks"][0]["verdict"] = "deny"          # critical + stated deadline
        raw["tasks"][1].update(verdict="defer", urgency="high")
        tasks = validate_pending(raw, STATEMENT)["plan"]["tasks"]
        self.assertEqual(tasks[0]["verdict"], "do_now")
        self.assertEqual(tasks[1]["verdict"], "schedule")

    def test_deadline_alone_blocks_deny(self):
        raw = good_raw()
        raw["tasks"][2].update(verdict="deny", urgency="low", deadline="Friday")
        self.assertEqual(validate_pending(raw, STATEMENT)["plan"]["tasks"][2]["verdict"], "schedule")

    def test_plan_never_excuses_everything(self):
        raw = good_raw()
        for t in raw["tasks"]:
            t.update(verdict="deny", urgency="low", deadline=None)
        verdicts = [t["verdict"] for t in validate_pending(raw, STATEMENT)["plan"]["tasks"]]
        self.assertEqual(verdicts[0], "schedule")

    def test_questions_are_capped_and_bad_values_ignored(self):
        out = validate_pending(good_raw(clarifying_questions=["a", "b", "c", "d", 5, ""]), STATEMENT)
        self.assertEqual(out["plan"]["clarifying_questions"], ["a", "b", "c"])
        self.assertEqual(validate_pending(good_raw(clarifying_questions="x"), STATEMENT)["plan"]["clarifying_questions"], [])

    def test_invented_deadline_is_dropped(self):
        raw = good_raw()
        raw["tasks"][0]["deadline"] = "2026-10-23"
        out = validate_pending(raw, STATEMENT)
        self.assertIsNone(out["plan"]["tasks"][0]["deadline"])

    def test_dangling_dependency_is_dropped(self):
        raw = good_raw()
        raw["tasks"][1]["depends_on"] = ["Something never listed"]
        self.assertEqual(validate_pending(raw, STATEMENT)["plan"]["tasks"][1]["depends_on"], [])

    def test_rejects_bad_shapes(self):
        bad = [
            [],
            {"tasks": []},
            {"tasks": "nope"},
            good_raw(tasks=[{"title": "x", "urgency": "apocalyptic", "verdict": "do_now", "reason": "r", "next_step": "n", "minimum_effort": "m"}]),
            good_raw(tasks=[{"title": "", "urgency": "low", "verdict": "deny", "reason": "r", "next_step": "n", "minimum_effort": "m"}]),
            good_raw(smallest_next_action=""),
            good_raw(tasks=[{"title": "x", "urgency": "low", "verdict": "obliterate", "reason": "r",
                             "next_step": "n", "minimum_effort": "m"}]),
            good_raw(tasks=["not a dict"]),
        ]
        for raw in bad:
            with self.subTest(raw=raw), self.assertRaises(InvalidModelOutput):
                validate_pending(raw, STATEMENT)


@override_settings(OLLAMA_BASE_URL="http://ollama.test:1234", OLLAMA_MODEL="gemma4:e4b",
                   OLLAMA_CONNECT_TIMEOUT=2, OLLAMA_READ_TIMEOUT=9)
class OllamaClientTests(SimpleTestCase):
    @mock.patch("cases.ollama.requests.post")
    def test_request_uses_configured_url_model_and_timeouts(self, post):
        post.return_value = fake_response(body=chat_body('{"a": 1}'))
        self.assertEqual(ask("sys", "usr", {"type": "object"}), {"a": 1})
        args, kwargs = post.call_args
        self.assertEqual(args[0], "http://ollama.test:1234/api/chat")
        self.assertEqual(kwargs["json"]["model"], "gemma4:e4b")
        self.assertEqual(kwargs["timeout"], (2, 9))
        self.assertFalse(kwargs["json"]["stream"])

    @mock.patch("cases.ollama.requests.post")
    def test_error_mapping(self, post):
        cases = [
            (requests.ConnectionError("x"), OllamaUnavailable),
            (requests.ConnectTimeout("x"), OllamaUnavailable),
            (requests.ReadTimeout("x"), OllamaTimeout),
        ]
        for exc, expected in cases:
            post.side_effect = exc
            with self.subTest(exc=type(exc).__name__), self.assertRaises(expected):
                ask("s", "u", {})
        post.side_effect = None
        post.return_value = fake_response(404, {"error": "model not found"})
        with self.assertRaises(OllamaModelMissing):
            ask("s", "u", {})
        post.return_value = fake_response(500, {})
        with self.assertRaises(OllamaError) as cm:
            ask("s", "u", {})
        self.assertEqual(cm.exception.code, "generation_failed")

    @mock.patch("cases.ollama.requests.post")
    def test_malformed_output(self, post):
        for body in [chat_body("not json {"), chat_body("[1, 2]"), {"unexpected": True}]:
            post.return_value = fake_response(body=body)
            with self.subTest(body=body), self.assertRaises(OllamaInvalidResponse):
                ask("s", "u", {})


@override_settings(MAX_STATEMENT_CHARS=200)
class FileRequestTests(TestCase):
    url = "/api/requests/"

    def post(self, payload):
        body = payload if isinstance(payload, (str, bytes)) else json.dumps(payload)
        return self.client.post(self.url, body, content_type="application/json")

    @mock.patch("cases.views.ask")
    def test_happy_path(self, ask_mock):
        ask_mock.return_value = good_raw()
        resp = self.post({"department": "pending", "statement": STATEMENT})
        self.assertEqual(resp.status_code, 201)
        case = resp.json()["case"]
        self.assertEqual(case["status"], "resolved")
        self.assertTrue(case["number"].startswith("BA-"))
        self.assertEqual(case["result"]["plan"]["smallest_next_action"], "Open the first assignment.")
        self.assertIn("official_notice", case["result"]["notice"])
        # statement is passed to the model inside delimiters, as data
        user_prompt = ask_mock.call_args[0][1]
        self.assertIn("<statement>", user_prompt)
        self.assertIn(STATEMENT, user_prompt)

    def test_input_validation(self):
        bad = [
            ("{not json", "Invalid JSON"),
            ("[1]", "Invalid JSON"),
            ({"department": "nope", "statement": "x"}, "Unknown department"),
            ({"department": "pending", "statement": "   "}, "Statement is empty"),
            ({"department": "pending", "statement": 123}, "Statement is empty"),
            ({"department": "pending", "statement": "x" * 201}, "too long"),
        ]
        for payload, msg in bad:
            with self.subTest(payload=payload):
                resp = self.post(payload)
                self.assertEqual(resp.status_code, 400)
                self.assertIn(msg, resp.json()["error"])
        self.assertEqual(Case.objects.count(), 0)

    @mock.patch("cases.views.ask")
    def test_ollama_failures_are_safe(self, ask_mock):
        for exc, status, code in [
            (OllamaUnavailable("secret internal detail"), 503, "unavailable"),
            (OllamaModelMissing("x"), 503, "model_missing"),
            (OllamaTimeout("x"), 504, "timeout"),
            (OllamaInvalidResponse("x"), 502, "invalid_response"),
            (OllamaError("boom"), 500, "generation_failed"),
        ]:
            ask_mock.side_effect = exc
            with self.subTest(code=code):
                resp = self.post({"department": "pending", "statement": STATEMENT})
                self.assertEqual(resp.status_code, status)
                body = resp.json()
                self.assertEqual(body["error_code"], code)
                self.assertEqual(body["case"]["status"], "failed")
                self.assertNotIn("secret internal detail", resp.content.decode())

    @mock.patch("cases.views.ask")
    def test_unusable_model_output_marks_case_failed(self, ask_mock):
        ask_mock.return_value = {"tasks": []}
        resp = self.post({"department": "pending", "statement": STATEMENT})
        self.assertEqual(resp.status_code, 502)
        self.assertEqual(Case.objects.get().status, "failed")
        self.assertIsNone(Case.objects.get().result)


class PageTests(TestCase):
    def test_index_renders(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Bureau of Pending Affairs")

    def test_list_cases(self):
        Case.objects.create(department="pending", statement="x")
        self.assertEqual(len(self.client.get("/api/cases/").json()["cases"]), 1)
