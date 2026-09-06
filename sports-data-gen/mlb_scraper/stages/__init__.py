"""The three pipeline stages, one module each.

Each reads what the previous one wrote and nothing else, so each can be run,
re-run and forced independently:

    extract    the website -> cache/     (slow, networked, rate-limited)
    transform  cache/      -> data/      (offline, cheap, safe to redo)
    load       data/       -> a bucket   (networked, overwrites on --force)

A date can legitimately sit in any combination of those states; status.json
tracks each stage separately.
"""
