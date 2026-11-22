import { ApiError, apiRequest } from "../api/client";

export type FamilyMember = {
  id: number;
  display_name: string;
  is_active: boolean;
};

export type ManagedChecklistItem = {
  id: number;
  label: string;
  position: number;
  is_active: boolean;
};

export type ManagedChore = {
  id: number;
  name: string;
  description: string;
  is_active: boolean;
  checklist_items: ManagedChecklistItem[];
};

export function isUnauthorized(reason: unknown): boolean {
  return reason instanceof ApiError && reason.status === 401;
}

export function listFamilyMembers(): Promise<FamilyMember[]> {
  return apiRequest<FamilyMember[]>("/family-members");
}

export function createFamilyMember(args: {
  displayName: string;
  isActive: boolean;
}): Promise<FamilyMember> {
  return apiRequest<FamilyMember>("/family-members", {
    method: "POST",
    body: JSON.stringify({
      display_name: args.displayName,
      is_active: args.isActive,
    }),
  });
}

export function updateFamilyMember(
  familyMemberId: number,
  changes: { display_name?: string; is_active?: boolean },
): Promise<FamilyMember> {
  return apiRequest<FamilyMember>(`/family-members/${familyMemberId}`, {
    method: "PATCH",
    body: JSON.stringify(changes),
  });
}

export function listChores(): Promise<ManagedChore[]> {
  return apiRequest<ManagedChore[]>("/chores");
}

export function createChore(args: {
  name: string;
  description: string;
}): Promise<ManagedChore> {
  return apiRequest<ManagedChore>("/chores", {
    method: "POST",
    body: JSON.stringify(args),
  });
}

export function updateChore(
  choreId: number,
  changes: { name?: string; description?: string; is_active?: boolean },
): Promise<ManagedChore> {
  return apiRequest<ManagedChore>(`/chores/${choreId}`, {
    method: "PATCH",
    body: JSON.stringify(changes),
  });
}

export function addChecklistItem(
  choreId: number,
  label: string,
): Promise<ManagedChecklistItem> {
  return apiRequest<ManagedChecklistItem>(`/chores/${choreId}/checklist-items`, {
    method: "POST",
    body: JSON.stringify({ label }),
  });
}

export function updateChecklistItem(
  choreId: number,
  itemId: number,
  changes: { label?: string; is_active?: boolean },
): Promise<ManagedChecklistItem> {
  return apiRequest<ManagedChecklistItem>(
    `/chores/${choreId}/checklist-items/${itemId}`,
    {
      method: "PATCH",
      body: JSON.stringify(changes),
    },
  );
}

export function deleteChecklistItem(
  choreId: number,
  itemId: number,
): Promise<void> {
  return apiRequest<void>(`/chores/${choreId}/checklist-items/${itemId}`, {
    method: "DELETE",
  });
}

export function reorderChecklist(
  choreId: number,
  orderedItemIds: number[],
): Promise<ManagedChore> {
  return apiRequest<ManagedChore>(`/chores/${choreId}/checklist-order`, {
    method: "PUT",
    body: JSON.stringify({ ordered_item_ids: orderedItemIds }),
  });
}

export type WeeklyReportSummary = {
  family_member_count: number;
  total_days: number;
  completed_days: number;
  incomplete_days: number;
};

export type WeeklyReportListItem = {
  id: number;
  week_start: string;
  week_end: string;
  generated_at: string;
  summary: WeeklyReportSummary;
};

export type ReportDayStatus = "complete" | "incomplete";

export type WeeklyReportDay = {
  date: string;
  status: ReportDayStatus;
};

export type WeeklyReportEntry = {
  id: number;
  family_member_name: string;
  chore_name: string;
  chore_description: string;
  completed_days: number;
  incomplete_days: number;
  days: WeeklyReportDay[];
};

export type WeeklyReportDetail = WeeklyReportListItem & {
  entries: WeeklyReportEntry[];
  total: number;
  limit: number;
  offset: number;
};

export function listReports(): Promise<WeeklyReportListItem[]> {
  return apiRequest<WeeklyReportListItem[]>("/reports");
}

export function getReport(
  weekStart: string,
  options: {
    limit?: number;
    offset?: number;
    signal?: AbortSignal;
  } = {},
): Promise<WeeklyReportDetail> {
  const params = new URLSearchParams({
    limit: String(options.limit ?? 25),
    offset: String(options.offset ?? 0),
  });
  return apiRequest<WeeklyReportDetail>(
    `/reports/${encodeURIComponent(weekStart)}?${params}`,
    { signal: options.signal },
  );
}
