"""Tracker read/write for Job Scanner.

🔴 CLAUDE.md non-negotiable: TRACKER WRITES USE A PROGRAM, NEVER AN IN-PLACE SHELL EDIT.
seen_jobs.json is ~730 KB. The standing method is json.load -> mutate -> json.dump with a
pre-write .bak-{timestamp} copy and post-write re-parse plus count assertions. No sed, no
heredoc, ever. This file is the prompt-injection payload's actual target.

The backup is NOT a stand-in for version control. private/ is gitignored, so the trackers
are in no repo, before or after a git init -- but that is not why the copy exists either.
os.replace already makes the write atomic, so a crash cannot corrupt the tracker. The copy
exists because the ASSERTIONS BELOW FIRE AFTER THE REPLACE: when one raises, the wrong file
is already on disk and the .bak is the only copy of the pre-write state. One per write
(a same-day re-run must not reuse r1's), KEEP_BACKUPS most recent kept.

Encoding is not optional. Both trackers are literal UTF-8; a bare open() defaults to
cp1252 and raises on ~64 stored titles. Always pass encoding="utf-8" on read AND write,
and keep writing with ensure_ascii=False.

⚠️ seen_jobs.json's `jobs` map holds TWO LEGACY STRING VALUES (_comment_r4 at line 3148,
_comment_2026-08-07 at line 3557). Every consumer must type-guard with isinstance(v, dict)
or .get() raises AttributeError. They are preserved on write, not cleaned up.
"""

import datetime
import glob
import json
import os
import shutil

# How many pre-write copies to keep per tracker. Three covers "the run that just went
# wrong, and the two before it" -- ~2.2 MB for seen_jobs.json, against unbounded growth:
# the previous code pruned nothing, so copies sat in private/ until cleared by hand.
KEEP_BACKUPS = 3

# Anchored to THIS FILE, not the working directory: bin/../private. A dispatch group that
# chdir'd would break a cwd-relative path, and a hardcoded absolute one breaks the moment
# the project is moved -- which is exactly what happened before this was fixed.
# Kept as str, not pathlib.Path: save() does `path + ".tmp"` and .format() on them.
#
# 🔴 The trackers live in private/ and are GITIGNORED. They are per-operator state, not
# project data: a fresh clone starts with no tracker and builds one on its first scan.
# Shipping a populated tracker would suppress every posting the previous owner had seen.
_PRIVATE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "private")

SEEN_JOBS = os.path.join(_PRIVATE, "seen_jobs.json")
INDEED_SEEN = os.path.join(_PRIVATE, "indeed_seen.json")


def load(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def job_entries(data):
    """Only the real dict-valued entries, legacy strings filtered out."""
    return {k: v for k, v in data.get("jobs", {}).items() if isinstance(v, dict)}


def count(data):
    return len(job_entries(data))


def add(data, url, company, title, location, date_found=None, status=None, note=None):
    """Add one posting. Returns True if added, False if the key was already present.

    `status` is "borderline" or None. Absence of status IS core -- there is no "core"
    value, and that convention is relied on by every existing entry.
    """
    jobs = data.setdefault("jobs", {})
    if url in jobs:
        return False
    entry = {
        "company": company,
        "title": title,
        "location": location,
        "dateFound": date_found or datetime.date.today().isoformat(),
    }
    if status:
        entry["status"] = status
    if note:
        entry["note"] = note
    jobs[url] = entry
    return True


def _backup_path(path, stamp):
    """Next {path}.bak-{stamp} name, suffixed if that second already has one.

    Two writes inside the same second must not share a copy -- that is the same-day
    collapse this replaces, one order of magnitude finer.

    🔴 Allocation is HIGHEST-SEEN + 1, never first-free. First-free reused a name that
    _prune() had just freed, and since prune orders by name, the reused low name was
    immediately the oldest -- so the copy protecting the newest write was the one deleted.
    Suffixes are zero-padded so -02 through -99 sort against each other correctly, and the
    bare stamp sorts first as the second's earliest.
    """
    base = "{0}.bak-{1}".format(path, stamp)
    existing = glob.glob(glob.escape(base) + "*")
    if not existing:
        return base
    highest = 1
    for name in existing:
        tail = name[len(base):]
        if tail.startswith("-") and tail[1:].isdigit():
            highest = max(highest, int(tail[1:]))
    return "{0}-{1:02d}".format(base, highest + 1)


def _prune(path, keep=KEEP_BACKUPS):
    """Drop all but the `keep` newest backups. Returns what was removed.

    🔴 Callers must run this only AFTER the post-write assertions pass. Deleting a
    recovery point before the write it protects has been verified defeats the purpose.
    """
    found = sorted(glob.glob(glob.escape(path) + ".bak-*"))
    removed = []
    for old in found[:-keep] if keep > 0 else found:
        os.remove(old)
        removed.append(old)
    return removed


def save(path, data, expected_added=None, date_stamp=None):
    """Write with a pre-write backup and post-write assertions.

    `expected_added` is the number of entries this run believes it added. If given, the
    post-write count is asserted against it. A mismatch raises rather than reporting a
    number nobody checked.

    `date_stamp` overrides the backup's timestamp; the default is per-write, not per-day.
    """
    stamp = date_stamp or datetime.datetime.now().strftime("%Y-%m-%dT%H%M%S")

    # A fresh clone has no private/ -- it is gitignored, so it does not survive a clone.
    # Without this the first scan dies at open(tmp, "w") with FileNotFoundError.
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)

    before = None
    backup = None
    if os.path.exists(path):
        before = count(load(path))
        backup = _backup_path(path, stamp)
        shutil.copy2(path, backup)

    after_intended = count(data)

    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False)
    os.replace(tmp, path)

    # Post-write: re-parse from disk. Never trust the in-memory object.
    #
    # Both raises below happen AFTER os.replace, so the bad file is already live. Name the
    # backup in the message -- it is the pre-write state, and whoever reads the traceback
    # is the one who has to restore it.
    recovery = "" if backup is None else "; pre-write copy at {0}".format(backup)
    reread = load(path)
    actual = count(reread)
    if actual != after_intended:
        raise AssertionError(
            "tracker write mismatch: in-memory {0} entries, on-disk {1}{2}".format(
                after_intended, actual, recovery))
    if before is not None and expected_added is not None:
        if actual - before != expected_added:
            raise AssertionError(
                "tracker delta mismatch: {0} -> {1} is {2}, expected +{3}{4}".format(
                    before, actual, actual - before, expected_added, recovery))

    # Assertions passed: this write is verified, so older recovery points can go.
    pruned = _prune(path)
    return {"before": before, "after": actual,
            "added": None if before is None else actual - before,
            "backup": backup, "pruned": pruned}
