import { useEffect, useId, useState } from "react";
import { Link } from "react-router-dom";
import {
  Alert,
  Button,
  Card,
  Loader,
  ProgressBar,
  Text,
  View,
} from "reshaped";
import { ApiError } from "../api/client";
import {
  getReport,
  isUnauthorized,
  type WeeklyReportDetail,
  type WeeklyReportEntry,
} from "./api";
import {
  formatGeneratedAt,
  formatReportWeekday,
  formatWeekRange,
  fromLocalDate,
  reportCompletionPercent,
} from "./report-utils";

const PAGE_SIZE = 5;
const LOAD_ERROR =
  "We couldn't load this weekly report. Check your connection and try again.";

type LoadStatus = "loading" | "ready" | "missing" | "error";

function messageFor(reason: unknown): string {
  return reason instanceof ApiError ? reason.message : LOAD_ERROR;
}

function entryStatusLabel(entry: WeeklyReportEntry): string {
  if (entry.completed_days === 7) return "Complete";
  if (entry.completed_days === 0) return "All incomplete";
  return `${entry.incomplete_days} incomplete`;
}

function entryStatusClass(entry: WeeklyReportEntry): string {
  if (entry.completed_days === 7) return "complete-pill";
  if (entry.completed_days === 0) return "empty-pill";
  return "partial-pill";
}

type Props = {
  weekStart: string;
  onSessionExpired: () => void;
};

