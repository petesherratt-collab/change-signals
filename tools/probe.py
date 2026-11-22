"""Find and check the pages to watch, before any collection.

    python tools/probe.py discover    # each site: robots.txt, redirects, candidate pages
    python tools/probe.py verify      # each listed page: two fetches, is the selection stable?

``discover`` reads ``sites`` from watchlist.yml, fetches each home page as the
archive's own user agent would, and lists links that look like careers, board
or news pages, with whether robots.txt allows them. ``verify`` reads ``pages``,
fetches each twice some seconds apart and reports whether the raw bytes and the
selected text are each byte-stable, plus sizes, so retention cost is known
before collection starts. It reports; it never edits the watchlist.

Output is Markdown on stdout, and also in the GitHub job summary when run there.
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
import time
import urllib.parse
import urllib.robotparser

import requests
import yaml
from bs4 import BeautifulSoup

USER_AGENT = "EvidenceArchive/0.1 (+https://github.com/petesherratt-collab/evidence-archive)"
KINDS = {
    "careers": re.compile(r"career|jobs|vacanc|join[- ]?us|work[- ]?(for|with)[- ]?us", re.I),
    "board": re.compile(r"board|leadership|director|management[- ]team|governance|our[- ]people", re.I),
    "news": re.compile(r"news|press|media|regulatory|rns|announcement", re.I),
}
TIMEOUT = 20


def fetch(url):
    """(final_url, status, body bytes, hops) following redirects one at a time, or an error string."""
    hops = []
    try:
        for _ in range(6):
            r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT, allow_redirects=False)
            if r.is_redirect or r.status_code in (301, 302, 303, 307, 308):
                nxt = urllib.parse.urljoin(url, r.headers.get("Location", ""))
                hops.append(f"{r.status_code} -> {nxt}")
                url = nxt
                continue
            return url, r.status_code, r.content, hops
        return url, None, b"", hops + ["too many redirects"]
    except requests.RequestException as exc:
        return url, None, b"", hops + [f"error: {type(exc).__name__}"]


def robots_for(base):
    rp = urllib.robotparser.RobotFileParser()
    _, status, body, _ = fetch(base + "/robots.txt")
    if status == 200:
        rp.parse(body.decode("utf-8", "replace").splitlines())
    else:
        rp.parse([])  # no robots.txt: everything allowed
    return rp, status


def selected_text(body, css):
    soup = BeautifulSoup(body, "html.parser")
    nodes = soup.select(css) if css else [soup]
    text = "\n".join(n.get_text("\n", strip=True) for n in nodes)
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def same_site(host, other):
    return registrable(host) == registrable(other)


def registrable(host):
    """'corporate.greggs.co.uk' -> 'greggs.co.uk'; 'www.asos.com' -> 'asos.com'."""
    parts = host.lower().split(".")
    if len(parts) >= 3 and parts[-1] == "uk" and parts[-2] in ("co", "org", "ac", "gov", "plc"):
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def discover(watch):
    out = ["# Discover", "", "| company | site | robots | home | redirects | candidates |", "|---|---|---|---|---|---|"]
    detail = []
    for c in watch["companies"]:
        for site in c["sites"]:
            base = f"https://{site}"
            rp, rstatus = robots_for(base)
            final, status, body, hops = fetch(base + "/")
            found = {k: [] for k in KINDS}
            if status == 200:
                soup = BeautifulSoup(body, "html.parser")
                for a in soup.find_all("a", href=True):
                    href = urllib.parse.urljoin(final, a["href"]).split("#")[0]
                    host = urllib.parse.urlparse(href).hostname or ""
                    if not href.startswith("http") or not same_site(site, host):
                        continue
                    label = f"{a.get_text(' ', strip=True)[:40]} {urllib.parse.urlparse(href).path}"
                    for kind, pattern in KINDS.items():
                        if pattern.search(label) and href not in [h for h, _ in found[kind]]:
                            found[kind].append((href, rp.can_fetch(USER_AGENT, href)))
            counts = ", ".join(f"{k} {len(v)}" for k, v in found.items())
            out.append(f"| {c['name']} | {site} | {rstatus} | {status} | {'; '.join(hops) or '-'} | {counts} |")
            for kind, links in found.items():
                for href, allowed in links[:4]:
                    detail.append(f"- {c['name']} / {kind}: {href}{'' if allowed else '  **robots: disallowed**'}")
    return "\n".join(out + ["", "## Candidate pages", ""] + detail)


def verify(watch, wait=20):
    out = ["# Verify", "", "| company | kind | status | redirects | raw stable | text stable | raw KB | text KB | robots |",
           "|---|---|---|---|---|---|---|---|---|"]
    robots = {}
    for p in watch.get("pages") or []:
        if str(p.get("status", "")).startswith("passed") and os.getenv("VERIFY_ALL") != "1":
            continue  # already passed; set VERIFY_ALL=1 to re-check everything
        host = urllib.parse.urlparse(p["url"]).hostname
        if host not in robots:
            robots[host] = robots_for(f"https://{host}")[0]
        first = fetch(p["url"])
        time.sleep(wait)
        second = fetch(p["url"])
        ok = first[1] == 200 and second[1] == 200
        raw_same = ok and first[2] == second[2]
        t1 = selected_text(first[2], p.get("css")) if ok else ""
        t2 = selected_text(second[2], p.get("css")) if ok else ""
        out.append(
            f"| {p['company']} | {p['kind']} | {first[1]}/{second[1]} | {'; '.join(first[3]) or '-'} | "
            f"{'yes' if raw_same else 'no'} | {'yes' if ok and t1 == t2 and t1 else 'no' if ok else '-'} | "
            f"{len(first[2]) / 1024:.0f} | {len(t1.encode()) / 1024:.1f} | "
            f"{'ok' if robots[host].can_fetch(USER_AGENT, p['url']) else 'DISALLOWED'} |")
        if ok and t1 != t2:
            a, b = set(t1.splitlines()), set(t2.splitlines())
            out.append(f"|  | churn: {sorted(a ^ b)[:3]} | | | | | | | |")
    return "\n".join(out)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "discover"
    with open("watchlist.yml", encoding="utf-8") as handle:
        watch = yaml.safe_load(handle)
    report = discover(watch) if mode == "discover" else verify(watch)
    print(report)
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(report + "\n")


if __name__ == "__main__":
    main()
