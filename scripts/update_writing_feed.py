#!/usr/bin/env python3
"""Regenerate the "Writing on LessWrong" feed in index.html.

A post is listed when Kyle O'Brien is an author, or when every author is on
the Geodesic team. Posts are pulled from the SOURCES users' LessWrong pages
(including posts they co-author), newest first.

    python3 scripts/update_writing_feed.py            # rewrite index.html
    python3 scripts/update_writing_feed.py --dry-run  # print the kept/dropped posts
"""
import html
import json
import re
import sys
import urllib.request
from pathlib import Path

SINCE = "2025-12-21"  # the Alignment Pretraining post
SOURCES = ["kyle-o-brien", "edward-james-young"]  # LessWrong user slugs
ALWAYS_INCLUDE = "kyle o'brien"

# Geodesic team (the Team section of index.html), by lowercase name and
# the display names they use on LessWrong. Advisors are not included.
TEAM = {
    "cameron tice", "cam",
    "puria radmard", "puria",
    "alexandra narin",
    "edward young", "edward james young",
    "kyle o'brien",
    "nathalie kirch",
    "nathaniel mitrani hadida",
}

INDEX = Path(__file__).resolve().parent.parent / "index.html"
START, END = "<!-- writing-feed:start -->", "<!-- writing-feed:end -->"
GRAPHQL = "https://www.lesswrong.com/graphql"


def gql(query):
    req = urllib.request.Request(
        GRAPHQL, json.dumps({"query": query}).encode(),
        {"content-type": "application/json", "user-agent": "geodesic-website-feed"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["data"]


def norm(name):
    return name.replace("’", "'").strip().lower()


def fetch_posts():
    posts = {}
    for slug in SOURCES:
        uid = gql('{ user(input:{selector:{slug:"%s"}}){ result{ _id } } }' % slug)["user"]["result"]["_id"]
        data = gql('{ posts(input:{terms:{view:"userPosts", userId:"%s", limit:100, after:"%s"}})'
                   '{ results{ _id title slug postedAt draft shortform user{displayName} coauthors{displayName} } } }'
                   % (uid, SINCE))
        for p in data["posts"]["results"]:
            if not p.get("draft") and not p.get("shortform"):
                posts[p["_id"]] = p
    return sorted(posts.values(), key=lambda p: p["postedAt"], reverse=True)


def authors(p):
    return [p["user"]["displayName"]] + [c["displayName"] for c in p["coauthors"]]


def keep(p):
    names = [norm(a) for a in authors(p)]
    return ALWAYS_INCLUDE in names or all(n in TEAM for n in names)


def esc(text):
    text = html.escape(text.replace(" ", " "), quote=False)
    for ch, ent in (("’", "&rsquo;"), ("‘", "&lsquo;"), ("“", "&ldquo;"), ("”", "&rdquo;")):
        text = text.replace(ch, ent)
    return text.encode("ascii", "xmlcharrefreplace").decode()


def byline(names):
    if len(names) <= 4:
        shown, rest = names[:-1], names[-1:]
        return esc(", ".join(shown) + (" and " if shown else "") + rest[0])
    return esc(f"{names[0]}, {names[1]} and {len(names) - 2} others")


def render(p):
    date = p["postedAt"][:10]
    pretty = __import__("datetime").date.fromisoformat(date).strftime("%b %-d, %Y")
    return f'''          <a class="writing-item" href="https://www.lesswrong.com/posts/{p["_id"]}/{p["slug"]}" target="_blank" rel="noopener">
            <time class="writing-date" datetime="{date}">{pretty}</time>
            <span class="writing-title">{esc(p["title"])}</span>
            <span class="writing-by">{byline(authors(p))}</span>
          </a>
'''


def main():
    dry = "--dry-run" in sys.argv
    posts = fetch_posts()
    kept = [p for p in posts if keep(p)]
    for p in posts:
        print(("keep " if keep(p) else "drop ") + p["postedAt"][:10], p["title"][:60], "-", ", ".join(authors(p)))
    if dry:
        return
    s = INDEX.read_text()
    a, b = s.index(START) + len(START), s.index(END)
    INDEX.write_text(s[:a] + "\n" + "".join(render(p) for p in kept) + "          " + s[b:])
    print(f"wrote {len(kept)} posts to {INDEX.name}")


if __name__ == "__main__":
    main()
