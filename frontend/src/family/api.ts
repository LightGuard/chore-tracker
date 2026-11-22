import { apiRequest } from "../api/client";

export type FamilyMember = {
  id: number;
  display_name: string;
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
