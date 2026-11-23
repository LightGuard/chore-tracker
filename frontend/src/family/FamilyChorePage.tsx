import { useCallback, useEffect, useRef, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Container,
  Divider,
  Loader,
  Text,
  View,
} from "reshaped";
import { ApiError } from "../api/client";
import { AppHeader } from "../components/AppHeader";
import { ChildSelector } from "../components/ChildSelector";
import { ThemePicker } from "../components/ThemePicker";
import { ThemeScope } from "../components/ThemeScope";
import { DEFAULT_THEME, resolveThemeId, updateFamilyMemberTheme } from "../theme/api";
import {
  applyDocumentTheme,
  clearCachedTheme,
  forgetRememberedChild,
  readCachedTheme,
  readRememberedChildId,
  rememberChildId,
  writeCachedTheme,
  writeLastTheme,
} from "../theme/storage";
import { useThemeCatalog } from "../theme/useThemeCatalog";
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
const THEME_SAVE_ERROR =
  "We couldn't save that theme. Check your connection and try again.";

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

const longDateFormatter = new Intl.DateTimeFormat("en", {
  weekday: "long",
  month: "long",
  day: "numeric",
  timeZone: "UTC",
});

function formatLongDate(value: string): string {
  const [year, month, day] = value.split("-").map(Number);
  return longDateFormatter.format(new Date(Date.UTC(year, month - 1, day)));
}

function isoWeekNumber(value: string): number {
  const date = new Date(`${value}T00:00:00Z`);
  const day = (date.getUTCDay() + 6) % 7;
  date.setUTCDate(date.getUTCDate() - day + 3);
  const firstThursday = new Date(Date.UTC(date.getUTCFullYear(), 0, 4));
  const firstDay = (firstThursday.getUTCDay() + 6) % 7;
  firstThursday.setUTCDate(firstThursday.getUTCDate() - firstDay + 3);
  return 1 + Math.round((date.getTime() - firstThursday.getTime()) / 604800000);
}

