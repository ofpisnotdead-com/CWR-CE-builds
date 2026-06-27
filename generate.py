#!/usr/bin/env python3
"""Generate a static index of CWR-CE CI builds, linking artifacts via nightly.link."""

import html
import json
import os
import re
import urllib.request
from datetime import datetime, timezone

REPO = os.environ.get("REPO", "ofpisnotdead-com/CWR-CE")
OUTPUT = os.environ.get("OUTPUT", "_site/index.html")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
API = f"https://api.github.com/repos/{REPO}/actions"


def fetch_json(url):
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def fetch_artifacts():
    items, page = [], 1
    while True:
        data = fetch_json(f"{API}/artifacts?per_page=100&page={page}")
        batch = data.get("artifacts", [])
        items += batch
        if len(items) >= data.get("total_count", 0) or not batch:
            return items
        page += 1


_runs = {}


def get_run(run_id):
    """Fetched once per run: completion status (so partial in-flight runs are
    skipped) and the commit title to label the build."""
    if run_id not in _runs:
        try:
            d = fetch_json(f"{API}/runs/{run_id}")
        except Exception:
            d = {}
        title = d.get("display_title") or (d.get("head_commit") or {}).get("message", "")
        _runs[run_id] = {
            "done": d.get("status") == "completed",
            "title": title.split("\n")[0],
            "created_at": d.get("created_at", ""),
        }
    return _runs[run_id]


def is_build(a):
    name = a["name"].lower()
    if a["expired"] or a["size_in_bytes"] == 0:
        return False
    return not (name.endswith(".dockerbuild") or "build-log" in name)


def human_size(n):
    mb = n / (1024 * 1024)
    return f"{mb:.1f} MB" if mb < 1024 else f"{mb / 1024:.1f} GB"


def age(created):
    dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
    days = (datetime.now(timezone.utc) - dt).days
    return "today" if days == 0 else f"{days}d ago"


def short_name(name):
    """Drop the trailing -<short sha> tag (the build sha is shown on the header)."""
    return re.sub(r"-[0-9a-f]{7,40}$", "", name)