export function ReportDetail({ weekStart, onSessionExpired }: Props) {
  const headingId = useId();
  const [report, setReport] = useState<WeeklyReportDetail | null>(null);
  const [offset, setOffset] = useState(0);
  const [status, setStatus] = useState<LoadStatus>("loading");
  const [error, setError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setStatus("loading");
    setError("");

    getReport(weekStart, {
      limit: PAGE_SIZE,
      offset,
      signal: controller.signal,
    })
      .then((loadedReport) => {
        if (controller.signal.aborted) return;
        setReport(loadedReport);
        setStatus("ready");
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        if (isUnauthorized(reason)) {
          onSessionExpired();
          return;
        }
        if (reason instanceof ApiError && reason.status === 404) {
          setReport(null);
          setStatus("missing");
          return;
        }
        setError(messageFor(reason));
        setStatus("error");
      });

    return () => controller.abort();
  }, [onSessionExpired, offset, reloadKey, weekStart]);

  const weekLabel = report
    ? formatWeekRange(report.week_start, report.week_end)
    : "";
  const pageDays = report
    ? Array.from({ length: 7 }, (_, index) => {
        const day = fromLocalDate(report.week_start);
        day.setUTCDate(day.getUTCDate() + index);
        return day.toISOString().slice(0, 10);
      })
    : [];
  const percent = report
    ? reportCompletionPercent(
        report.summary.completed_days,
        report.summary.total_days,
      )
    : 0;
  const shownStart = report && report.entries.length > 0 ? offset + 1 : 0;
  const shownEnd = report ? offset + report.entries.length : 0;

  return (
    <section className="report-detail" aria-label="Report detail">
      <View gap={4}>
        <View>
          <Link className="report-back-link" to="/admin/reports">
            ← All weekly reports
          </Link>
        </View>

        {status === "loading" && (
          <View
            align="center"
            gap={2}
            padding={6}
            attributes={{ role: "status" }}
          >
            <Loader ariaLabel="Loading weekly report" />
            <Text color="neutral-faded">Loading weekly report…</Text>
          </View>
        )}

        {status === "missing" && (
          <Alert color="neutral" title="Report not found">
            That weekly report does not exist. Return to the report history to
            choose a generated report.
          </Alert>
        )}

        {status === "error" && (
          <Alert
            color="critical"
            title="Weekly report is unavailable"
            actionsSlot={
              <Button
                variant="outline"
                onClick={() => setReloadKey((value) => value + 1)}
              >
                Try again
              </Button>
            }
          >
            {error}
          </Alert>
        )}

        {status === "ready" && report && (
          <>
            <View gap={1}>
              <Text
                as="h2"
                variant="headline-1"
                attributes={{ id: headingId }}
              >
                {weekLabel}
              </Text>
              <Text color="neutral-faded">
                Every child with an assignment this week, their assigned chore,
                and a persisted completion status for each day.
              </Text>
            </View>

            <div className="report-meta">
              <span>
                Generated{" "}
                <strong>
                  <time dateTime={report.generated_at}>
                    {formatGeneratedAt(report.generated_at)}
                  </time>
                </strong>
              </span>
              <span>
                Snapshot <strong>Finalized</strong>
              </span>
              <span>
                Entries <strong>{report.summary.family_member_count}</strong>
              </span>
            </div>

            <div className="report-stat-grid">
              <div className="report-stat">
                <Text variant="caption-1" color="neutral-faded">
                  Children with assignments
                </Text>
                <strong>{report.summary.family_member_count}</strong>
                <Text variant="caption-1" color="neutral-faded">
                  every assigned child is represented
                </Text>
              </div>
              <div className="report-stat">
                <Text variant="caption-1" color="neutral-faded">
                  Days complete
                </Text>
                <strong>{report.summary.completed_days}</strong>
                <Text variant="caption-1" color="neutral-faded">
                  of {report.summary.total_days} child-day slots
                </Text>
              </div>
              <div className="report-stat">
                <Text variant="caption-1" color="neutral-faded">
                  Days incomplete
                </Text>
                <strong>{report.summary.incomplete_days}</strong>
                <Text variant="caption-1" color="neutral-faded">
                  reported as incomplete, not errors
                </Text>
              </div>
            </div>

            <div className="report-progress-card">
              <div className="report-progress-copy">
                <Text variant="caption-1" color="neutral-faded">
                  Family completion for the week
                </Text>
                <Text variant="caption-1" weight="semibold">
                  {percent}%
                </Text>
              </div>
              <ProgressBar
                value={percent}
                color="positive"
                ariaLabel="Family completion for the week"
              />
            </div>

            {report.total === 0 ? (
              <Alert color="neutral" title="This report has no entries">
                No child had an assignment recorded for this week.
              </Alert>
            ) : (
              <Card padding={0} borderRadius="large">
                <div className="report-table-wrap">
                  <table
                    className="report-table"
                    aria-label={`Report entries for ${weekLabel}`}
                  >
                    <thead>
                      <tr>
                        <th scope="col">Child &amp; chore</th>
                        {pageDays.map((day) => (
                          <th key={day} scope="col">
                            <span>{formatReportWeekday(day)}</span>
                            <strong>{fromLocalDate(day).getUTCDate()}</strong>
                          </th>
                        ))}
                        <th scope="col">Week</th>
                      </tr>
                    </thead>
                    <tbody>
                      {report.entries.map((entry) => (
                        <tr
                          key={entry.id}
                          aria-label={`Report entry for ${entry.family_member_name}`}
                        >
                          <td className="report-child-cell">
                            <span className="report-child-inner">
                              <span
                                className="report-avatar"
                                aria-hidden="true"
                              >
                                {entry.family_member_name
                                  .slice(0, 1)
                                  .toUpperCase()}
                              </span>
                              <span className="report-child-copy">
                                <strong>{entry.family_member_name}</strong>
                                <span>{entry.chore_name}</span>
                              </span>
                            </span>
                          </td>
                          {entry.days.map((day) => (
                            <td key={day.date} className="report-day-cell">
                              <span
                                className={`report-day-status ${day.status}`}
                                aria-label={`${day.date}: ${
                                  day.status === "complete"
                                    ? "Complete"
                                    : "Incomplete"
                                }`}
                              >
                                {day.status === "complete" ? "✓" : "–"}
                              </span>
                            </td>
                          ))}
                          <td className="report-total-cell">
                            <strong>
                              {entry.completed_days} <span>/ 7</span>
                            </strong>
                            <span
                              className={`report-status-pill ${entryStatusClass(entry)}`}
                            >
                              {entryStatusLabel(entry)}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            )}

            <div className="report-legend">
              <span>
                <i className="yes">✓</i> Complete
              </span>
              <span>
                <i className="no">–</i> Incomplete
              </span>
              <span>All seven days are persisted with the report.</span>
            </div>

            {report.total > 0 && (
              <div className="report-pagination">
                <Text variant="caption-1" color="neutral-faded">
                  Showing {shownStart}–{shownEnd} of {report.total} entries
                </Text>
                <View direction="row" gap={2}>
                  <Button
                    variant="outline"
                    disabled={offset === 0}
                    onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                  >
                    Previous
                  </Button>
                  <Button
                    variant="outline"
                    disabled={offset + PAGE_SIZE >= report.total}
                    onClick={() => setOffset(offset + PAGE_SIZE)}
                  >
                    Next
                  </Button>
                </View>
              </div>
            )}

            <Text variant="caption-1" color="neutral-faded">
              Finalized immutable snapshot. Daily status is calculated from
              persisted checklist completion records for the assignment week; a
              day without a complete record is reported as incomplete.
            </Text>
          </>
        )}
      </View>
    </section>
  );
}
