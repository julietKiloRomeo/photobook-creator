"""Job handlers — what the background worker actually runs."""

from __future__ import annotations

import logging
from datetime import datetime

from shoebox.config import get_settings
from shoebox.jobs import JobReporter
from shoebox.pipeline.tier2 import ProposedTheme, cluster_stacks, propose_themes
from shoebox.store import connection, dao

log = logging.getLogger(__name__)


def _theme_base_name(proposal: ProposedTheme) -> str:
    """Name a proposal after the day it happened.

    Date names beat ``Day 1``/``Day 2``: they do not renumber every time
    a photo lands in an earlier gap, so a name the owner is looking at
    keeps meaning the same thing across runs.
    """
    started: datetime | None = proposal.started_at
    if started is None:
        return "Undated photos"
    return f"{started:%b} {started.day}, {started.year}"


def _free_name(base: str, taken: set[str]) -> str:
    name = base
    suffix = 2
    while name in taken:
        name = f"{base} ({suffix})"
        suffix += 1
    return name


def process_project(project_id: str, reporter: JobReporter) -> None:
    """Recompute stacks and themes for a project from current references.

    Two invariants make this safe to re-run after every upload:

    1. Stack identity survives (``dao.sync_stacks``), so theme
       assignments and best-shot picks are not cascaded away.
    2. Theme proposal is *additive*: a stack that already belongs to a
       theme is never touched. Only stacks nothing owns get grouped into
       fresh proposals.
    """
    settings = get_settings()
    reporter.progress(0.05, "Loading references")

    with connection() as conn:
        references = dao.list_references(conn, project_id)

    if not references:
        log.info("Project %s has no references to process", project_id)
        reporter.progress(1.0, "No photos to process")
        return

    reporter.progress(0.2, "Clustering stacks")
    groups = cluster_stacks(
        references,
        burst_max_seconds=settings.burst_max_seconds,
        max_location_gap_meters=settings.max_location_gap_meters,
    )

    reporter.progress(0.5, "Saving stacks")
    with connection() as conn:
        stacks = dao.sync_stacks(conn, project_id, groups)

    reporter.progress(0.7, "Proposing themes")
    with connection() as conn:
        ref_by_id = {r["id"]: r for r in dao.list_references(conn, project_id)}
        enriched = []
        for stack in stacks:
            full = dao.get_stack(conn, stack["id"])
            assert full is not None
            full["references"] = [ref_by_id[rid] for rid in full["reference_ids"]]
            enriched.append(full)

        # Anything the owner (or a previous run) already filed stays put.
        assigned = dao.list_assigned_stack_ids(conn, project_id)
        unassigned = [s for s in enriched if s["id"] not in assigned]

        # Retire AI proposals that ended up empty; they carry no meaning
        # and would otherwise pile up as clutter.
        for theme in dao.list_themes(conn, project_id):
            if theme["ai_proposed"] and not dao.list_stack_ids_for_theme(conn, theme["id"]):
                dao.delete_theme(conn, theme["id"])

        # A surviving AI theme for the same day absorbs the new stacks
        # rather than spawning "Aug 9, 2026 (2)" beside it — but only one
        # proposal each, since two proposals mean the pipeline saw two
        # distinct themes (a day spent in two places) and that decision
        # stands. Owner-named themes are off limits, so their names are
        # merely reserved. ``reserved`` holds every name now in use: a
        # name a theme took this run is never handed out again, whether
        # that theme was absorbed or freshly created.
        remaining = dao.list_themes(conn, project_id)
        mergeable = {t["name"]: t["id"] for t in remaining if t["ai_proposed"]}
        reserved = {t["name"] for t in remaining if not t["ai_proposed"]}

        proposals = propose_themes(
            unassigned,
            theme_partition_hours=settings.theme_partition_hours,
            max_location_gap_meters=settings.max_location_gap_meters,
        )

        for proposal in proposals:
            base = _theme_base_name(proposal)
            theme_id = mergeable.pop(base, None)
            if theme_id is None:
                name = _free_name(base, reserved | set(mergeable))
                theme_id = dao.create_theme(
                    conn,
                    project_id=project_id,
                    name=name,
                    ai_proposed=True,
                )["id"]
            else:
                name = base
            reserved.add(name)
            for stack_id in proposal.stack_ids:
                dao.assign_stack_to_theme(
                    conn,
                    stack_id=stack_id,
                    theme_id=theme_id,
                    adopt=False,
                )

    log.info(
        "Processed project %s: %d references, %d stacks, %d new theme(s) for %d "
        "unassigned stack(s)",
        project_id,
        len(references),
        len(stacks),
        len(proposals),
        len(unassigned),
    )
    reporter.progress(1.0, "Done")
