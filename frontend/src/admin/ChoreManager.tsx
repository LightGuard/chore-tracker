import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  FormControl,
  Loader,
  Switch,
  Text,
  TextArea,
  TextField,
  View,
} from "reshaped";
import { ApiError } from "../api/client";
import {
  addChecklistItem,
  createChore,
  deleteChecklistItem,
  isUnauthorized,
  listChores,
  reorderChecklist,
  updateChecklistItem,
  updateChore,
  type ManagedChecklistItem,
  type ManagedChore,
} from "./api";

type Props = {
  onSessionExpired: () => void;
};

function errorMessage(reason: unknown, fallback: string): string {
  return reason instanceof ApiError ? reason.message : fallback;
}

export function ChoreManager({ onSessionExpired }: Props) {
  const [chores, setChores] = useState<ManagedChore[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      setChores(await listChores());
    } catch (reason) {
      if (isUnauthorized(reason)) {
        onSessionExpired();
        return;
      }
      setError(errorMessage(reason, "Chores could not be loaded."));
    } finally {
      setLoading(false);
    }
  }, [onSessionExpired]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function run(operation: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await operation();
      await refresh();
    } catch (reason) {
      if (isUnauthorized(reason)) {
        onSessionExpired();
        return;
      }
      setError(errorMessage(reason, "The chore update failed."));
    } finally {
      setBusy(false);
    }
  }

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleaned = name.trim();
    if (!cleaned) {
      setError("Chore name must not be blank.");
      return;
    }
    await run(async () => {
      await createChore({ name: cleaned, description: description.trim() });
      setName("");
      setDescription("");
    });
  }

  async function saveChore(
    chore: ManagedChore,
    changes: { name: string; description: string },
  ) {
    const cleaned = changes.name.trim();
    if (!cleaned) {
      setError("Chore name must not be blank.");
      return;
    }
    await run(() =>
      updateChore(chore.id, {
        name: cleaned,
        description: changes.description.trim(),
      }),
    );
  }

  async function toggleChore(chore: ManagedChore) {
    await run(() => updateChore(chore.id, { is_active: !chore.is_active }));
  }

  async function addItem(chore: ManagedChore, label: string) {
    const cleaned = label.trim();
    if (!cleaned) {
      setError("Checklist label must not be blank.");
      return;
    }
    await run(() => addChecklistItem(chore.id, cleaned));
  }

  async function updateItem(
    chore: ManagedChore,
    item: ManagedChecklistItem,
    changes: { label?: string; is_active?: boolean },
  ) {
    const cleaned = changes.label?.trim();
    if (cleaned !== undefined && !cleaned) {
      setError("Checklist label must not be blank.");
      return;
    }
    await run(() =>
      updateChecklistItem(chore.id, item.id, {
        ...(cleaned !== undefined ? { label: cleaned } : {}),
        ...(changes.is_active !== undefined
          ? { is_active: changes.is_active }
          : {}),
      }),
    );
  }

  async function removeItem(chore: ManagedChore, item: ManagedChecklistItem) {
    await run(() => deleteChecklistItem(chore.id, item.id));
  }

  async function moveItem(chore: ManagedChore, index: number, offset: number) {
    const target = index + offset;
    if (target < 0 || target >= chore.checklist_items.length) return;
    const ordered = chore.checklist_items.map((item) => item.id);
    [ordered[index], ordered[target]] = [ordered[target], ordered[index]];
    await run(() => reorderChecklist(chore.id, ordered));
  }

  return (
    <Card
      as="section"
      padding={5}
      borderRadius="large"
      attributes={{ "aria-labelledby": "chore-catalog-heading" }}
    >
      <View gap={4}>
        <View gap={1}>
          <Text
            as="h2"
            variant="headline-2"
            attributes={{ id: "chore-catalog-heading" }}
          >
            Chore catalog
          </Text>
          <Text color="neutral-faded">
            New chores start inactive. Add at least one active checklist item
            before activating a chore. Catalog edits never rewrite historical
            assignments.
          </Text>
        </View>

        {error && (
          <Alert color="critical" title="Chore update failed">
            {error}
          </Alert>
        )}

        <Card as="section" padding={4} borderRadius="medium">
          <form onSubmit={(event) => void handleCreate(event)}>
            <View gap={3}>
              <Text as="h3" variant="headline-3">
                Add a chore
              </Text>
              <FormControl id="new-chore-name">
                <FormControl.Label>New chore name</FormControl.Label>
                <TextField
                  name="name"
                  value={name}
                  onChange={({ value }) => setName(value)}
                  inputAttributes={{ required: true }}
                />
              </FormControl>
              <FormControl id="new-chore-description">
                <FormControl.Label>New chore description</FormControl.Label>
                <TextArea
                  name="description"
                  value={description}
                  onChange={({ value }) => setDescription(value)}
                  resize="auto"
                />
              </FormControl>
              <View direction="row">
                <Button type="submit" disabled={busy}>
                  Create chore
                </Button>
              </View>
            </View>
          </form>
        </Card>

        {loading ? (
          <View align="center" gap={2} padding={4} attributes={{ role: "status" }}>
            <Loader ariaLabel="Loading chores" />
            <Text color="neutral-faded">Loading chores…</Text>
          </View>
        ) : chores.length === 0 ? (
          <Alert color="neutral" title="No chores yet">
            Add the first chore using the form above.
          </Alert>
        ) : (
          <View gap={3}>
            {chores.map((chore) => (
              <ChoreCard
                key={chore.id}
                chore={chore}
                busy={busy}
                onSave={(changes) => void saveChore(chore, changes)}
                onToggle={() => void toggleChore(chore)}
                onAddItem={(label) => void addItem(chore, label)}
                onUpdateItem={(item, changes) =>
                  void updateItem(chore, item, changes)
                }
                onRemoveItem={(item) => void removeItem(chore, item)}
                onMoveItem={(index, offset) =>
                  void moveItem(chore, index, offset)
                }
              />
            ))}
          </View>
        )}
      </View>
    </Card>
  );
}

