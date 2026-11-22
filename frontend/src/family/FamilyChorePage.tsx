import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Container,
  Divider,
  FormControl,
  Loader,
  Select,
  Text,
  View,
} from "reshaped";
import { ApiError } from "../api/client";
import { FamilyCompletionHistory } from "./FamilyCompletionHistory";
import {
  getActiveFamilyMembers,
  getCurrentAssignment,
  setChecklistItemCompletion,
  type ChecklistItem,
  type CurrentAssignment,
  type FamilyMember,
} from "./api";

type AssignmentStatus =
  | "idle"
  | "loading"
  | "ready"
  | "missing"
  | "inactive"
  | "error";

const MEMBERS_ERROR =
  "We couldn't load the family members. Check your connection and try again.";
const ASSIGNMENT_ERROR =
  "We couldn't load this week's chore. Check your connection and try again.";
const SAVE_ERROR =
  "We couldn't save that change. Check your connection and try again.";

function readableError(reason: unknown, fallback: string): string {
  return reason instanceof ApiError ? reason.message : fallback;
}

const dateFormatter = new Intl.DateTimeFormat("en", {
  month: "short",
  day: "numeric",
  timeZone: "UTC",
});

function formatDate(value: string): string {
  const [year, month, day] = value.split("-").map(Number);
  return dateFormatter.format(new Date(Date.UTC(year, month - 1, day)));
}

