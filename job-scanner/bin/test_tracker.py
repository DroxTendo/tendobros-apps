"""Tests for the Job Scanner tracker read/write module.

Run:
  .venv\\Scripts\\python.exe bin\\run_tests.py        (from the project root)

Every guard in jobscan_tracker.save() was added after a real incident -- the companies.md
166 KB -> 13 KB truncation, the Marsh silent dedup death, the cp1252 encode failures. This
file is what stops a refactor from quietly removing one. When a tracker write goes wrong,
add the check HERE first, then fix the module.

🔴 EVERY TEST RUNS IN A TEMP DIRECTORY. The real trackers are 733 KB of durable,
un-versioned record; a test suite must never be able to touch them. check_real_trackers_
untouched() asserts that at the end of the run.
"""

import datetime
import glob
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import jobscan_tracker as T

# An en-dash, the character class that raises UnicodeEncodeError under cp1252. Written as
# an escape so this source file stays pure ASCII, like the modules it tests.
EN_DASH_TITLE = "Senior Data Engineer – Remote"


class Recorder(object):
    """Collects pass/fail. Mirrors test_jobscan.py's failure-list style, counted."""

    def __init__(self):
        self.total = 0
        self.failures = []

    def ok(self, label, cond, detail=""):
        self.total += 1
        if not cond:
            self.failures.append(label + (" -- " + detail if detail else ""))


def baks(path):
    return sorted(glob.glob(glob.escape(path) + ".bak-*"))


def seeded(*urls):
    data = {"jobs": {}}
    for u in urls:
        T.add(data, u, "Acme", "Data Engineer", "Chicago, IL")
    return data


# ---------------------------------------------------------------------------------------
# Path resolution -- the 🔵 non-negotiable that tracker paths are never hardcoded
# ---------------------------------------------------------------------------------------

def check_paths_resolve_from_the_module(r):
    for name, path in (("SEEN_JOBS", T.SEEN_JOBS), ("INDEED_SEEN", T.INDEED_SEEN)):
        r.ok(name + " is absolute", os.path.isabs(path), path)
        r.ok(name + " lives in private/",
             os.path.basename(os.path.dirname(path)) == "private", path)

    # The point of anchoring to __file__: a dispatch group that chdir'd must still resolve.
    cwd = os.getcwd()
    tmp = tempfile.mkdtemp(prefix="jstracker-cwd-")
    try:
        os.chdir(tmp)
        import importlib
        reloaded = importlib.reload(T)
        r.ok("SEEN_JOBS survives a chdir", reloaded.SEEN_JOBS == T.SEEN_JOBS,
             reloaded.SEEN_JOBS)
    finally:
        os.chdir(cwd)
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------------------
# load / job_entries / count
# ---------------------------------------------------------------------------------------

def check_utf8_round_trip(r, root):
    path = os.path.join(root, "utf8.json")
    data = {"jobs": {}}
    T.add(data, "https://x/1", "Acme", EN_DASH_TITLE, "Chicago, IL")
    T.save(path, data)

    reread = T.load(path)
    r.ok("en-dash title survives a save/load round trip",
         reread["jobs"]["https://x/1"]["title"] == EN_DASH_TITLE)

    raw = open(path, "rb").read()
    r.ok("written with ensure_ascii=False (real UTF-8 bytes, not an escape)",
         EN_DASH_TITLE.encode("utf-8") in raw and b"\\u2013" not in raw)


def check_legacy_string_values(r, root):
    """seen_jobs.json holds two legacy STRING values. They must not be counted, and must
    not be dropped -- every consumer type-guards, and save() preserves them."""
    path = os.path.join(root, "legacy.json")
    data = seeded("https://x/1", "https://x/2")
    data["jobs"]["_comment_r4"] = "a legacy string value, deliberately preserved"

    r.ok("count() excludes legacy string values", T.count(data) == 2, str(T.count(data)))
    r.ok("job_entries() excludes them too",
         set(T.job_entries(data)) == {"https://x/1", "https://x/2"})

    T.save(path, data)
    reread = T.load(path)
    r.ok("legacy string value survives the write",
         reread["jobs"].get("_comment_r4") == "a legacy string value, deliberately preserved")
    r.ok("count() still excludes it after the round trip", T.count(reread) == 2)


# ---------------------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------------------

