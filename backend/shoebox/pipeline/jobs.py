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

        proposals = propose_themes(
            enriched,
            theme_partition_hours=settings.theme_partition_hours,
        )

        # Replace theme set: clear and reinsert. This is acceptable in M1
        # (user hasn't renamed yet on first run); M2+ will preserve renames.
        existing = dao.list_themes(conn, project_id)
        for theme in existing:
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
