"""SQLite persistence for immutable weekly completion reports."""

from __future__ import annotations

import sqlite3
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
    WeeklyReportHeader,
    WeeklyReportIncompleteError,
    WeeklyReportReward,
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
            day.status,
            reward.rewarded_at AS reward_rewarded_at,
            reward.rewarded_by_administrator_id AS reward_administrator_id,
            reward_administrator.email AS reward_administrator_email
        """
        reward_joins = """
            LEFT JOIN weekly_report_rewards AS reward
              ON reward.weekly_report_entry_id = entry.id
            LEFT JOIN administrators AS reward_administrator
              ON reward_administrator.id = reward.rewarded_by_administrator_id
        """
        if limit is None:
            rows = connection.execute(
                f"""
                SELECT {columns}
                FROM weekly_report_entries AS entry
                JOIN weekly_report_days AS day
                  ON day.report_entry_id = entry.id
                {reward_joins}
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
                {reward_joins}
                ORDER BY entry.position, day.day_index
                """,
                (report_id, limit, offset),
            ).fetchall()

        grouped: dict[int, tuple[sqlite3.Row, list[WeeklyReportDay]]] = {}
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
                reward=SQLiteWeeklyReportPersistence._reward_from_row(row),
            )
            for row, days in grouped.values()
        )

    @staticmethod
    def _reward_from_row(row) -> WeeklyReportReward | None:
        if row["reward_rewarded_at"] is None:
            return None
        return WeeklyReportReward(
            rewarded_at=_parse_timestamp(row["reward_rewarded_at"]),
            administrator_id=row["reward_administrator_id"],
            administrator_email=row["reward_administrator_email"],
        )

    @staticmethod
    def _header_from_row(row) -> WeeklyReportHeader:
        return WeeklyReportHeader(
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
        )

    @classmethod
    def _load_header_by_id(
        cls, connection, report_id: int
    ) -> WeeklyReportHeader | None:
        row = connection.execute(
            """
            SELECT id, week_start, week_end, generated_at, family_member_count,
                   total_days, completed_days, incomplete_days
            FROM weekly_reports
            WHERE id = ? AND finalized_at IS NOT NULL
            """,
            (report_id,),
        ).fetchone()
        return None if row is None else cls._header_from_row(row)

    @classmethod
    def _load_report_by_id(cls, connection, report_id: int) -> WeeklyReport | None:
        header = cls._load_header_by_id(connection, report_id)
        if header is None:
            return None
        return WeeklyReport(
            id=header.id,
            week_start=header.week_start,
            week_end=header.week_end,
            generated_at=header.generated_at,
            summary=header.summary,
            entries=cls._load_entries(connection, header.id),
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
            row["weekly_assignment_id"]: (
                row["item_count"],
                row["required_item_count"],
            )
            for row in connection.execute(
                f"""
                SELECT weekly_assignment_id, COUNT(*) AS item_count,
                       SUM(CASE WHEN is_required = 1 THEN 1 ELSE 0 END)
                         AS required_item_count
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
                  AND item.is_required = 1
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
            item_count, required_item_count = item_counts.get(assignment_id, (0, 0))
            sources.append(
                AssignmentReportSource(
                    weekly_assignment_id=assignment_id,
                    family_member_id=row["family_member_id"],
                    family_member_name=row["display_name"],
                    chore_name=row["chore_name_snapshot"],
                    chore_description=row["chore_description_snapshot"],
                    checklist_item_count=item_count,
                    required_checklist_item_count=required_item_count,
                    required_completed_item_counts=completed_item_counts,
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
            if report_id is None:
                raise RuntimeError("The weekly report insert did not return an ID")
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
                if entry_id is None:
                    raise RuntimeError(
                        "The weekly report entry insert did not return an ID"
                    )
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

    def list(self) -> tuple[WeeklyReportHeader, ...]:
        with transaction(self._database_path) as connection:
            rows = connection.execute(
                """
                SELECT id, week_start, week_end, generated_at, family_member_count,
                       total_days, completed_days, incomplete_days
                FROM weekly_reports
                WHERE finalized_at IS NOT NULL
                ORDER BY week_start DESC, id DESC
                """
            ).fetchall()
            return tuple(self._header_from_row(row) for row in rows)

    def get_header(self, week_start: date) -> WeeklyReportHeader | None:
        with transaction(self._database_path) as connection:
            row = connection.execute(
                """
                SELECT id, week_start, week_end, generated_at, family_member_count,
                       total_days, completed_days, incomplete_days
                FROM weekly_reports
                WHERE week_start = ? AND finalized_at IS NOT NULL
                """,
                (week_start.isoformat(),),
            ).fetchone()
            return None if row is None else self._header_from_row(row)

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

    def mark_rewarded(
        self,
        week_start: date,
        entry_id: int,
        administrator_id: int,
        rewarded_at: datetime,
    ) -> WeeklyReportReward | None:
        with transaction(self._database_path) as connection:
            # Serialize competing markers before checking the entry scope.
            connection.execute("BEGIN IMMEDIATE")
            entry = connection.execute(
                """
                SELECT entry.id
                FROM weekly_report_entries AS entry
                JOIN weekly_reports AS report
                  ON report.id = entry.report_id
                WHERE entry.id = ?
                  AND report.week_start = ?
                  AND report.finalized_at IS NOT NULL
                """,
                (entry_id, week_start.isoformat()),
            ).fetchone()
            if entry is None:
                return None
            connection.execute(
                """
                INSERT INTO weekly_report_rewards (
                    weekly_report_entry_id, rewarded_at,
                    rewarded_by_administrator_id
                )
                VALUES (?, ?, ?)
                ON CONFLICT (weekly_report_entry_id) DO NOTHING
                """,
                (entry_id, _format_timestamp(rewarded_at), administrator_id),
            )
            reward_row = connection.execute(
                """
                SELECT reward.rewarded_at,
                       reward.rewarded_by_administrator_id,
                       administrator.email
                FROM weekly_report_rewards AS reward
                JOIN administrators AS administrator
                  ON administrator.id = reward.rewarded_by_administrator_id
                WHERE reward.weekly_report_entry_id = ?
                """,
                (entry_id,),
            ).fetchone()
            if reward_row is None:
                raise RuntimeError("The weekly report reward was not persisted")
            return WeeklyReportReward(
                rewarded_at=_parse_timestamp(reward_row["rewarded_at"]),
                administrator_id=reward_row["rewarded_by_administrator_id"],
                administrator_email=reward_row["email"],
            )
