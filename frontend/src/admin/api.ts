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
