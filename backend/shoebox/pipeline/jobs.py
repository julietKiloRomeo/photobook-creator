"""Job handlers — what the background worker actually runs."""

from __future__ import annotations

from shoebox.config import get_settings
from shoebox.jobs import JobReporter
from shoebox.pipeline.tier2 import cluster_stacks, propose_themes
from shoebox.store import connection, dao


def process_project(project_id: str, reporter: JobReporter) -> None:
    """Recompute stacks and themes for a project from current references.

    This is intentionally idempotent: replays produce the same shape
    (modulo new uploads in between).
    """
    settings = get_settings()
    reporter.progress(0.05, "Loading references")

    with connection() as conn:
        references = dao.list_references(conn, project_id)

    if not references:
        reporter.progress(1.0, "No photos to process")
        return

    reporter.progress(0.2, "Clustering stacks")
    groups = cluster_stacks(
        references,
        burst_max_seconds=settings.burst_max_seconds,
    )

    reporter.progress(0.5, "Saving stacks")
    with connection() as conn:
        stacks = dao.replace_stacks(conn, project_id, groups)

    reporter.progress(0.7, "Proposing themes")
    # Re-fetch stacks with reference lists for the theme proposer.
    with connection() as conn:
        ref_by_id = {r["id"]: r for r in dao.list_references(conn, project_id)}
        enriched = []
        for stack in stacks:
            full = dao.get_stack(conn, stack["id"])
            assert full is not None
            full["references"] = [ref_by_id[rid] for rid in full["reference_ids"]]
            enriched.append(full)

        # Only re-propose for stacks that are not already assigned to a
        # surviving (user-owned) theme. See B-1 in step-2 manual findings.
        existing = dao.list_themes(conn, project_id)
        surviving_user_themes = [t for t in existing if not t["ai_proposed"]]
        claimed_stack_ids: set[str] = set()
        for theme in surviving_user_themes:
            claimed_stack_ids.update(dao.list_stack_ids_for_theme(conn, theme["id"]))

        unclaimed = [s for s in enriched if s["id"] not in claimed_stack_ids]
        proposals = propose_themes(
            unclaimed,
            theme_partition_hours=settings.theme_partition_hours,
        )

        # Drop only AI-proposed themes the user has not adopted.
        for theme in existing:
            if theme["ai_proposed"]:
                conn.execute("DELETE FROM themes WHERE id = ?", (theme["id"],))

        for proposal in proposals:
            theme = dao.create_theme(
                conn,
                project_id=project_id,
                name=proposal.name,
                ai_proposed=True,
            )
            for stack_id in proposal.stack_ids:
                dao.assign_stack_to_theme(conn, stack_id=stack_id, theme_id=theme["id"])

    reporter.progress(1.0, "Done")