def main():
    # group surviving artifacts into builds keyed by workflow run
    builds = {}
    for a in fetch_artifacts():
        if not is_build(a):
            continue
        run = a["workflow_run"]
        rid = run["id"]
        if not get_run(rid)["done"]:
            continue
        b = builds.setdefault(rid, {
            "branch": run["head_branch"] or "?",
            "sha": run["head_sha"],
            "fork": run["head_repository_id"] != run["repository_id"],
            "title": get_run(rid)["title"],
            "created_at": get_run(rid)["created_at"] or a["created_at"],
            "arts": [],
        })
        b["arts"].append(a)

    branches = {}
    for rid, b in builds.items():
        branches.setdefault(b["branch"], []).append((rid, b))

    order = sorted(branches, key=lambda x: (x != "main", x.lower()))
    art_count = sum(len(b["arts"]) for b in builds.values())

    sections = []
    for branch in order:
        sections.append(f"<h2>{html.escape(branch)}</h2>")
        for rid, b in sorted(branches[branch],
                             key=lambda x: x[1]["created_at"], reverse=True):
            sha = b["sha"][:7]
            commit = f'https://github.com/{REPO}/commit/{b["sha"]}'
            fork = (' · <span class="fork">fork PR · unreviewed</span>'
                    if b["fork"] else "")
            rows = []
            for a in sorted(b["arts"], key=lambda a: a["name"]):
                link = f'https://nightly.link/{REPO}/actions/runs/{rid}/{a["name"]}.zip'
                label = html.escape(short_name(a["name"]))
                rows.append(f'<tr><td>{label}</td>'
                            f'<td class="sz">{human_size(a["size_in_bytes"])}</td>'
                            f'<td><a class="dl" href="{link}">download</a></td></tr>')
            sections.append(
                '<div class="build">'
                f'<div class="title">{html.escape(b["title"] or sha)}</div>'
                f'<div class="sub"><a href="{commit}"><code>{sha}</code></a>'
                f' · {age(b["created_at"])}{fork}</div>'
                f'<table class="arts">{"".join(rows)}</table></div>')

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    doc = (TEMPLATE
           .replace("{repo}", REPO)
           .replace("{builds}", str(len(builds)))
           .replace("{count}", str(art_count))
           .replace("{now}", now)
           .replace("{body}", "\n".join(sections)))

    os.makedirs(os.path.dirname(OUTPUT) or ".", exist_ok=True)
    with open(OUTPUT, "w") as f:
        f.write(doc)
    print(f"wrote {OUTPUT}: {len(builds)} builds, {art_count} artifacts, "
          f"{len(branches)} branches")


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{repo} — CI builds</title>
<style>
  body { font: 15px/1.5 system-ui, sans-serif; max-width: 960px; margin: 2rem auto; padding: 0 1rem; color: #1c1e21; }
  h1 { margin-bottom: .2rem; }
  .note { background: #fff8e1; border: 1px solid #f0d98a; padding: .6rem .8rem; border-radius: 6px; font-size: 14px; }
  .help { margin: .6rem 0 0; }
  .help a { font-weight: 600; }
  .meta { color: #666; font-size: 13px; margin: .3rem 0 1.5rem; }
  h2 { margin: 2rem 0 .6rem; border-bottom: 1px solid #eee; padding-bottom: .3rem; }
  .build { margin: 0 0 1.4rem; }
  .build .title { font-weight: 600; }
  .build .sub { color: #666; font-size: 13px; margin-top: .1rem; }
  .arts { border-collapse: collapse; margin-top: .5rem; font-size: 13px; }
  .arts td { padding: .2rem 1.2rem .2rem 0; border-bottom: 1px solid #f3f3f3; white-space: nowrap; }
  .arts td.sz { color: #888; text-align: right; padding-right: 1.6rem; }
  code { background: #f3f3f3; padding: 1px 4px; border-radius: 3px; }
  a { color: #0969da; text-decoration: none; }
  a:hover { text-decoration: underline; }
  .dl { font-weight: 600; }
  .fork { color: #9a6700; font-weight: 600; }
  dialog { max-width: 640px; border: 1px solid #ddd; border-radius: 10px; padding: 1.4rem 1.6rem; color: #1c1e21; }
  dialog::backdrop { background: rgba(0,0,0,.45); }
  dialog h2 { margin: 0 0 .4rem; border: 0; padding: 0; }
  dialog h3 { margin: 1.1rem 0 .2rem; font-size: 15px; }
  dialog ul, dialog ol { margin: .3rem 0; padding-left: 1.2rem; }
  .close { margin-top: 1.3rem; font: inherit; padding: .4rem 1rem; border: 1px solid #ccc; border-radius: 6px; background: #f6f8fa; cursor: pointer; }
</style>
</head>
<body>
<h1>{repo} — CI builds</h1>
<p class="note"><strong>Unofficial work-in-progress builds, straight from CI.</strong>
No warranty. Builds tagged <em>fork PR</em> are compiled from unreviewed contributor code — run at your own risk.
Links are served by <a href="https://nightly.link">nightly.link</a>; artifacts expire and disappear automatically.</p>
<p class="help"><a href="#" id="help-open">❓ What are these files? · Which one do I need? · How to use?</a></p>
<p class="meta">{builds} builds · {count} artifacts · generated {now}</p>
{body}

<dialog id="help">
  <h2>Using these builds</h2>

  <h3>What are these files?</h3>
  <p>Automatic, unofficial builds of the game, produced by CI on every change. They all run from the Steam demo folder, which works as a dev sandbox: it ships the minimal assets the engine needs to run fully — including features the demo executable normally disables. Each build groups a few downloads:</p>
  <ul>
    <li><strong>Game</strong> — the full executable: mission editor, mods and multiplayer included (these are off in the demo build).</li>
    <li><strong>GameDemo</strong> — the cut-down demo executable.</li>
    <li><strong>Server</strong> — the dedicated server, only needed to host.</li>
    <li><strong>Symbols</strong> — debug symbols for crash diagnosis, not needed to play.</li>
  </ul>
  <p><code>Linux-x64-*</code> are for Linux, <code>Windows-x64-*</code> for Windows. Every download is a <code>.zip</code>.</p>

  <h3>Which one do I need?</h3>
  <p>Pick by your platform, then:</p>
  <ul>
    <li>Full features (editor, mods, multiplayer) → <strong>Game</strong></li>
    <li>Plain demo → <strong>GameDemo</strong></li>
  </ul>
  <p>Use a build under <strong>main</strong> for the latest stable WIP, or a branch / PR build to test that specific change. You don't need <em>Server</em> or <em>Symbols</em> to play.</p>

  <h3>How do I use it? (the Steam demo folder is the sandbox)</h3>
  <ol>
    <li>In Steam, open the demo install folder: right-click the game → <em>Manage → Browse local files</em>.</li>
    <li><strong>Back up first</strong> — copy the files you are about to overwrite (or the whole folder) somewhere safe.</li>
    <li>Extract the downloaded <code>.zip</code> and copy its files into that folder, overwriting when asked.</li>
    <li>Launch the executable you grabbed — <code>PoseidonGame</code> or <code>PoseidonGameDemo</code> (<code>.exe</code> on Windows).</li>
    <li>To revert, delete the new files and restore your backup.</li>
  </ol>

  <form method="dialog"><button class="close">Close</button></form>
</dialog>

<script>
  const dlg = document.getElementById("help");
  document.getElementById("help-open").addEventListener("click", function (e) { e.preventDefault(); dlg.showModal(); });
  dlg.addEventListener("click", function (e) { if (e.target === dlg) dlg.close(); });
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
