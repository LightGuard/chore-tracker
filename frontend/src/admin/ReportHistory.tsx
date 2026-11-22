import { useEffect, useId, useState } from "react";
import { Link } from "react-router-dom";
import {
  Alert,
  Badge,
  Button,
  Card,
  Loader,
  Text,
  View,
} from "reshaped";
import { ApiError } from "../api/client";
import {
  isUnauthorized,
  listReports,
  type WeeklyReportListItem,
} from "./api";
import { formatGeneratedAt, formatWeekRange } from "./report-utils";

const LOAD_ERROR =
  "We couldn't load the weekly reports. Check your connection and try again.";

function messageFor(reason: unknown): string {
  return reason instanceof ApiError ? reason.message : LOAD_ERROR;
}

function reportBadgeColor(
  report: WeeklyReportListItem,
): "positive" | "warning" | "neutral" {
  if (report.summary.total_days === 0) return "neutral";
  if (report.summary.completed_days === report.summary.total_days) {
    return "positive";
  }
  if (report.summary.completed_days === 0) return "neutral";
  return "warning";
}

type Props = {
  onSessionExpired: () => void;
};

export function ReportHistory({ onSessionExpired }: Props) {
  const headingId = useId();
  const [reports, setReports] = useState<WeeklyReportListItem[]>([]);
  const [status, setStatus] = useState<"loading" | "ready" | "error">(
    "loading",
  );
  const [error, setError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setStatus("loading");
    setError("");

    listReports()
      .then((loadedReports) => {
        if (controller.signal.aborted) return;
        setReports(loadedReports);
        setStatus("ready");
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        if (isUnauthorized(reason)) {
          onSessionExpired();
          return;
        }
        setError(messageFor(reason));
        setStatus("error");
      });

    return () => controller.abort();
  }, [onSessionExpired, reloadKey]);

  return (
    <Card
      as="section"
      padding={5}
      borderRadius="large"
      attributes={{ "aria-labelledby": headingId }}
    >
      <View gap={4}>
        <View gap={1}>
          <Text
            as="h2"
            variant="headline-2"
            attributes={{ id: headingId }}
          >
            Report history
          </Text>
          <Text color="neutral-faded">
            Finalized Monday–Sunday snapshots, newest first. Each report is
            read from what was persisted for that week.
          </Text>
        </View>

        {status === "loading" && (
          <View
            align="center"
            gap={2}
            padding={4}
            attributes={{ role: "status" }}
          >
            <Loader ariaLabel="Loading weekly reports" />
            <Text color="neutral-faded">Loading weekly reports…</Text>
          </View>
        )}

        {status === "error" && (
          <Alert
            color="critical"
            title="Weekly reports are unavailable"
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

        {status === "ready" && reports.length === 0 && (
          <Alert color="neutral" title="No weekly reports yet">
            Reports are created after a Monday–Sunday week ends and the weekly
            rollover runs. Check back after the next report is generated.
          </Alert>
        )}

        {status === "ready" &&
          reports.map((report) => {
            const reportHeadingId = `${headingId}-${report.id}`;
            const week = formatWeekRange(report.week_start, report.week_end);
            return (
              <Card
                as="article"
                key={report.id}
                padding={4}
                borderRadius="medium"
                attributes={{ "aria-labelledby": reportHeadingId }}
              >
                <View gap={3}>
                  <View
                    direction="row"
                    align="center"
                    justify="space-between"
                    gap={3}
                    wrap
                  >
                    <View gap={1}>
                      <Text
                        as="h3"
                        variant="headline-3"
                        attributes={{ id: reportHeadingId }}
                      >
                        {week}
                      </Text>
                      <Text variant="caption-1" color="neutral-faded">
                        Generated{" "}
                        <time dateTime={report.generated_at}>
                          {formatGeneratedAt(report.generated_at)}
                        </time>
                      </Text>
                    </View>
                    <View direction="row" align="center" gap={2} wrap>
                      <Badge
                        color={reportBadgeColor(report)}
                        variant="faded"
                      >
                        {report.summary.completed_days} /{" "}
                        {report.summary.total_days} days
                      </Badge>
                      <Link
                        className="report-link-button"
                        to={`/admin/reports/${report.week_start}`}
                        aria-label={`View report for ${week}`}
                      >
                        View report
                      </Link>
                    </View>
                  </View>
                  <Text variant="caption-1" color="neutral-faded">
                    {report.summary.family_member_count} children ·{" "}
                    {report.summary.incomplete_days} incomplete days
                  </Text>
                </View>
              </Card>
            );
          })}
      </View>
    </Card>
  );
}
