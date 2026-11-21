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
    cfg = build_config.build({"pages": [{"company": "X", "kind": "news", "url": "https://x.com/n", "css": "main"}]})
    assert cfg["checks"][0]["name"] == "X | news"
    assert cfg["checks"][0]["transform"] == [{"css": "main"}, "text"]


class FakeRouter:
    def __init__(self, log_path, answer):
        self.log_path, self.answer, self.n = log_path, answer, 0

    def handle(self, request):
        self.n += 1
        rid = f"r{self.n}"
        with open(self.log_path, "a") as h:
            h.write(json.dumps({"record_type": "fast_path_request", "request_id": rid}) + "\n")
            h.write(json.dumps({"record_type": "fast_path_observation", "request_id": rid, "agreed": True,
                                "distinct_valid_answers": 1, "models": [{"model": "m", "valid": True}]}) + "\n")
        return {"value": self.answer, "route": "model", "model": "m", "total_ms": 12.0}

    def drain(self):
        pass


class FakeFastPath:
    @staticmethod
    def FastPathRequest(*args):
        return args


def test_label_all_records_route_and_agreement(tmp_path):
    log = tmp_path / "log.jsonl"
    change = {"check": "X | careers", "company": "X", "kind": "careers", "poll_id": 3,
              "polled_at": "2026-11-20T06:17:00+00:00", "removed": ["a"], "added": ["b"]}
    done = set()
    out = label_changes.label_all([change], done, FakeRouter(log, "sell"), FakeFastPath, log)
    assert out[0]["label"] == "sell" and out[0]["agreed"] is True and out[0]["route"] == "model"
    assert label_changes.label_all([change], done, FakeRouter(log, "sell"), FakeFastPath, log) == []
    bad = label_changes.label_all([{**change, "poll_id": 4}], set(), FakeRouter(log, "maybe"), FakeFastPath, log)
    assert bad[0]["label"] is None and bad[0]["raw_value"] == "maybe"


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
