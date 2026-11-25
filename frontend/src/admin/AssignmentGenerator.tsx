import { useState, type FormEvent } from "react";
import {
  Alert,
  Button,
  Card,
  FormControl,
  Text,
  TextField,
  View,
} from "reshaped";
import { ApiError } from "../api/client";
import {
  generateAssignments,
  isUnauthorized,
  type AssignmentGenerationResult,
} from "./api";
import { formatWeekRange } from "./report-utils";

type Props = {
  onSessionExpired: () => void;
};

function isoDate(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function currentWeekStart(): string {
  const today = new Date();
  const daysSinceMonday = (today.getDay() + 6) % 7;
  today.setDate(today.getDate() - daysSinceMonday);
  return isoDate(today);
}

function messageFor(reason: unknown, fallback: string): string {
  return reason instanceof ApiError ? reason.message : fallback;
}

function assignmentCountLabel(count: number): string {
  return `${count} assignment${count === 1 ? "" : "s"}`;
}

export function AssignmentGenerator({ onSessionExpired }: Props) {
  const [week, setWeek] = useState(currentWeekStart);
  const [result, setResult] = useState<AssignmentGenerationResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const targetWeek = week.trim();
    if (!targetWeek) {
      setError("Choose a week to generate.");
      return;
    }

    setBusy(true);
    setError("");
    setResult(null);
    try {
      const generated = await generateAssignments(targetWeek);
      setResult(generated);
      setWeek(generated.week_start);
    } catch (reason) {
      if (isUnauthorized(reason)) {
        onSessionExpired();
        return;
      }
      setError(messageFor(reason, "Assignments could not be generated."));
    } finally {
      setBusy(false);
    }
  }

  const resultRange = result
    ? formatWeekRange(result.week_start, result.week_end)
    : "";
  const resultCount = result ? assignmentCountLabel(result.assignment_count) : "";

  return (
    <Card
      as="section"
      padding={5}
      borderRadius="large"
      className="admin-panel"
      attributes={{
        "aria-labelledby": "weekly-assignments-heading",
        id: "weekly-assignments",
      }}
    >
      <View gap={4}>
        <View gap={1}>
          <Text
            as="h2"
            variant="headline-2"
            attributes={{ id: "weekly-assignments-heading" }}
          >
            Weekly assignments
          </Text>
          <Text color="neutral-faded">
            Generate the Monday–Sunday assignments for a selected week. Manual
            generation uses the same deterministic rotation and immutable
            snapshots as the scheduled rollover, and repeating a week leaves its
            existing assignments unchanged.
          </Text>
        </View>

        {error && (
          <Alert color="critical" title="Assignment generation failed">
            {error}
          </Alert>
        )}

        <div className="admin-split admin-invite-grid">
          <Card
            as="section"
            padding={4}
            borderRadius="medium"
            className="admin-subpanel admin-form-panel"
          >
            <form onSubmit={(event) => void handleSubmit(event)}>
              <View gap={3}>
                <Text as="h3" variant="headline-3">
                  Generate a week
                </Text>
                <FormControl id="assignment-week">
                  <FormControl.Label>Target week</FormControl.Label>
                  <TextField
                    name="week"
                    value={week}
                    onChange={({ value }) => setWeek(value)}
                    inputAttributes={{ type: "date", required: true }}
                  />
                </FormControl>
                <Text variant="caption-1" color="neutral-faded">
                  Choose any date in the target week. The Monday–Sunday window is
                  resolved in the application reporting timezone.
                </Text>
                <View direction="row">
                  <Button
                    type="submit"
                    disabled={busy}
                    loading={busy}
                    loadingAriaLabel="Generating assignments"
                  >
                    Generate assignments
                  </Button>
                </View>
              </View>
            </form>

            {result && (
              <View gap={3} paddingTop={4}>
                <Alert
                  color={result.status === "generated" ? "positive" : "neutral"}
                  title={
                    result.status === "generated"
                      ? "Assignments generated"
                      : "Assignments already exist"
                  }
                >
                  {result.status === "generated"
                    ? `Generated ${resultCount} for ${resultRange}.`
                    : `Nothing changed; ${resultCount} already existed for ${resultRange}.`}
                </Alert>

                {result.assignments.length === 0 ? (
                  <Text color="neutral-faded">
                    No active family members were included in this week. The week
                    was still recorded as generated.
                  </Text>
                ) : (
                  <View gap={2}>
                    <Text as="h4" variant="featured-2">
                      Assignments for {resultRange}
                    </Text>
                    <dl className="admin-context-list">
                      {result.assignments.map((assignment) => (
                        <div key={assignment.id}>
                          <dt>{assignment.family_member_name}</dt>
                          <dd>{assignment.chore_name}</dd>
                        </div>
                      ))}
                    </dl>
                  </View>
                )}
              </View>
            )}
          </Card>

          <aside className="admin-context-panel admin-access-context">
            <span className="admin-context-kicker">How generation works</span>
            <h3>Same rules as Monday</h3>
            <p>
              Manual generation uses the same rotation, active catalog ordering,
              and immutable chore snapshots as the scheduled rollover.
            </p>
            <dl className="admin-context-list">
              <div>
                <dt>Window</dt>
                <dd>Mon–Sun</dd>
              </div>
              <div>
                <dt>Existing week</dt>
                <dd>Unchanged</dd>
              </div>
              <div>
                <dt>Reports</dt>
                <dd>Rollover only</dd>
              </div>
            </dl>
          </aside>
        </div>
      </View>
    </Card>
  );
}
