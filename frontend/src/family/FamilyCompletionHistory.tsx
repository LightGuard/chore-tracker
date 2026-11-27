import { useEffect, useId, useState } from "react";
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
  getCompletionHistory,
  type CompletionHistoryRecord,
  type CompletionStatus,
} from "./api";

const PAGE_SIZE = 50;
const LOAD_ERROR =
  "We couldn't load the completion history. Check your connection and try again.";

type StatusDetails = {
  label: string;
  color: "positive" | "warning" | "neutral";
};

const STATUS: Record<CompletionStatus, StatusDetails> = {
  complete: { label: "Complete", color: "positive" },
  incomplete: { label: "Incomplete", color: "warning" },
  not_yet_recorded: { label: "Not yet recorded", color: "neutral" },
};

const UPCOMING_STATUS: StatusDetails = {
  label: "Upcoming",
  color: "neutral",
};

function statusFor(
  record: CompletionHistoryRecord,
  today: string | null | undefined,
): StatusDetails {
  if (
    record.completion_status === "not_yet_recorded" &&
    today != null &&
    record.completion_date > today
  ) {
    return UPCOMING_STATUS;
  }
  return STATUS[record.completion_status];
}

const dayFormatter = new Intl.DateTimeFormat("en", {
  weekday: "long",
  month: "short",
  day: "numeric",
  year: "numeric",
  timeZone: "UTC",
});

const weekFormatter = new Intl.DateTimeFormat("en", {
  month: "short",
  day: "numeric",
  year: "numeric",
  timeZone: "UTC",
});

function fromLocalDate(value: string): Date {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day));
}

function formatDay(value: string): string {
  return dayFormatter.format(fromLocalDate(value));
}

function formatWeek(start: string, end: string): string {
  return `Week of ${weekFormatter.format(fromLocalDate(start))} – ${weekFormatter.format(fromLocalDate(end))}`;
}

type HistoryWeek = {
  assignmentId: number;
  weekStart: string;
  weekEnd: string;
  choreName: string;
  records: CompletionHistoryRecord[];
};

function groupByWeek(records: CompletionHistoryRecord[]): HistoryWeek[] {
  const groups: HistoryWeek[] = [];
  const byAssignment = new Map<number, HistoryWeek>();

  for (const record of records) {
    let group = byAssignment.get(record.assignment_id);
    if (!group) {
      group = {
        assignmentId: record.assignment_id,
        weekStart: record.week_start,
        weekEnd: record.week_end,
        choreName: record.chore_name,
        records: [],
      };
      byAssignment.set(record.assignment_id, group);
      groups.push(group);
    }
    group.records.push(record);
  }

  return groups;
}

function messageFor(reason: unknown): string {
  return reason instanceof ApiError ? reason.message : LOAD_ERROR;
}

type Props = {
  familyMemberId: number;
  displayName: string;
  today?: string | null;
};

export function FamilyCompletionHistory({
  familyMemberId,
  displayName,
  today,
}: Props) {
  const headingId = useId();
  const [records, setRecords] = useState<CompletionHistoryRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadMoreError, setLoadMoreError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    setRecords([]);
    setTotal(0);
    setStatus("loading");
    setError("");
    setLoadMoreError("");

    getCompletionHistory(familyMemberId, {
      limit: PAGE_SIZE,
      offset: 0,
      signal: controller.signal,
    })
      .then((page) => {
        setRecords(page.items);
        setTotal(page.total);
        setStatus("ready");
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(messageFor(reason));
        setStatus("error");
      });

    return () => controller.abort();
  }, [familyMemberId, reloadKey]);

  async function loadMore() {
    setLoadingMore(true);
    setLoadMoreError("");
    try {
      const page = await getCompletionHistory(familyMemberId, {
        limit: PAGE_SIZE,
        offset: records.length,
      });
      setRecords((current) => [...current, ...page.items]);
      setTotal(page.total);
    } catch (reason) {
      setLoadMoreError(messageFor(reason));
    } finally {
      setLoadingMore(false);
    }
  }

  const groups = groupByWeek(records);
  const hasMore = records.length < total;

  return (
    <Card
      as="section"
      padding={4}
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
            Completion history for {displayName}
          </Text>
          <Text color="neutral-faded">
            Saved daily records from this child&apos;s weekly assignments. Days
            without saved checklist activity are marked not yet recorded, and
            future days are marked upcoming.
          </Text>
        </View>

        {status === "loading" && (
          <View
            align="center"
            gap={2}
            padding={4}
            attributes={{ role: "status" }}
          >
            <Loader ariaLabel="Loading completion history" />
            <Text color="neutral-faded">Loading completion history…</Text>
          </View>
        )}

        {status === "error" && (
          <Alert
            color="critical"
            title="Completion history is unavailable"
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

        {status === "ready" && records.length === 0 && (
          <Alert color="neutral" title="No completion history yet">
            {displayName} has no historical chore records. Complete a daily
            checklist to start building history.
          </Alert>
        )}

        {status === "ready" &&
          groups.map((group) => {
            const weekHeadingId = `${headingId}-week-${group.assignmentId}`;
            return (
              <Card
                as="section"
                key={group.assignmentId}
                padding={4}
                borderRadius="medium"
                attributes={{ "aria-labelledby": weekHeadingId }}
              >
                <View gap={2}>
                  <View gap={1}>
                    <Text
                      as="h3"
                      variant="headline-3"
                      attributes={{ id: weekHeadingId }}
                    >
                      {group.choreName}
                    </Text>
                    <Text variant="caption-1" color="neutral-faded">
                      {formatWeek(group.weekStart, group.weekEnd)}
                    </Text>
                  </View>

                  <View
                    as="ol"
                    gap={1}
                    attributes={{
                      "aria-label": `${group.choreName} daily records`,
                    }}
                  >
                    {group.records.map((record) => {
                      const statusDetails = statusFor(record, today);
                      return (
                        <View.Item as="li" key={record.completion_date}>
                          <View
                            direction="row"
                            align="center"
                            justify="space-between"
                            gap={3}
                            wrap
                          >
                            <Text
                              as="time"
                              attributes={{ dateTime: record.completion_date }}
                            >
                              {formatDay(record.completion_date)}
                            </Text>
                            <Badge
                              color={statusDetails.color}
                              variant="faded"
                            >
                              {statusDetails.label}
                            </Badge>
                          </View>
                        </View.Item>
                      );
                    })}
                  </View>
                </View>
              </Card>
            );
          })}

        {loadMoreError && (
          <Alert color="critical" title="More history could not be loaded">
            {loadMoreError}
          </Alert>
        )}

        {status === "ready" && hasMore && (
          <View direction="row" justify="center">
            <Button
              variant="outline"
              loading={loadingMore}
              loadingAriaLabel="Loading more history"
              onClick={() => void loadMore()}
            >
              Load more history
            </Button>
          </View>
        )}
      </View>
    </Card>
  );
}
