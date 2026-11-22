"""SQLite persistence for immutable weekly completion reports."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from chore_tracker.adapters.sqlite import transaction
from chore_tracker.application.services.weekly_reports import (
    AssignmentReportSource,
    DailyStatus,
    WeeklyReport,
    WeeklyReportDay,
    WeeklyReportEntry,
    WeeklyReportEntryPage,
    WeeklyReportIncompleteError,
    WeeklyReportSummary,
    build_weekly_report_draft,
)


def _format_timestamp(value: datetime) -> str:
    return (
        value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    )


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


class SQLiteWeeklyReportPersistence:
    """Generate and read finalized report snapshots in one transaction."""

    def __init__(self, database_path: str | Path) -> None:
        self._database_path = database_path

    @staticmethod
    def _load_entries(
        connection,
        report_id: int,
        limit: int | None = None,
        offset: int = 0,
    ) -> tuple[WeeklyReportEntry, ...]:
        columns = """
            entry.id AS entry_id,
            entry.weekly_assignment_id,
            entry.family_member_id,
            entry.family_member_name_snapshot,
            entry.chore_name_snapshot,
            entry.chore_description_snapshot,
            entry.completed_days,
            entry.incomplete_days,
            entry.position,
            day.report_date,
            day.status
        """
        if limit is None:
            rows = connection.execute(
                f"""
                SELECT {columns}
                FROM weekly_report_entries AS entry
                JOIN weekly_report_days AS day
                  ON day.report_entry_id = entry.id
                WHERE entry.report_id = ?
                ORDER BY entry.position, day.day_index
                """,
                (report_id,),
            ).fetchall()
        else:
            rows = connection.execute(
                f"""
                SELECT {columns}
                FROM (
                    SELECT *
                    FROM weekly_report_entries
                    WHERE report_id = ?
                    ORDER BY position, id
                    LIMIT ? OFFSET ?
                ) AS entry
                JOIN weekly_report_days AS day
                  ON day.report_entry_id = entry.id
                ORDER BY entry.position, day.day_index
                """,
                (report_id, limit, offset),
            ).fetchall()

        grouped: dict[int, tuple[object, list[WeeklyReportDay]]] = {}
        for row in rows:
            entry_id = row["entry_id"]
            if entry_id not in grouped:
                grouped[entry_id] = (row, [])
            grouped[entry_id][1].append(
                WeeklyReportDay(
                    report_date=date.fromisoformat(row["report_date"]),
                    status=DailyStatus(row["status"]),
                )
            )
        return tuple(
            WeeklyReportEntry(
                id=row["entry_id"],
                weekly_assignment_id=row["weekly_assignment_id"],
                family_member_id=row["family_member_id"],
                family_member_name=row["family_member_name_snapshot"],
                chore_name=row["chore_name_snapshot"],
                chore_description=row["chore_description_snapshot"],
                completed_days=row["completed_days"],
                incomplete_days=row["incomplete_days"],
                days=tuple(days),
            )
            for row, days in grouped.values()
        )

    @classmethod
    def _load_report_by_id(cls, connection, report_id: int) -> WeeklyReport | None:
        row = connection.execute(
            """
            SELECT id, week_start, week_end, generated_at, family_member_count,
                   total_days, completed_days, incomplete_days
            FROM weekly_reports
            WHERE id = ? AND finalized_at IS NOT NULL
            """,
            (report_id,),
        ).fetchone()
        if row is None:
            return None
        return WeeklyReport(
            id=row["id"],
            week_start=date.fromisoformat(row["week_start"]),
            week_end=date.fromisoformat(row["week_end"]),
            generated_at=_parse_timestamp(row["generated_at"]),
            summary=WeeklyReportSummary(
                family_member_count=row["family_member_count"],
                total_days=row["total_days"],
                completed_days=row["completed_days"],
                incomplete_days=row["incomplete_days"],
            ),
            entries=cls._load_entries(connection, row["id"]),
        )

    @staticmethod
    def _read_assignment_sources(
        connection, week_start: date, week_end: date
    ) -> tuple[AssignmentReportSource, ...]:
        assignment_rows = connection.execute(
            """
            SELECT assignment.id, assignment.family_member_id,
                   member.display_name, assignment.chore_name_snapshot,
                   assignment.chore_description_snapshot
            FROM weekly_assignments AS assignment
            JOIN family_members AS member
              ON member.id = assignment.family_member_id
            WHERE assignment.week_start = ? AND assignment.week_end = ?
            ORDER BY member.display_name COLLATE NOCASE, member.id, assignment.id
            """,
            (week_start.isoformat(), week_end.isoformat()),
        ).fetchall()
        if not assignment_rows:
            return ()

        assignment_ids = [row["id"] for row in assignment_rows]
        placeholders = ", ".join("?" for _ in assignment_ids)
        item_counts = {
            row["weekly_assignment_id"]: row["item_count"]
            for row in connection.execute(
                f"""
                SELECT weekly_assignment_id, COUNT(*) AS item_count
                FROM assignment_checklist_items
                WHERE weekly_assignment_id IN ({placeholders})
                GROUP BY weekly_assignment_id
                """,
                assignment_ids,
            ).fetchall()
        }
        completed_counts = {
            (row["weekly_assignment_id"], row["completion_date"]): row[
                "completed_count"
            ]
            for row in connection.execute(
                f"""
                SELECT item.weekly_assignment_id, completion.completion_date,
                       SUM(completion.is_completed) AS completed_count
                FROM assignment_checklist_items AS item
                JOIN daily_checklist_completions AS completion
                  ON completion.assignment_checklist_item_id = item.id
                WHERE item.weekly_assignment_id IN ({placeholders})
                  AND completion.completion_date BETWEEN ? AND ?
                GROUP BY item.weekly_assignment_id,
                         completion.completion_date
                """,
                (*assignment_ids, week_start.isoformat(), week_end.isoformat()),
            ).fetchall()
        }

        sources = []
        for row in assignment_rows:
            assignment_id = row["id"]
            completed_item_counts = tuple(
                completed_counts.get(
                    (
                        assignment_id,
                        (week_start + timedelta(days=day_index)).isoformat(),
                    ),
                    0,
                )
                for day_index in range(7)
            )
            sources.append(
                AssignmentReportSource(
                    weekly_assignment_id=assignment_id,
                    family_member_id=row["family_member_id"],
                    family_member_name=row["display_name"],
                    chore_name=row["chore_name_snapshot"],
                    chore_description=row["chore_description_snapshot"],
                    checklist_item_count=item_counts.get(assignment_id, 0),
                    completed_item_counts=completed_item_counts,
                )
            )
        return tuple(sources)

    def generate(
        self, week_start: date, week_end: date, generated_at: datetime
    ) -> WeeklyReport:
        with transaction(self._database_path) as connection:
            # Serialize competing generators before checking for an existing week.
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT id FROM weekly_reports WHERE week_start = ?",
                (week_start.isoformat(),),
            ).fetchone()
            if existing is not None:
                report = self._load_report_by_id(connection, existing["id"])
                if report is None:
                    raise WeeklyReportIncompleteError(
                        "An existing weekly report has not been finalized"
                    )
                return report

            sources = self._read_assignment_sources(connection, week_start, week_end)
            draft = build_weekly_report_draft(
                week_start, week_end, generated_at, sources
            )
            timestamp = _format_timestamp(draft.generated_at)
            report_id = connection.execute(
                """
                INSERT INTO weekly_reports (
                    week_start, week_end, family_member_count, total_days,
                    completed_days, incomplete_days, generated_at, finalized_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    week_start.isoformat(),
                    week_end.isoformat(),
                    draft.summary.family_member_count,
                    draft.summary.total_days,
                    draft.summary.completed_days,
                    draft.summary.incomplete_days,
                    timestamp,
                    timestamp,
                ),
            ).lastrowid
            for position, entry in enumerate(draft.entries):
                entry_id = connection.execute(
                    """
                    INSERT INTO weekly_report_entries (
                        report_id, weekly_assignment_id, position,
                        family_member_id, family_member_name_snapshot,
                        chore_name_snapshot, chore_description_snapshot,
                        completed_days, incomplete_days
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        report_id,
                        entry.weekly_assignment_id,
                        position,
                        entry.family_member_id,
                        entry.family_member_name,
                        entry.chore_name,
                        entry.chore_description,
                        entry.completed_days,
                        entry.incomplete_days,
                    ),
                ).lastrowid
                connection.executemany(
                    """
                    INSERT INTO weekly_report_days (
                        report_entry_id, report_date, day_index, status
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    [
                        (
                            entry_id,
                            day.report_date.isoformat(),
                            day_index,
                            day.status.value,
                        )
                        for day_index, day in enumerate(entry.days)
                    ],
                )

            report = self._load_report_by_id(connection, report_id)
            if report is None:
                raise RuntimeError("The weekly report could not be read after creation")
            return report

    def get(self, week_start: date) -> WeeklyReport | None:
        with transaction(self._database_path) as connection:
            row = connection.execute(
                """
                SELECT id
                FROM weekly_reports
                WHERE week_start = ? AND finalized_at IS NOT NULL
                """,
                (week_start.isoformat(),),
            ).fetchone()
            if row is None:
                return None
            return self._load_report_by_id(connection, row["id"])

    def get_entries(
        self, week_start: date, limit: int, offset: int
    ) -> WeeklyReportEntryPage | None:
        with transaction(self._database_path) as connection:
            report = connection.execute(
                """
                SELECT id
                FROM weekly_reports
                WHERE week_start = ? AND finalized_at IS NOT NULL
                """,
                (week_start.isoformat(),),
            ).fetchone()
            if report is None:
                return None
            report_id = report["id"]
            total = connection.execute(
                "SELECT COUNT(*) FROM weekly_report_entries WHERE report_id = ?",
                (report_id,),
            ).fetchone()[0]
            entries = self._load_entries(connection, report_id, limit, offset)
            return WeeklyReportEntryPage(
                report_id=report_id,
                entries=entries,
                total=total,
                limit=limit,
                offset=offset,
            )
