# HybridCut restart — person-restore → matte-visible

**Current stamp:** [`2026-10-11-matte-visible`](./matte-visible-restart.md) (use that doc).

## person-restore (kept)

Varázsceruza / paint-face wrote face-only masks into **MaskStore**. Megnyitás stayed on Gyors, reloaded scraps, skipped RVM → empty cover → source-only UI.

Restore: `MaskStore.purge()` on open · Max + Éles · Delete/Backspace clip delete · no Varázsceruza / Ecset / Radír / Lasszó.

## matte-visible (why screenshots still failed)

After person-restore, Maszk could still be a **solid light-gray rectangle** and Cutout the **opaque full frame** when alpha was an **all-ones / near-uniform slab** (0–255 clip, wrong pha tensor, or flat cache). That looked “ready” (Cutout ✓) while people were not cut out — and the chip could still say **Gyors** if the Max-on-open tree was never synced.

See **matte-visible-restart.md** for pull/sync/checklist and smoke tests.
