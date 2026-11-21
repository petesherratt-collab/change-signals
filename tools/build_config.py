"""Write kibitzr.yml from the verified pages in watchlist.yml.

    python tools/build_config.py > kibitzr.yml

Every check archives (raw response, poll log, hash chains) and selects with
the page's CSS selector then reduces to text. There is no reporting
transform, so the archive's normalised hash is taken on the selected text.
"""

import sys

import yaml


def check_name(page):
    return f"{page['company']} | {page['kind']}"


def build(watch, root="./archive"):
    checks = []
    for page in watch.get("pages") or []:
        checks.append({
            "name": check_name(page),
            "url": page["url"],
            "period": "24h",
            "archive": {"root": root},
            "transform": [{"css": page.get("css") or "body"}, "text"],
        })
    return {"checks": checks}


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--watchlist", default="watchlist.yml")
    args = parser.parse_args()
    with open(args.watchlist, encoding="utf-8") as handle:
        watch = yaml.safe_load(handle)
    yaml.safe_dump(build(watch), sys.stdout, sort_keys=False, allow_unicode=True)


if __name__ == "__main__":
    main()