def check_add(r):
    data = {"jobs": {}}
    first = T.add(data, "https://x/1", "Acme", "Data Engineer", "Chicago, IL")
    r.ok("add() returns True for a new key", first is True)

    again = T.add(data, "https://x/1", "OTHER", "OTHER TITLE", "OTHER PLACE")
    r.ok("add() returns False for a duplicate key", again is False)
    r.ok("a duplicate does NOT overwrite the stored entry",
         data["jobs"]["https://x/1"]["company"] == "Acme",
         data["jobs"]["https://x/1"]["company"])

    # 🔴 Absence of `status` IS core. There is no "core" value, and every stored entry
    # relies on that convention -- writing status="core" would break the dedup tiering.
    r.ok("status is omitted entirely when None", "status" not in data["jobs"]["https://x/1"])
    r.ok("note is omitted entirely when None", "note" not in data["jobs"]["https://x/1"])

    T.add(data, "https://x/2", "Acme", "Data Architect", "Remote",
          status="borderline", note="hands-on?")
    r.ok("status is stored when given", data["jobs"]["https://x/2"]["status"] == "borderline")
    r.ok("note is stored when given", data["jobs"]["https://x/2"]["note"] == "hands-on?")

    today = datetime.date.today().isoformat()
    r.ok("dateFound defaults to today", data["jobs"]["https://x/2"]["dateFound"] == today)

    T.add(data, "https://x/3", "Acme", "Data Engineer", "Remote", date_found="2026-01-02")
    r.ok("dateFound honours an explicit value",
         data["jobs"]["https://x/3"]["dateFound"] == "2026-01-02")


# ---------------------------------------------------------------------------------------
# save -- directory creation, backups, pruning
# ---------------------------------------------------------------------------------------

def check_fresh_clone_path(r, root):
    """private/ is gitignored and does not survive a clone. The first save must create it
    rather than dying at open(tmp, "w") with FileNotFoundError."""
    path = os.path.join(root, "does", "not", "exist", "seen_jobs.json")
    res = T.save(path, seeded("https://x/1"))
    r.ok("first save creates the missing parent directory", os.path.exists(path))
    r.ok("no backup on a first write -- there is nothing to back up",
         res["backup"] is None and baks(path) == [])
    r.ok("return dict reports before=None on a first write", res["before"] is None)
    r.ok("return dict reports added=None on a first write", res["added"] is None)


def check_backup_per_write(r, root):
    path = os.path.join(root, "perwrite.json")
    data = seeded("https://x/1")
    T.save(path, data)

    made = []
    for i in range(2, 5):
        T.add(data, "https://x/%d" % i, "Acme", "Data Engineer", "Chicago, IL")
        res = T.save(path, data, expected_added=1)
        made.append(res["backup"])

    r.ok("every write after the first makes its own backup",
         len(set(made)) == 3 and all(made), str([os.path.basename(b or "") for b in made]))
    r.ok("same-second writes do not share a copy",
         len(set(os.path.basename(b) for b in made)) == 3)
    r.ok("the return dict names the backup it made", os.path.exists(made[-1]))


def check_newest_backup_is_never_the_pruned_one(r, root):
    """🔴 The first-free defect: prune frees a low name, the next write reuses it, and
    prune -- ordering by name -- then deletes the copy protecting the newest write."""
    path = os.path.join(root, "monotonic.json")
    data = seeded("https://x/1")
    T.save(path, data)

    for i in range(2, 14):
        T.add(data, "https://x/%d" % i, "Acme", "Data Engineer", "Chicago, IL")
        res = T.save(path, data, expected_added=1)
        if not os.path.exists(res["backup"]):
            r.ok("write %d kept its own backup" % i, False, res["backup"])
            return
    r.ok("across 12 writes, each backup outlives the write that made it", True)

    kept = baks(path)
    r.ok("prune holds the count at KEEP_BACKUPS", len(kept) == T.KEEP_BACKUPS, str(len(kept)))
    r.ok("the kept backups are the newest ones", kept == sorted(kept)[-T.KEEP_BACKUPS:])


def check_prune_directly(r, root):
    path = os.path.join(root, "prune.json")
    open(path, "w", encoding="utf-8").write('{"jobs": {}}')
    for name in (".bak-2026-01-01", ".bak-2026-01-02", ".bak-2026-01-03"):
        shutil.copy2(path, path + name)

    # Neighbours that must survive: a temp file, and another tracker's backup.
    tmpfile = path + ".tmp"
    sibling = os.path.join(root, "indeed_seen.json.bak-2026-01-01")
    open(tmpfile, "w", encoding="utf-8").write("x")
    open(sibling, "w", encoding="utf-8").write("x")

    removed = T._prune(path, keep=1)
    r.ok("_prune removes oldest-first",
         [os.path.basename(p) for p in removed]
         == ["prune.json.bak-2026-01-01", "prune.json.bak-2026-01-02"],
         str([os.path.basename(p) for p in removed]))
    r.ok("_prune keeps the newest", baks(path) == [path + ".bak-2026-01-03"])
    r.ok("_prune ignores the .tmp neighbour", os.path.exists(tmpfile))
    r.ok("_prune ignores another tracker's backups", os.path.exists(sibling))

    r.ok("_prune(keep=0) removes everything", T._prune(path, keep=0) and baks(path) == [])


# ---------------------------------------------------------------------------------------
# save -- the assertions, and what they leave behind
# ---------------------------------------------------------------------------------------

