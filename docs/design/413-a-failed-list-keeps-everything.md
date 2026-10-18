# 413 - A library list that failed to load deletes nothing

## Problem

The web lost its papers twice. On 10/17 15:10:55 a web tab opened while the paper
list call timed out. `refresh` left `papers` empty, and its `finally` still ran
`sweepLocalResidues`, which keeps only folders named in `papers`. Keep was empty, so it
purged all three indexed papers (`paper_residue_sweep deleted_n=6 keep_n=0`, three
`library_index_upsert op=remove caller=purge`). On 10/19 the web opened with an empty
index and showed nothing.

The phone runs the same code. A cold launch whose list call fails would have purged the
only copy of every paper, since the phone owns them (design/185).

The same `finally` also ran `_editStash.purgeOrphans` against the empty list.

## Change

- `refresh` sets `listed` once the merged list is published. The residue sweep and the
  edit stash purge run only then.
- `sweepLocalResidues` also keeps every disk index entry that has a session, with its
  mate. Such a paper is the device's own whatever the list says. A delete purges the
  paper by name before it sweeps, so deleting still works.
- `paper_residue_sweep` reports `indexed_n`.
- The hidden sample row (design/364) was seeded and swept on every launch, because the
  list filters it out. It now stays on disk, still hidden. Near sync leaves it out.

## What it does not do

Papers the 10/17 sweep deleted are gone from the browser. The phone still has them;
syncing again copies them back.

## Tests

`mobile/test/web_no_local_disk_test.dart`: `design/413 a list that failed to load
deletes nothing`. It fails without the change.
