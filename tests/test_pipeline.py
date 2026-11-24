import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import build_config  # noqa: E402
import label_changes  # noqa: E402
import probe  # noqa: E402
import score  # noqa: E402
import extract_changes  # noqa: E402


def test_registrable_domain():
    assert probe.registrable("corporate.greggs.co.uk") == "greggs.co.uk"
    assert probe.registrable("www.asos.com") == "asos.com"
    assert probe.same_site("www.greggs.com", "greggs.com")
    assert not probe.same_site("www.greggs.com", "www.greggs.co.uk")


def test_selected_text_and_diff():
    html = b"<nav>Menu</nav><main><p>A</p><p> B </p></main>"
    assert probe.selected_text(html, "main") == "A\nB"
    assert extract_changes.diff("A\nB", "B\nC") == (["A"], ["C"])


def test_build_config():
    cfg = build_config.build({"pages": [{"company": "X", "kind": "news", "url": "https://x.com/n", "css": "main", "status": "passed 2026-11-22"}, {"company": "Y", "kind": "news", "url": "https://y.com", "status": "new"}]})
    assert cfg["checks"][0]["name"] == "X | news"
    assert cfg["checks"][0]["transform"] == [{"css": "main"}, "text"]


class FakeFuture:
    def __init__(self, value):
        self.value = value

    def result(self):
        return self.value

    def done(self):
        return True


class FakeRouter:
    """Step A through handle(); step B through start_prompt_race()."""

    def __init__(self, log_path, cosmetic, votes):
        self.log_path, self.cosmetic, self.votes, self.n = log_path, cosmetic, votes, 0

    def handle(self, request):
        self.n += 1
        rid = f"r{self.n}"
        with open(self.log_path, "a") as h:
            h.write(json.dumps({"record_type": "fast_path_request", "request_id": rid}) + "\n")
            h.write(json.dumps({"record_type": "fast_path_observation", "request_id": rid, "agreed": True,
                                "distinct_valid_answers": 1, "models": []}) + "\n")
        return {"value": self.cosmetic, "route": "model", "model": "m", "total_ms": 10.0}

    def drain(self):
        pass

    def start_prompt_race(self, prompt):
        return {FakeFuture({"model": f"m{i}", "valid": True, "value": v, "total_ms": 5 + i}): f"m{i}"
                for i, v in enumerate(self.votes)}


class FakeFastPath:
    @staticmethod
    def FastPathRequest(*args):
        return args

    @staticmethod
    def build_answer_prompt(*args):
        return "prompt"


CHANGE = {"check": "X | careers", "company": "X", "kind": "careers", "poll_id": 3,
          "polled_at": "2026-11-20T06:17:00+00:00", "removed": ["a"], "added": ["b"]}


def test_cosmetic_change_is_irrelevant_without_step_b(tmp_path, monkeypatch):
    monkeypatch.setattr(label_changes, "wait", lambda fs, return_when: (set(fs), set()))
    log = tmp_path / "log.jsonl"
    out = label_changes.label_all([CHANGE], set(), FakeRouter(log, True, ["sell"]), FakeFastPath, log)
    assert out[0]["label"] == "irrelevant" and out[0]["cosmetic"] is True and out[0]["b_model"] is None
    assert out[0]["route"] == "model" and out[0]["agreed"] is True


def test_non_cosmetic_change_is_raced_and_disagreement_is_flagged(tmp_path, monkeypatch):
    monkeypatch.setattr(label_changes, "wait", lambda fs, return_when: (set(fs), set()))
    log = tmp_path / "log.jsonl"
    done = set()
    out = label_changes.label_all([CHANGE], done, FakeRouter(log, False, ["sell", "sell", "irrelevant"]), FakeFastPath, log)
    assert out[0]["label"] == "sell" and out[0]["b_votes"] == {"sell": 2, "irrelevant": 1}
    assert out[0]["b_agreed"] is False and out[0]["agreed"] is False
    assert label_changes.label_all([CHANGE], done, FakeRouter(log, False, ["sell"]), FakeFastPath, log) == []


def test_price_lines_are_stripped_but_counts_kept():
    text = "296.0p\n▲ +6.0p · +2.07%\n33.60\n-0.30\nShare price at 23 Nov 26 16:35\n15\nStore manager, Leeds\n+2.07%"
    assert extract_changes.strip_prices(text) == "15\nStore manager, Leeds"


def series(start, values):
    d, out = datetime.date.fromisoformat(start), []
    for v in values:
        while d.weekday() >= 5:
            d += datetime.timedelta(days=1)
        out.append((d, v))
        d += datetime.timedelta(days=1)
    return out


def test_entry_is_strictly_after_the_poll_date():
    stock = series("2026-11-02", [100, 200] + [220] * 25)   # jumps on day 2
    bench = series("2026-11-02", [1000] * 27)
    # polled on the first day: entry is day 2's close, so the jump is NOT captured
    assert abs(score.excess(stock, bench, datetime.date(2026, 11, 2), 5) - 0.10) < 1e-9
    assert score.excess(stock, bench, datetime.date(2026, 11, 2), 30) is None


def test_events_net_per_company_day():
    labels = [{"company": "X", "label": "buy", "polled_at": "2026-11-02T06:00"},
              {"company": "X", "label": "sell", "polled_at": "2026-11-02T06:00"},
              {"company": "X", "label": "sell", "polled_at": "2026-11-03T06:00"},
              {"company": "X", "label": "irrelevant", "polled_at": "2026-11-04T06:00"}]
    ev = score.events(labels, {"X": "X.L"})
    assert [(e["date"].isoformat(), e["side"]) for e in ev] == [("2026-11-03", "sell")]


def test_permutation_p_is_small_for_a_clear_gap_and_large_for_none():
    gap, p = score.permutation_p([0.05] * 10, [-0.05] * 10, n=2000)
    assert gap > 0 and p < 0.01
    _, p2 = score.permutation_p([0.0, 0.01, -0.01] * 4, [0.0, -0.01, 0.01] * 4, n=2000)
    assert p2 > 0.3