type ChoreCardProps = {
  chore: ManagedChore;
  busy: boolean;
  onSave: (changes: { name: string; description: string }) => void;
  onToggle: () => void;
  onAddItem: (label: string) => void;
  onUpdateItem: (
    item: ManagedChecklistItem,
    changes: { label?: string; is_active?: boolean },
  ) => void;
  onRemoveItem: (item: ManagedChecklistItem) => void;
  onMoveItem: (index: number, offset: number) => void;
};

function ChoreCard({
  chore,
  busy,
  onSave,
  onToggle,
  onAddItem,
  onUpdateItem,
  onRemoveItem,
  onMoveItem,
}: ChoreCardProps) {
  const [name, setName] = useState(chore.name);
  const [description, setDescription] = useState(chore.description);
  const [newItemLabel, setNewItemLabel] = useState("");

  useEffect(() => setName(chore.name), [chore.name]);
  useEffect(() => setDescription(chore.description), [chore.description]);

  const activeItems = chore.checklist_items.filter((item) => item.is_active);

  return (
    <Card
      as="article"
      padding={4}
      borderRadius="medium"
      attributes={{ "aria-label": `Chore ${chore.name}` }}
    >
      <View gap={3}>
        <View
          direction="row"
          align="center"
          justify="space-between"
          gap={2}
          wrap
        >
          <Text as="h3" variant="headline-3">
            {chore.name}
          </Text>
          <Badge color={chore.is_active ? "positive" : "neutral"} variant="faded">
            {chore.is_active ? "Active" : "Inactive"}
          </Badge>
        </View>

        <View gap={2}>
          <FormControl id={`chore-name-${chore.id}`}>
            <FormControl.Label>Chore name</FormControl.Label>
            <TextField
              name="name"
              value={name}
              onChange={({ value }) => setName(value)}
            />
          </FormControl>
          <FormControl id={`chore-description-${chore.id}`}>
            <FormControl.Label>Description</FormControl.Label>
            <TextArea
              name="description"
              value={description}
              onChange={({ value }) => setDescription(value)}
              resize="auto"
            />
          </FormControl>
          <View direction="row" gap={2} wrap>
            <Button
              disabled={busy}
              onClick={() => onSave({ name, description })}
            >
              Save chore details
            </Button>
            <Button
              variant="outline"
              disabled={
                busy || (!chore.is_active && activeItems.length === 0)
              }
              onClick={onToggle}
            >
              {chore.is_active ? "Deactivate chore" : "Activate chore"}
            </Button>
          </View>
        </View>

        <FormControl id={`new-checklist-item-${chore.id}`}>
          <FormControl.Label>Add checklist item</FormControl.Label>
          <View direction="row" gap={2} align="end" wrap>
            <View grow>
              <TextField
                name="label"
                value={newItemLabel}
                onChange={({ value }) => setNewItemLabel(value)}
              />
            </View>
            <Button
              disabled={busy}
              onClick={() => {
                onAddItem(newItemLabel);
                setNewItemLabel("");
              }}
            >
              Add item
            </Button>
          </View>
        </FormControl>

        {chore.checklist_items.length === 0 ? (
          <Alert color="neutral" title="No checklist items">
            Add at least one checklist item before activating this chore.
          </Alert>
        ) : (
          <View
            as="ol"
            gap={2}
            attributes={{ "aria-label": `Checklist for ${chore.name}` }}
          >
            {chore.checklist_items.map((item, index) => (
              <ChecklistItemRow
                key={`${item.id}-${item.label}-${item.is_active}`}
                chore={chore}
                item={item}
                index={index}
                activeItemCount={activeItems.length}
                busy={busy}
                onSave={(label) => onUpdateItem(item, { label })}
                onToggle={(isActive) =>
                  onUpdateItem(item, { is_active: isActive })
                }
                onMove={(offset) => onMoveItem(index, offset)}
                onRemove={() => onRemoveItem(item)}
              />
            ))}
          </View>
        )}
      </View>
    </Card>
  );
}