export function FamilyChorePage() {
  const catalog = useThemeCatalog();
  const [members, setMembers] = useState<FamilyMember[]>([]);
  const [membersLoading, setMembersLoading] = useState(true);
  const [membersError, setMembersError] = useState("");
  const [membersReloadKey, setMembersReloadKey] = useState(0);

  const [selectedMemberId, setSelectedMemberId] = useState("");
  const [themeId, setThemeId] = useState(() => {
    const remembered = readRememberedChildId();
    return remembered === null
      ? DEFAULT_THEME.id
      : resolveThemeId(readCachedTheme("child", remembered), [DEFAULT_THEME]);
  });
  const [needsThemePicker, setNeedsThemePicker] = useState(false);
  const [themeBusy, setThemeBusy] = useState(false);
  const [themeError, setThemeError] = useState("");
  const [failedThemeId, setFailedThemeId] = useState("");
  const [switchOpen, setSwitchOpen] = useState(false);
  const [restoring, setRestoring] = useState(
    () => readRememberedChildId() !== null,
  );

  const [assignment, setAssignment] = useState<CurrentAssignment | null>(null);
  const [assignmentStatus, setAssignmentStatus] =
    useState<AssignmentStatus>("idle");
  const [assignmentError, setAssignmentError] = useState("");
  const [assignmentReloadKey, setAssignmentReloadKey] = useState(0);

  const [savingItemId, setSavingItemId] = useState<number | null>(null);
  const [saveError, setSaveError] = useState("");
  const [historyOpen, setHistoryOpen] = useState(false);
  const restored = useRef(false);

  useEffect(() => {
    applyDocumentTheme(themeId);
  }, [themeId]);

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

  const selectMember = useCallback(
    (member: FamilyMember) => {
      setSelectedMemberId(String(member.id));
      setSwitchOpen(false);
      setRestoring(false);
      setThemeError("");
      setFailedThemeId("");
      setSaveError("");

      const hasSavedTheme =
        member.theme_id !== null &&
        catalog.themes.some((theme) => theme.id === member.theme_id);

      if (hasSavedTheme) {
        const resolved = resolveThemeId(member.theme_id, catalog.themes);
        setThemeId(resolved);
        applyDocumentTheme(resolved);
        writeCachedTheme("child", member.id, resolved);
        writeLastTheme(resolved);
        rememberChildId(member.id);
        setNeedsThemePicker(false);
      } else {
        setThemeId(DEFAULT_THEME.id);
        applyDocumentTheme(DEFAULT_THEME.id);
        clearCachedTheme("child", member.id);
        forgetRememberedChild();
        setNeedsThemePicker(true);
      }
    },
    [catalog.themes],
  );

  useEffect(() => {
    if (restored.current || membersLoading || membersError) return;
    restored.current = true;
    const remembered = readRememberedChildId();
    if (remembered !== null) {
      const member = members.find((entry) => entry.id === remembered);
      if (member) {
        selectMember(member);
        return;
      }
      forgetRememberedChild();
      setThemeId(DEFAULT_THEME.id);
      applyDocumentTheme(DEFAULT_THEME.id);
    }
    setRestoring(false);
  }, [members, membersLoading, membersError, selectMember]);

  useEffect(() => {
    if (!selectedMemberId || needsThemePicker) {
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
  }, [selectedMemberId, needsThemePicker, assignmentReloadKey]);

  const selectedMember = members.find(
    (member) => String(member.id) === selectedMemberId,
  );

  const saveTheme = useCallback(
    async (nextThemeId: string) => {
      if (!selectedMember || themeBusy) return;
      if (!needsThemePicker && nextThemeId === themeId) return;

      setThemeBusy(true);
      setThemeError("");
      setFailedThemeId(nextThemeId);
      try {
        const result = await updateFamilyMemberTheme(
          selectedMember.id,
          nextThemeId,
        );
        const stored = resolveThemeId(result.theme_id, catalog.themes);
        setThemeId(stored);
        applyDocumentTheme(stored);
        writeCachedTheme("child", selectedMember.id, stored);
        writeLastTheme(stored);
        rememberChildId(selectedMember.id);
        setNeedsThemePicker(false);
        setThemeError("");
        setFailedThemeId("");
      } catch (reason) {
        setThemeError(readableError(reason, THEME_SAVE_ERROR));
      } finally {
        setThemeBusy(false);
      }
    },
    [catalog.themes, needsThemePicker, selectedMember, themeBusy, themeId],
  );

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

  const completedCount =
    assignment?.checklist_items.filter((item) => item.is_completed).length ?? 0;
  const itemCount = assignment?.checklist_items.length ?? 0;
  const firstTimePicker = Boolean(selectedMember && needsThemePicker);
  const showCurrentChild = Boolean(selectedMember);

  return (
    <ThemeScope themeId={themeId}>
      <AppHeader
        themes={catalog.themes}
        themeId={themeId}
        themeDisabled={!showCurrentChild || themeBusy}
        themeDisabledReason="Choose a child before changing the theme."
        themeBusy={themeBusy}
        onThemeChange={saveTheme}
        currentChild={selectedMember?.display_name}
        onSwitchChild={
          selectedMember ? () => setSwitchOpen(true) : undefined
        }
        context="family"
      />

      <Container width="100%">
        <main className="app-shell family-shell homestead-family">
          <div className="family-hero">
            <div>
              <div className="section-kicker">
                {assignment ? formatLongDate(assignment.today) : "This week at our house"}
              </div>
              <h1>
                {selectedMember ? (
                  <>
                    <em>{selectedMember.display_name}&rsquo;s</em> week
                  </>
                ) : (
                  "Who’s doing chores?"
                )}
              </h1>
              <p className="section-lede">
                {selectedMember
                  ? "One week, one chore, one page. Pick up where you left off."
                  : "This is a shared family screen. Choosing a name does not sign you in."}
              </p>
            </div>
          </div>

          {catalog.error && (
            <Alert color="warning" title="Theme catalog unavailable">
              {catalog.error} Homestead is being used for now.
            </Alert>
          )}

          {themeError && !firstTimePicker && (
            <Alert
              color="critical"
              title="Theme was not saved"
              actionsSlot={
                failedThemeId ? (
                  <Button
                    variant="outline"
                    disabled={themeBusy}
                    onClick={() => void saveTheme(failedThemeId)}
                  >
                    Try again
                  </Button>
                ) : undefined
              }
            >
              {themeError}
            </Alert>
          )}

          {membersLoading || restoring ? (
            <View
              align="center"
              gap={2}
              padding={6}
              attributes={{ role: "status" }}
              className="homestead-status-card"
            >
              <Loader ariaLabel="Loading family members" />
              <Text color="neutral-faded">Loading the house&hellip;</Text>
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
            <>
              {!selectedMember && (
                <ChildSelector members={members} onSelect={selectMember} />
              )}

              {selectedMember && switchOpen && (
                <ChildSelector
                  members={members}
                  selectedId={selectedMember.id}
                  onSelect={selectMember}
                  onCancel={() => setSwitchOpen(false)}
                />
              )}

              {firstTimePicker && !switchOpen && (
                <ThemePicker
                  themes={catalog.themes}
                  childName={selectedMember?.display_name ?? "this child"}
                  selectedId={themeId}
                  busy={themeBusy}
                  error={themeError}
                  onSelect={saveTheme}
                  onRetry={
                    failedThemeId
                      ? () => void saveTheme(failedThemeId)
                      : undefined
                  }
                />
              )}

              {!firstTimePicker && !switchOpen && (
                <View className="assignment-stack">
                  {assignmentStatus === "idle" && (
                    <Alert color="neutral" title="Select a child">
                      Choose a family member above to see this week&rsquo;s chore.
                    </Alert>
                  )}

                  {assignmentStatus === "loading" && (
                    <View
                      align="center"
                      gap={2}
                      padding={6}
                      attributes={{ role: "status" }}
                      className="homestead-status-card"
                    >
                      <Loader ariaLabel="Loading chore assignment" />
                      <Text color="neutral-faded">
                        Loading this week&rsquo;s chore&hellip;
                      </Text>
                    </View>
                  )}

                  {assignmentStatus === "missing" && (
                    <Alert color="neutral" title="No chore assigned this week">
                      {selectedMember?.display_name ?? "This family member"} does
                      not have a chore assigned for this week yet. An
                      administrator may need to generate the weekly assignments.
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
                      className="homestead-assignment-card"
                    >
                      <View gap={4}>
                        <div className="assignment-heading-row">
                          <div>
                            <div className="section-kicker">
                              This week&rsquo;s chore
                            </div>
                            <Text
                              as="h2"
                              variant="headline-2"
                              attributes={{ id: "assignment-heading" }}
                              className="assignment-chore-name"
                            >
                              {assignment.chore_name}
                            </Text>
                            <Text
                              variant="caption-1"
                              color="neutral-faded"
                              className="assignment-week"
                            >
                              Week of {formatDate(assignment.week_start)} &ndash;{" "}
                              {formatDate(assignment.week_end)}
                            </Text>
                            {assignment.chore_description && (
                              <Text className="assignment-description">
                                {assignment.chore_description}
                              </Text>
                            )}
                          </div>
                          <span className="week-stamp">
                            Week {isoWeekNumber(assignment.week_start)}
                          </span>
                        </div>

                        <Divider />

                        <div className="progress-block">
                          <div className="progress-row">
                            <span>Today</span>
                            <strong>
                              {completedCount} of {itemCount} done
                            </strong>
                          </div>
                          <div
                            className="progress-segments"
                            aria-hidden="true"
                          >
                            {assignment.checklist_items.map((item) => (
                              <i
                                key={item.id}
                                className={item.is_completed ? "on" : undefined}
                              />
                            ))}
                          </div>
                        </div>

                        {assignment.checklist_items.length === 0 ? (
                          <Alert color="warning" title="No checklist items">
                            This chore does not have any checklist items yet.
                          </Alert>
                        ) : (
                          <View
                            as="ol"
                            gap={2}
                            attributes={{ "aria-label": "Today's checklist" }}
                            className="homestead-checklist"
                          >
                            {assignment.checklist_items.map((item) => (
                              <View.Item as="li" key={item.id}>
                                <Checkbox
                                  name={"checklist-item-" + item.id}
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
                          <Alert
                            color="critical"
                            title="Couldn't save that change"
                          >
                            {saveError}
                          </Alert>
                        )}

                        <View
                          gap={2}
                          attributes={{ "aria-live": "polite" }}
                          className="completion-status"
                        >
                          {assignment.is_complete ? (
                            <div className="all-done-stamp" role="status">
                              <span>All done for today</span>
                              <strong>Every item on this chore is complete.</strong>
                            </div>
                          ) : (
                            <Text weight="medium" color="neutral-faded">
                              {completedCount} of {itemCount} complete today
                            </Text>
                          )}
                        </View>
                      </View>
                    </Card>
                  )}

                  {selectedMember && (
                    <View gap={3} paddingTop={4} className="history-wrap">
                      <div className="history-heading-row">
                        <h2>Past chores</h2>
                        <Button
                          variant="outline"
                          onClick={() => setHistoryOpen((open) => !open)}
                        >
                          {historyOpen ? "Hide history" : "View history"}
                        </Button>
                      </div>
                      {historyOpen && (
                        <FamilyCompletionHistory
                          key={selectedMember.id}
                          familyMemberId={selectedMember.id}
                          displayName={selectedMember.display_name}
                        />
                      )}
                    </View>
                  )}
                </View>
              )}
            </>
          )}
        </main>
      </Container>
    </ThemeScope>
  );
}