"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item
from lab9.graders import GRADERS


def _is_non_finite(val: object) -> bool:
    return isinstance(val, float) and (math.isnan(val) or math.isinf(val))


def _check_ratchet(spec: dict, base_spec: dict) -> list[str]:
    """Kiểm tra quy tắc ratchet trên cùng eval_set_version: chỉ được giữ nguyên hoặc siết chặt hơn."""
    if spec.get("eval_set_version") != base_spec.get("eval_set_version"):
        return []
    problems: list[str] = []

    # 1. Ratchet cho spec["metrics"]
    pr_metrics = {m["id"]: m for m in (spec.get("metrics") or [])}
    for bm in base_spec.get("metrics") or []:
        mid = bm["id"]
        if mid not in pr_metrics:
            problems.append(f"ratchet: metric {mid} removed")
            continue
        pm = pr_metrics[mid]
        if bm.get("blocking") and not pm.get("blocking"):
            problems.append(f"ratchet: metric {mid} changed from blocking to non-blocking")
        bth = bm.get("threshold") or {}
        pth = pm.get("threshold") or {}
        if "min" in bth and ("min" not in pth or pth["min"] < bth["min"]):
            problems.append(f"ratchet: metric {mid} min loosened ({bth['min']} -> {pth.get('min')})")
        if "max" in bth and ("max" not in pth or pth["max"] > bth["max"]):
            problems.append(f"ratchet: metric {mid} max loosened ({bth['max']} -> {pth.get('max')})")
        if "max_increase" in bth and (
            "max_increase" not in pth or pth["max_increase"] > bth["max_increase"]
        ):
            problems.append(
                f"ratchet: metric {mid} max_increase loosened ({bth['max_increase']} -> {pth.get('max_increase')})"
            )
        if bth.get("no_significant_drop") and not pth.get("no_significant_drop"):
            problems.append(f"ratchet: metric {mid} dropped no_significant_drop")

    # 2. Ratchet cho spec["slices"]
    pr_slices = {(s["name"], s["metric"]): s for s in (spec.get("slices") or [])}
    for bs in base_spec.get("slices") or []:
        skey = (bs["name"], bs["metric"])
        sid = f"{bs['name']}/{bs['metric']}"
        if skey not in pr_slices:
            problems.append(f"ratchet: slice {sid} removed")
            continue
        ps = pr_slices[skey]
        if bs.get("blocking") and not ps.get("blocking"):
            problems.append(f"ratchet: slice {sid} changed from blocking to non-blocking")
        if "min" in bs and ("min" not in ps or ps["min"] < bs["min"]):
            problems.append(f"ratchet: slice {sid} min loosened ({bs['min']} -> {ps.get('min')})")
        if "max" in bs and ("max" not in ps or ps["max"] > bs["max"]):
            problems.append(f"ratchet: slice {sid} max loosened ({bs['max']} -> {ps.get('max')})")
        if bs.get("no_significant_drop") and not ps.get("no_significant_drop"):
            problems.append(f"ratchet: slice {sid} dropped no_significant_drop")

    return problems


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems: list[str] = []

    # 1. Cấm mọi giá trị NaN / inf trong pr["metrics"]
    pr_metrics = pr.get("metrics") or {}
    for k, v in pr_metrics.items():
        if _is_non_finite(v):
            problems.append(f"metric {k} is non-finite ({v})")

    # 2. Cấm report có evaluator_failures (kể cả khi điểm trung bình vẫn đạt)
    failures = pr.get("evaluator_failures") or []
    if failures:
        problems.append(f"evaluator_failures non-empty ({len(failures)}): {failures[0]}")

    # 3. Kiểm tra số dòng, trùng lặp (item_id, seed) và đối khớp tập (item_id, seed) với baseline
    rows = pr.get("rows") or []
    base_rows = base.get("rows") or []
    manifest = pr.get("manifest") or {}
    expected_n = int(manifest.get("items") or 0) * len(manifest.get("seeds") or [])
    if len(rows) != expected_n:
        problems.append(f"row count {len(rows)} != manifest {expected_n} (dropped or extra rows)")

    pr_pairs = [(r.get("item_id"), r.get("seed")) for r in rows]
    if len(pr_pairs) != len(set(pr_pairs)):
        problems.append("duplicate (item_id, seed) rows detected in PR")

    base_pairs = {(r.get("item_id"), r.get("seed")) for r in base_rows}
    if set(pr_pairs) != base_pairs:
        problems.append("(item_id, seed) set of PR differs from baseline (cherry-picked items/seeds)")

    # 4. Kiểm tra các metric chấm theo dòng không bị thiếu, None hoặc NaN/inf
    base_row_keys = set(base_rows[0].keys()) if base_rows else set()
    graded_ids = [
        m["id"]
        for m in (spec.get("metrics") or [])
        if m["id"] in GRADERS or m["id"] in base_row_keys
    ]
    missing_cells: list[str] = []
    for r in rows:
        tag = f"{r.get('item_id')}@{r.get('seed')}"
        for mid in graded_ids:
            val = r.get(mid)
            if mid not in r or val is None or _is_non_finite(val):
                missing_cells.append(f"{tag}:{mid}={val!r}")
    if missing_cells:
        problems.append(
            f"{len(missing_cells)} missing/None/non-finite graded cell(s), first: {missing_cells[0]}"
        )

    # 5. Kiểm tra nhãn slices từng dòng không bị sửa so với baseline
    base_slices = {
        (r.get("item_id"), r.get("seed")): sorted(r.get("slices") or [])
        for r in base_rows
    }
    tampered_slices: list[str] = []
    for r in rows:
        key = (r.get("item_id"), r.get("seed"))
        if key in base_slices and sorted(r.get("slices") or []) != base_slices[key]:
            tampered_slices.append(f"{key[0]}@{key[1]}")
    if tampered_slices:
        problems.append(
            f"slice tags differ from baseline on {len(tampered_slices)} row(s), first: {tampered_slices[0]}"
        )

    # 6. Đối chiếu giá trị tổng hợp trong pr["metrics"] khớp với dữ liệu thực trong pr["rows"]
    if rows and not missing_cells:
        for mid in graded_ids:
            if mid not in pr_metrics or pr_metrics[mid] is None or _is_non_finite(pr_metrics[mid]):
                continue
            vals = [bool(r[mid]) for r in rows]
            expected_val = sum(vals) if mid in ("secret_leak", "approval_bypass") else round(sum(vals) / len(vals), 4)
            if isinstance(pr_metrics[mid], (int, float)) and abs(pr_metrics[mid] - expected_val) > 1e-4:
                problems.append(
                    f"summary metric {mid}={pr_metrics[mid]} disagrees with rows ({expected_val})"
                )

    # 7. Kiểm tra quy tắc ratchet khi có base_spec
    if base_spec is not None:
        problems.extend(_check_ratchet(spec, base_spec))

    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked: list[str] = []
    lines: list[str] = []
    bs = spec.get("bootstrap", {})
    for s in spec.get("slices") or []:
        name, metric = s["name"], s["metric"]
        sid = f"slice:{name}/{metric}"
        # Tính điểm trung bình theo từng item chỉ trên các dòng thuộc slice này
        a = per_item(pr, metric, slice_name=name)
        val = round(sum(a.values()) / len(a), 4) if a else None
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        else:
            if "min" in s and val < s["min"]:
                verdict = "fail"
            if "max" in s and val > s["max"]:
                verdict = "fail"
            # Nếu bật no_significant_drop: chạy paired bootstrap riêng trên tập item của slice
            if s.get("no_significant_drop"):
                b = per_item(base, metric, slice_name=name)
                keys = sorted(set(a) & set(b))
                if not keys:
                    verdict = "missing"
                else:
                    d, lo, hi = stats.paired_bootstrap(
                        [a[k] for k in keys],
                        [b[k] for k in keys],
                        n_resamples=bs.get("n_resamples", 1000),
                        rng=bs.get("rng", 2027),
                        confidence=bs.get("confidence", 0.95),
                    )
                    note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                    if hi < 0:
                        verdict = "fail"
        if verdict != "ok" and s.get("blocking"):
            blocked.append(sid)
        th = {k: s[k] for k in ("min", "max", "no_significant_drop") if k in s}
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if s.get("blocking") else "warn")
        lines.append(f"  {sid:<28} {val!s:<8} {json.dumps(th):<34} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
