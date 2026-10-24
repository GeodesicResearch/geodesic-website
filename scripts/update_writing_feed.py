#!/usr/bin/env python3
"""Regenerate the LessWrong feed in index.html (Research section).

A post is listed when Kyle O'Brien is an author, or when every author is on
the Geodesic team. Posts are pulled from the SOURCES users' LessWrong pages
(including posts they co-author), newest first. Tags, full bylines,
affiliations and linked papers come from scripts/writing_feed.json, which
must have an entry for every post that is listed.

    python3 scripts/update_writing_feed.py            # rewrite index.html
    python3 scripts/update_writing_feed.py --dry-run  # print the kept/dropped posts
"""
import datetime
import html
import json
import sys
import urllib.request
from pathlib import Path

SINCE = "2025-12-21"  # the Alignment Pretraining post
SOURCES = ["kyle-o-brien", "edward-james-young"]  # LessWrong user slugs
ALWAYS_INCLUDE = "kyle o'brien"

# Geodesic team (the Team section of index.html), by lowercase name and
# the display names they use on LessWrong. Mentors are not included.
TEAM = {
    "cameron tice", "cam",
    "puria radmard", "puria",
    "alexandra narin",
    "edward young", "edward james young",
    "kyle o'brien",
    "nathalie kirch",
    "nathaniel mitrani hadida",
}

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"
META = json.loads((ROOT / "scripts" / "writing_feed.json").read_text())
START, END = "<!-- writing-feed:start -->", "<!-- writing-feed:end -->"
GRAPHQL = "https://www.lesswrong.com/graphql"

ICONS = {
    "paper": '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true"><path d="M3.5 1.75h6l3 3v9.5h-9z"/><path d="M9.5 1.75v3h3M5.75 8h4.5M5.75 10.5h4.5"/></svg>',
    "link": '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true"><path d="M4 12L12 4M12 4H5M12 4v7"/></svg>',
}


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


def lw_authors(p):
    return [p["user"]["displayName"]] + [c["displayName"] for c in p["coauthors"]]


def keep(p):
    names = [norm(a) for a in lw_authors(p)]
    return ALWAYS_INCLUDE in names or all(n in TEAM for n in names)


def esc(text):
    text = html.escape(text.replace(" ", " ").replace("'", "’"), quote=False)
    for ch, ent in (("’", "&rsquo;"), ("‘", "&lsquo;"), ("“", "&ldquo;"), ("”", "&rdquo;")):
        text = text.replace(ch, ent)
    return text.encode("ascii", "xmlcharrefreplace").decode()


def join_names(names):
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def byline(entries):
    """Return (authors html, affiliations html) for a post's author entries."""
    people = []
    for e in entries:
        name, aff = (e, None) if isinstance(e, str) else (e["name"], e.get("aff"))
        aff = aff or META["roster"][name]
        people.append((name, aff))
    affs = []
    for _, a in people:
        affs += [x for x in a if x not in affs]
    if len(affs) == 1:
        return esc(join_names([n for n, _ in people])), esc(affs[0])
    marks = lambda a: "<sup>%s</sup>" % ",".join(str(affs.index(x) + 1) for x in a)
    names = [esc(n) + marks(a) for n, a in people]
    legend = "; ".join("<sup>%d</sup>&thinsp;%s" % (i + 1, esc(a)) for i, a in enumerate(affs))
    return join_names(names), legend


def render(p):
    m = META["posts"][p["_id"]]
    date = datetime.date.fromisoformat(p["postedAt"][:10])
    authors, affs = byline(m["authors"])
    art = m.get("artifact")
    artifact = ""
    if art:
        label = esc(art["label"])
        artifact = f'''
    <a class="writing-artifact" href="{html.escape(art["url"])}" target="_blank" rel="noopener" aria-label="{label} (opens in a new tab)">{ICONS[art.get("kind", "link")]}{label}</a>'''
    return f'''          <article class="writing-item">
            <div class="writing-meta">
              <time class="writing-date" datetime="{date}">{date.strftime("%b %-d, %Y")}</time>
              <span class="writing-tag">{m["tag"]}</span>
            </div>
            <div class="writing-main">
              <h3 class="writing-title"><a href="https://www.lesswrong.com/posts/{p["_id"]}/{p["slug"]}" target="_blank" rel="noopener">{esc(p["title"])}</a></h3>
              <p class="writing-by">{authors}</p>
              <p class="writing-aff">{affs}</p>
            </div>{artifact}
          </article>
'''


def main():
    dry = "--dry-run" in sys.argv
    posts = fetch_posts()
    kept = [p for p in posts if keep(p)]
    for p in posts:
        print(("keep " if keep(p) else "drop ") + p["postedAt"][:10], p["title"][:60], "-", ", ".join(lw_authors(p)))
    missing = [p for p in kept if p["_id"] not in META["posts"]]
    for p in kept:
        t = META["posts"].get(p["_id"], {}).get("tag")
        if t is not None and t not in META["tags"]:
            sys.exit(f"bad tag {t!r} for {p['title']}")
    if missing:
        sys.exit("Add these posts to scripts/writing_feed.json (tag, authors, artifact):\n" +
                 "\n".join(f'  {p["_id"]}  {p["title"]}  [{", ".join(lw_authors(p))}]' for p in missing))
    if dry:
        return
    s = INDEX.read_text()
    a, b = s.index(START) + len(START), s.index(END)
    INDEX.write_text(s[:a] + "\n" + "".join(render(p) for p in kept) + "          " + s[b:])
    print(f"wrote {len(kept)} posts to {INDEX.name}")


if __name__ == "__main__":
    main()