def check_delta_mismatch(r, root):
    path = os.path.join(root, "delta.json")
    data = seeded("https://x/1", "https://x/2")
    T.save(path, data)
    pre = open(path, "rb").read()
    before_baks = baks(path)

    T.add(data, "https://x/3", "Acme", "Data Engineer", "Chicago, IL")
    try:
        T.save(path, data, expected_added=7)  # the truth is +1
        r.ok("a delta mismatch raises", False, "no exception")
        return
    except AssertionError as exc:
        message = str(exc)

    r.ok("a delta mismatch raises", True)
    r.ok("the message names the pre-write copy", "pre-write copy at " in message, message)

    backup = message.split("pre-write copy at ", 1)[-1].strip()
    r.ok("the named copy exists", os.path.exists(backup), backup)
    r.ok("the named copy restores the pre-write file byte-for-byte",
         os.path.exists(backup) and open(backup, "rb").read() == pre)
    # This is the whole reason the copy exists: the assertions fire AFTER os.replace.
    r.ok("the bad write is already live on disk", open(path, "rb").read() != pre)
    r.ok("a failed write prunes nothing", len(baks(path)) == len(before_baks) + 1,
         str(len(baks(path))))


def check_write_mismatch(r, root):
    """The in-memory vs on-disk guard -- the one that caught the Marsh silent dedup death.
    Forced by making the post-write re-read disagree with what was serialised."""
    path = os.path.join(root, "mismatch.json")
    data = seeded("https://x/1", "https://x/2")
    T.save(path, data)

    real_load = T.load
    calls = []

    def lying_load(p):
        calls.append(p)
        result = real_load(p)
        if len(calls) > 1:  # the post-write re-read only
            result = {"jobs": {"https://x/1": result["jobs"]["https://x/1"]}}
        return result

    T.load = lying_load
    try:
        T.add(data, "https://x/3", "Acme", "Data Engineer", "Chicago, IL")
        T.save(path, data)
        r.ok("an in-memory/on-disk mismatch raises", False, "no exception")
    except AssertionError as exc:
        r.ok("an in-memory/on-disk mismatch raises", True)
        r.ok("the write-mismatch message names the pre-write copy too",
             "pre-write copy at " in str(exc), str(exc))
    finally:
        T.load = real_load


def check_return_contract(r, root):
    path = os.path.join(root, "contract.json")
    data = seeded("https://x/1")
    T.save(path, data)
    T.add(data, "https://x/2", "Acme", "Data Engineer", "Chicago, IL")
    res = T.save(path, data, expected_added=1)

    for key in ("before", "after", "added", "backup", "pruned"):
        r.ok("the return dict carries " + key, key in res, str(sorted(res)))
    r.ok("before/after/added agree",
         (res["before"], res["after"], res["added"]) == (1, 2, 1), str(res))
    r.ok("pruned is a list", isinstance(res["pruned"], list))


# ---------------------------------------------------------------------------------------

def check_real_trackers_untouched(r, fingerprints, pre_existing_baks):
    for path, before in fingerprints.items():
        after = os.path.exists(path) and (os.path.getsize(path), os.path.getmtime(path))
        r.ok("the real " + os.path.basename(path) + " was never written",
             after == before, "{0} -> {1}".format(before, after))
    # 🔴 A DELTA, never an absolute. This asserted `strays == []` until 2026-09-07, which
    # contradicted the module under test: KEEP_BACKUPS is 3, so up to three backups are
    # DESIGNED to sit in private/ after a real scan. The absolute form therefore failed on
    # every run following a tracker write -- not because the suite had touched anything (the
    # fingerprint checks above prove it had not), but because a legitimate backup existed.
    # It went unnoticed only because a sanitisation pass had left private/ with zero backups.
    # A check that cries wolf on healthy state is one nobody reads the next time it fires.
    strays = [b for b in baks(T.SEEN_JOBS) + baks(T.INDEED_SEEN)
              if b not in pre_existing_baks]
    r.ok("no NEW backup landed in private/", strays == [], str(strays))


def main():
    fingerprints = {}
    for path in (T.SEEN_JOBS, T.INDEED_SEEN):
        fingerprints[path] = (os.path.exists(path)
                              and (os.path.getsize(path), os.path.getmtime(path)))
    pre_existing_baks = set(baks(T.SEEN_JOBS) + baks(T.INDEED_SEEN))

    r = Recorder()
    root = tempfile.mkdtemp(prefix="jstracker-")
    try:
        check_paths_resolve_from_the_module(r)
        check_utf8_round_trip(r, root)
        check_legacy_string_values(r, root)
        check_add(r)
        check_fresh_clone_path(r, root)
        check_backup_per_write(r, root)
        check_newest_backup_is_never_the_pruned_one(r, root)
        check_prune_directly(r, root)
        check_delta_mismatch(r, root)
        check_write_mismatch(r, root)
        check_return_contract(r, root)
        check_real_trackers_untouched(r, fingerprints, pre_existing_baks)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    if r.failures:
        print("FAIL: {0} of {1} tracker checks".format(len(r.failures), r.total))
        for f in r.failures:
            print("  - " + f)
        return 1
    print("OK: {0} tracker checks passed".format(r.total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
