import { apiRequest } from "../api/client";

export type FamilyMember = {
  id: number;
  display_name: string;
  theme_id: string | null;
};

export type ChecklistItem = {
  id: number;
  label: string;
  position: number;
  is_completed: boolean;
};

export type CurrentAssignment = {
  id: number;
  family_member_id: number;
  week_start: string;
  week_end: string;
  chore_name: string;
  chore_description: string;
  today: string;
  checklist_items: ChecklistItem[];
  is_complete: boolean;
};

export type ChecklistCompletionResult = {
  assignment_id: number;
  completion_date: string;
  checklist_item: Omit<ChecklistItem, "position">;
  is_complete: boolean;
};

export type CompletionStatus = "complete" | "incomplete" | "not_yet_recorded";

export type CompletionHistoryRecord = {
  assignment_id: number;
  week_start: string;
  week_end: string;
  chore_name: string;
  chore_description: string;
  completion_date: string;
  completion_status: CompletionStatus;
};

export type CompletionHistoryPage = {
  items: CompletionHistoryRecord[];
  total: number;
  limit: number;
  offset: number;
};

export type DerivedStatsDayState = "complete" | "incomplete" | "not_recorded";

export type DerivedStatsDay = {
  date: string;
  completed_checklist_items: number;
  total_checklist_items: number;
  state: DerivedStatsDayState;
};

export type DerivedStatsStanding = {
  family_member_id: number;
  display_name: string;
  completed_checklist_items: number;
  complete_days: number;
  current_streak: number;
};

export type DerivedStats = {
  family_member_id: number;
  display_name: string;
  as_of: string;
  timezone: string;
  lifetime: {
    completed_checklist_items: number;
    complete_days: number;
    current_streak: number;
  };
  current_week: {
    week_start: string;
    week_end: string;
    completed_checklist_items: number;
    complete_days: number;
    days: DerivedStatsDay[];
  };
  household: {
    active_players: number;
    weekly_standings: DerivedStatsStanding[];
  };
};

export function getActiveFamilyMembers(
  signal?: AbortSignal,
): Promise<FamilyMember[]> {
  return apiRequest<FamilyMember[]>("/family-members/active", { signal });
}

export function getCurrentAssignment(
  familyMemberId: number,
  signal?: AbortSignal,
): Promise<CurrentAssignment> {
  return apiRequest<CurrentAssignment>(
    `/family-members/${familyMemberId}/current-assignment`,
    { signal },
  );
}

export function getCompletionHistory(
  familyMemberId: number,
  options: {
    limit?: number;
    offset?: number;
    signal?: AbortSignal;
  } = {},
): Promise<CompletionHistoryPage> {
  const params = new URLSearchParams({
    limit: String(options.limit ?? 50),
    offset: String(options.offset ?? 0),
  });
  return apiRequest<CompletionHistoryPage>(
    `/family-members/${familyMemberId}/completion-history?${params}`,
    { signal: options.signal },
  );
}

export function setChecklistItemCompletion(args: {
  familyMemberId: number;
  assignmentId: number;
  checklistItemId: number;
  completionDate: string;
  isCompleted: boolean;
}): Promise<ChecklistCompletionResult> {
  return apiRequest<ChecklistCompletionResult>(
    `/family-members/${args.familyMemberId}/assignments/${args.assignmentId}` +
      `/checklist-items/${args.checklistItemId}/completion`,
    {
      method: "PUT",
      body: JSON.stringify({
        completion_date: args.completionDate,
        is_completed: args.isCompleted,
      }),
    },
  );
}

export function getDerivedStats(
  familyMemberId: number,
  signal?: AbortSignal,
): Promise<DerivedStats> {
  return apiRequest<DerivedStats>(
    `/family-members/${familyMemberId}/derived-stats`,
    { signal },
  );
}
