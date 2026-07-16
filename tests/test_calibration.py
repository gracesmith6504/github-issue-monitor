"""Validation harness: compare actual LLM scores against expected scores for known issues.

This test hits the real GitHub API and a real LLM endpoint, so it's marked slow
and skipped by default. Run it explicitly:

    pytest tests/test_calibration.py -m slow

Set CALIBRATION_MODEL to override the model (default: gpt-4o-mini):

    CALIBRATION_MODEL=gpt-4o pytest tests/test_calibration.py -m slow
"""
import json
import os
import subprocess
import time

import pytest

from app.core.assessment import assess_issue
from app.core.llm import LLMClient
from app.core.profiles import load_profile
from app.core.prompt import build_system_prompt

pytestmark = pytest.mark.slow

EXPECTED = {
    832:  (5, 5, 5, "JUMP ON IT"),
    1339: (5, 5, 5, "JUMP ON IT"),
    2173: (5, 4, 3, "GO FOR IT"),
    2095: (4, 4, 5, "JUMP ON IT"),
    1347: (3, 3, 3, "STRETCH"),
    1425: (3, 2, 2, "STRETCH"),
    2304: (2, 2, 1, "LONG SHOT"),
    1358: (2, 1, 1, "NOT YET"),
    2267: (2, 3, 3, "STRETCH"),
    2309: (3, 2, 2, "STRETCH"),
    2292: (3, 1, 2, "STRETCH"),
    2278: (3, 2, 2, "STRETCH"),
}


def _get_token():
    result = subprocess.run(
        ["gh", "auth", "token"], capture_output=True, text=True
    )
    if result.returncode != 0:
        pytest.skip("gh auth token failed — not logged in")
    return result.stdout.strip()


def _fetch_issue(issue_num):
    result = subprocess.run(
        ["gh", "issue", "view", str(issue_num), "--repo", "NVIDIA/OpenShell",
         "--json", "number,title,body,labels,url,comments"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None
    data = json.loads(result.stdout)
    return {
        "repo": "NVIDIA/OpenShell",
        "number": data["number"],
        "title": data["title"],
        "body": data.get("body") or "",
        "url": data.get("url", ""),
        "labels": [l["name"] for l in data.get("labels", [])],
        "comments": [
            {"user": c["author"]["login"], "body": c["body"]}
            for c in (data.get("comments") or [])[-5:]
        ],
        "repo_language": "Rust",
    }


class TestCalibration:
    @pytest.fixture(autouse=True, scope="class")
    def setup(self, request):
        token = _get_token()
        model = os.environ.get("CALIBRATION_MODEL", "gpt-4o-mini")
        profile = load_profile("openshell")
        system_prompt = build_system_prompt(profile)
        client = LLMClient(
            api_key=token, base_url="https://models.github.ai/inference"
        )

        results = []
        test_issues = list(EXPECTED.keys())

        for issue_num in test_issues:
            issue = _fetch_issue(issue_num)
            if not issue:
                continue
            analysis = assess_issue(
                issue, client, model,
                system_prompt=system_prompt, profile=profile,
            )
            results.append((issue_num, issue["title"], analysis))
            time.sleep(1)

        request.cls.results = results
        request.cls.model = model

    def test_print_results(self):
        print(f"\nModel: {self.model} | Profile: openshell")
        print(f"{'#':>5} {'Verdict':<12} {'Score':>5} {'SP':>2} {'Sc':>2} {'Fm':>2}  Title")
        print("-" * 100)

        for issue_num, title, analysis in self.results:
            if not analysis:
                print(f"{issue_num:>5} {'FAILED':<12}")
                continue
            v = analysis["verdict"]
            t = analysis["total_score"]
            sp = analysis["starting_point"]
            sc = analysis["scope"]
            fm = analysis["familiarity"]
            short_title = (title or "")[:58]
            print(f"{issue_num:>5} {v:<12} {t:>3}/15  {sp:>1}  {sc:>1}  {fm:>1}  {short_title}")

    def test_verdict_accuracy(self):
        verdict_correct = 0
        validated = 0

        for issue_num, _title, analysis in self.results:
            if not analysis or issue_num not in EXPECTED:
                continue
            validated += 1
            _exp_sp, _exp_sc, _exp_fm, exp_verdict = EXPECTED[issue_num]
            if analysis["verdict"] == exp_verdict:
                verdict_correct += 1

        assert validated > 0, "No issues were validated"
        pct = verdict_correct / validated * 100
        print(f"\nVerdict accuracy: {verdict_correct}/{validated} ({pct:.0f}%)")

    def test_score_accuracy(self):
        exact = 0
        close = 0
        miss = 0
        validated = 0
        misses = []

        for issue_num, title, analysis in self.results:
            if not analysis or issue_num not in EXPECTED:
                continue
            validated += 1
            exp_sp, exp_sc, exp_fm, exp_verdict = EXPECTED[issue_num]
            act_sp = analysis["starting_point"]
            act_sc = analysis["scope"]
            act_fm = analysis["familiarity"]
            max_diff = max(
                abs(act_sp - exp_sp), abs(act_sc - exp_sc), abs(act_fm - exp_fm)
            )
            if max_diff == 0:
                exact += 1
            elif max_diff <= 1:
                close += 1
            else:
                miss += 1
                misses.append((issue_num, title, analysis, EXPECTED[issue_num]))

        assert validated > 0, "No issues were validated"
        print(f"\nScores: {exact} exact, {close} close (+-1), {miss} missed")

        for issue_num, title, analysis, expected in misses:
            exp_sp, exp_sc, exp_fm, exp_verdict = expected
            print(f"\n  #{issue_num}: {title}")
            print(f"    Expected: SP={exp_sp} Scope={exp_sc} Fam={exp_fm} -> {exp_verdict}")
            print(f"    Actual:   SP={analysis['starting_point']} Scope={analysis['scope']} Fam={analysis['familiarity']} -> {analysis['verdict']}")