export function FamilyChorePage() {
  const [members, setMembers] = useState<FamilyMember[]>([]);
  const [membersLoading, setMembersLoading] = useState(true);
  const [membersError, setMembersError] = useState("");
  const [membersReloadKey, setMembersReloadKey] = useState(0);

  const [selectedMemberId, setSelectedMemberId] = useState("");
  const [assignment, setAssignment] = useState<CurrentAssignment | null>(null);
  const [assignmentStatus, setAssignmentStatus] =
    useState<AssignmentStatus>("idle");
  const [assignmentError, setAssignmentError] = useState("");
  const [assignmentReloadKey, setAssignmentReloadKey] = useState(0);

  const [savingItemId, setSavingItemId] = useState<number | null>(null);
  const [saveError, setSaveError] = useState("");
  const [historyOpen, setHistoryOpen] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    setMembersLoading(true);
    setMembersError("");

    getActiveFamilyMembers(controller.signal)
      .then((loadedMembers) => {
        setMembers(loadedMembers);
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setMembersError(readableError(reason, MEMBERS_ERROR));
      })
      .finally(() => {
        if (!controller.signal.aborted) setMembersLoading(false);
      });

    return () => controller.abort();
  }, [membersReloadKey]);

  useEffect(() => {
    if (!selectedMemberId) {
      setAssignment(null);
      setAssignmentStatus("idle");
      setAssignmentError("");
      return;
    }

    const controller = new AbortController();
    setAssignment(null);
    setAssignmentStatus("loading");
    setAssignmentError("");
    setSaveError("");

    getCurrentAssignment(Number(selectedMemberId), controller.signal)
      .then((loadedAssignment) => {
        setAssignment(loadedAssignment);
        setAssignmentStatus("ready");
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        if (reason instanceof ApiError && reason.status === 404) {
          setAssignmentStatus("missing");
        } else if (reason instanceof ApiError && reason.status === 409) {
          setAssignmentStatus("inactive");
        } else {
          setAssignmentStatus("error");
          setAssignmentError(readableError(reason, ASSIGNMENT_ERROR));
        }
      });

    return () => controller.abort();
  }, [selectedMemberId, assignmentReloadKey]);

  const handleToggle = useCallback(
    async (item: ChecklistItem, isCompleted: boolean) => {
      if (!assignment || savingItemId !== null) return;

      setSavingItemId(item.id);
      setSaveError("");
      try {
        const result = await setChecklistItemCompletion({
          familyMemberId: assignment.family_member_id,
          assignmentId: assignment.id,
          checklistItemId: item.id,
          completionDate: assignment.today,
          isCompleted,
        });
        setAssignment((current) => {
          if (!current) return current;
          return {
            ...current,
            checklist_items: current.checklist_items.map((entry) =>
              entry.id === item.id
                ? { ...entry, is_completed: result.checklist_item.is_completed }
                : entry,
            ),
            is_complete: result.is_complete,
          };
        });
      } catch (reason) {
        setSaveError(readableError(reason, SAVE_ERROR));
      } finally {
        setSavingItemId(null);
      }
    },
    [assignment, savingItemId],
  );

  const selectedMember = members.find(
    (member) => String(member.id) === selectedMemberId,
  );
  const completedCount =
    assignment?.checklist_items.filter((item) => item.is_completed).length ?? 0;
  const itemCount = assignment?.checklist_items.length ?? 0;

  return (
    <Container width="100%">
      <main className="app-shell family-shell">
        <View gap={1} paddingBlock={3}>
          <Text as="h1" variant="headline-1">
            Chore Tracker
          </Text>
          <Text color="neutral-faded">
            Choose your name to see this week&apos;s chore. This is a shared
            family screen; selecting a name does not sign you in.
          </Text>
        </View>

        <View gap={4} paddingTop={4}>
          {membersLoading ? (
            <View align="center" gap={2} padding={6} attributes={{ role: "status" }}>
              <Loader ariaLabel="Loading family members" />
              <Text color="neutral-faded">Loading family members…</Text>
            </View>
          ) : membersError ? (
            <Alert
              color="critical"
              title="Family members are unavailable"
              actionsSlot={
                <Button
                  variant="outline"
                  onClick={() => setMembersReloadKey((value) => value + 1)}
                >
                  Try again
                </Button>
              }
            >
              {membersError}
            </Alert>
          ) : members.length === 0 ? (
            <Alert color="neutral" title="No family members yet">
              Ask an administrator to add an active family member before chores
              can be viewed.
            </Alert>
          ) : (
            <Card padding={4} borderRadius="medium">
              <View gap={3}>
                <Text as="h2" variant="headline-3">
                  Who&apos;s doing chores?
                </Text>
                <FormControl id="child-select">
                  <FormControl.Label>Child</FormControl.Label>
                  <Select
                    name="family-member"
                    value={selectedMemberId}
                    placeholder="Choose a child"
                    onChange={({ value }) => setSelectedMemberId(value)}
                  >
                    {members.map((member) => (
                      <option key={member.id} value={String(member.id)}>
                        {member.display_name}
                      </option>
                    ))}
                  </Select>
                </FormControl>
                <Text variant="caption-1" color="neutral-faded">
                  Profiles are for selecting the right chore. They are not
                  authenticated accounts.
                </Text>
              </View>
            </Card>
          )}

          {!membersLoading && !membersError && members.length > 0 && (
            <View>
              {assignmentStatus === "idle" && (
                <Alert color="neutral" title="Select a child">
                  Choose a family member above to see this week&apos;s chore.
                </Alert>
              )}

              {assignmentStatus === "loading" && (
                <View
                  align="center"
                  gap={2}
                  padding={6}
                  attributes={{ role: "status" }}
                >
                  <Loader ariaLabel="Loading chore assignment" />
                  <Text color="neutral-faded">Loading this week&apos;s chore…</Text>
                </View>
              )}

              {assignmentStatus === "missing" && (
                <Alert color="neutral" title="No chore assigned this week">
                  {selectedMember?.display_name ?? "This family member"} does
                  not have a chore assigned for this week yet. An administrator
                  may need to generate the weekly assignments.
                </Alert>
              )}

              {assignmentStatus === "inactive" && (
                <Alert color="warning" title="This profile is inactive">
                  Ask an administrator to reactivate the profile to view its
                  chore.
                </Alert>
              )}

              {assignmentStatus === "error" && (
                <Alert
                  color="critical"
                  title="This week's chore is unavailable"
                  actionsSlot={
                    <Button
                      variant="outline"
                      onClick={() =>
                        setAssignmentReloadKey((value) => value + 1)
                      }
                    >
                      Try again
                    </Button>
                  }
                >
                  {assignmentError}
                </Alert>
              )}

              {assignmentStatus === "ready" && assignment && (
                <Card
                  as="section"
                  padding={5}
                  borderRadius="large"
                  raised
                  attributes={{ "aria-labelledby": "assignment-heading" }}
                >
                  <View gap={4}>
                    <View gap={1}>
                      <Text
                        as="h2"
                        variant="headline-2"
                        attributes={{ id: "assignment-heading" }}
                      >
                        {assignment.chore_name}
                      </Text>
                      <Text variant="caption-1" color="neutral-faded">
                        Week of {formatDate(assignment.week_start)} –{" "}
                        {formatDate(assignment.week_end)}
                      </Text>
                      {assignment.chore_description && (
                        <Text>{assignment.chore_description}</Text>
                      )}
                    </View>

                    <Divider />

                    {assignment.checklist_items.length === 0 ? (
                      <Alert color="warning" title="No checklist items">
                        This chore does not have any checklist items yet.
                      </Alert>
                    ) : (
                      <View
                        as="ol"
                        gap={2}
                        attributes={{ "aria-label": "Today's checklist" }}
                      >
                        {assignment.checklist_items.map((item) => (
                          <View.Item as="li" key={item.id}>
                            <Checkbox
                              name={`checklist-item-${item.id}`}
                              value={String(item.id)}
                              checked={item.is_completed}
                              disabled={savingItemId !== null}
                              onChange={({ checked }) =>
                                void handleToggle(item, checked)
                              }
                            >
                              {item.label}
                            </Checkbox>
                          </View.Item>
                        ))}
                      </View>
                    )}

                    {saveError && (
                      <Alert color="critical" title="Couldn't save that change">
                        {saveError}
                      </Alert>
                    )}

                    <View gap={2} attributes={{ "aria-live": "polite" }}>
                      <Text
                        weight="medium"
                        color={
                          assignment.is_complete ? "positive" : "neutral-faded"
                        }
                      >
                        {completedCount} of {itemCount} complete today
                      </Text>
                      {assignment.is_complete && (
                        <Alert color="positive" title="All done for today">
                          Every item on this chore is complete.
                        </Alert>
                      )}
                    </View>
                  </View>
                </Card>
              )}

              {selectedMemberId && (
                <View gap={3} paddingTop={4}>
                  <View
                    direction="row"
                    align="center"
                    justify="space-between"
                    gap={2}
                    wrap
                  >
                    <Text as="h2" variant="headline-3">
                      Past chores
                    </Text>
                    <Button
                      variant="outline"
                      onClick={() => setHistoryOpen((open) => !open)}
                    >
                      {historyOpen ? "Hide history" : "View history"}
                    </Button>
                  </View>
                  {historyOpen && (
                    <FamilyCompletionHistory
                      key={selectedMemberId}
                      familyMemberId={Number(selectedMemberId)}
                      displayName={
                        selectedMember?.display_name ?? "this child"
                      }
                    />
                  )}
                </View>
              )}
            </View>
          )}
        </View>
      </main>
    </Container>
  );
}