type ChecklistRowProps = {
  chore: ManagedChore;
  item: ManagedChecklistItem;
  index: number;
  activeItemCount: number;
  busy: boolean;
  onSave: (label: string) => void;
  onToggle: (isActive: boolean) => void;
  onMove: (offset: number) => void;
  onRemove: () => void;
};

function ChecklistItemRow({
  chore,
  item,
  index,
  activeItemCount,
  busy,
  onSave,
  onToggle,
  onMove,
  onRemove,
}: ChecklistRowProps) {
  const [label, setLabel] = useState(item.label);

  useEffect(() => setLabel(item.label), [item.label]);

  const removeBlocked =
    chore.is_active && item.is_active && activeItemCount <= 1;

  return (
    <View.Item as="li" attributes={{ "aria-label": item.label }}>
      <Card padding={3} borderRadius="medium">
        <View gap={2}>
          <TextField
            name={`checklist-label-${item.id}`}
            value={label}
            onChange={({ value }) => setLabel(value)}
            inputAttributes={{
              "aria-label": `Checklist item ${index + 1} for ${chore.name}`,
            }}
          />
          <View direction="row" gap={2} align="center" wrap>
            <Button disabled={busy} onClick={() => onSave(label)}>
              Save item
            </Button>
            <Switch
              name={`checklist-active-${item.id}`}
              checked={item.is_active}
              onChange={({ checked }) => onToggle(checked)}
              size="small"
            >
              Active
            </Switch>
            <Button
              variant="outline"
              size="small"
              disabled={busy || index === 0}
              onClick={() => onMove(-1)}
            >
              Move up
            </Button>
            <Button
              variant="outline"
              size="small"
              disabled={
                busy || index === chore.checklist_items.length - 1
              }
              onClick={() => onMove(1)}
            >
              Move down
            </Button>
            <Button
              variant="ghost"
              color="critical"
              size="small"
              disabled={busy || removeBlocked}
              onClick={onRemove}
            >
              Remove
            </Button>
          </View>
        </View>
      </Card>
    </View.Item>
  );
}
