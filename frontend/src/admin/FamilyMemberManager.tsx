import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  FormControl,
  Loader,
  Switch,
  Text,
  TextField,
  View,
} from "reshaped";
import { ApiError } from "../api/client";
import {
  createFamilyMember,
  isUnauthorized,
  listFamilyMembers,
  updateFamilyMember,
  type FamilyMember,
} from "./api";

type Props = {
  onSessionExpired: () => void;
};

function errorMessage(reason: unknown, fallback: string): string {
  return reason instanceof ApiError ? reason.message : fallback;
}

export function FamilyMemberManager({ onSessionExpired }: Props) {
  const [members, setMembers] = useState<FamilyMember[]>([]);
  const [displayName, setDisplayName] = useState("");
  const [newMemberActive, setNewMemberActive] = useState(true);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      setMembers(await listFamilyMembers());
    } catch (reason) {
      if (isUnauthorized(reason)) {
        onSessionExpired();
        return;
      }
      setError(errorMessage(reason, "Family members could not be loaded."));
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
      setError(errorMessage(reason, "The family member update failed."));
    } finally {
      setBusy(false);
    }
  }

  async function handleCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleaned = displayName.trim();
    if (!cleaned) {
      setError("Display name must not be blank.");
      return;
    }
    await run(async () => {
      await createFamilyMember({
        displayName: cleaned,
        isActive: newMemberActive,
      });
      setDisplayName("");
      setNewMemberActive(true);
    });
  }

  async function handleUpdate(
    member: FamilyMember,
    changes: { display_name: string; is_active: boolean },
  ) {
    const cleaned = changes.display_name.trim();
    if (!cleaned) {
      setError("Display name must not be blank.");
      return;
    }
    await run(() =>
      updateFamilyMember(member.id, {
        display_name: cleaned,
        is_active: changes.is_active,
      }),
    );
  }

  return (
    <Card
      as="section"
      padding={5}
      borderRadius="large"
      className="admin-panel admin-family-panel"
      attributes={{
        "aria-labelledby": "family-members-heading",
        id: "family-members",
      }}
    >
      <View gap={4}>
        <View gap={1}>
          <Text
            as="h2"
            variant="headline-2"
            attributes={{ id: "family-members-heading" }}
          >
            Family members
          </Text>
          <Text color="neutral-faded">
            Manage the profiles available in the child selector. Inactive
            profiles keep their historical assignments and completion records.
          </Text>
        </View>

        {error && (
          <Alert color="critical" title="Family member update failed">
            {error}
          </Alert>
        )}

        <div className="admin-split admin-family-grid">
          <Card
            as="section"
            padding={4}
            borderRadius="medium"
            className="admin-subpanel admin-form-panel"
          >
            <form onSubmit={(event) => void handleCreate(event)}>
              <View gap={3}>
                <Text as="h3" variant="headline-3">
                  Add a family member
                </Text>
                <FormControl id="new-family-member-name">
                  <FormControl.Label>New family member name</FormControl.Label>
                  <TextField
                    name="display_name"
                    value={displayName}
                    onChange={({ value }) => setDisplayName(value)}
                    inputAttributes={{ required: true }}
                  />
                </FormControl>
                <Switch
                  name="new-family-member-active"
                  checked={newMemberActive}
                  onChange={({ checked }) => setNewMemberActive(checked)}
                >
                  Active
                </Switch>
                <View direction="row">
                  <Button type="submit" disabled={busy}>
                    Add family member
                  </Button>
                </View>
              </View>
            </form>
          </Card>

          <div className="admin-list-panel">
            <div className="admin-list-heading">
              <Text as="h3" variant="headline-3">
                Household roster
              </Text>
            </div>

            {loading ? (
              <View
                align="center"
                gap={2}
                padding={4}
                attributes={{ role: "status" }}
              >
                <Loader ariaLabel="Loading family members" />
                <Text color="neutral-faded">Loading family members…</Text>
              </View>
            ) : members.length === 0 ? (
              <Alert color="neutral" title="No family members yet">
                Add the first family member using the form above.
              </Alert>
            ) : (
              <div className="admin-member-grid">
                {members.map((member) => (
                  <FamilyMemberRow
                    key={`${member.id}-${member.display_name}-${member.is_active}`}
                    member={member}
                    busy={busy}
                    onSave={(changes) => handleUpdate(member, changes)}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      </View>
    </Card>
  );
}

type RowProps = {
  member: FamilyMember;
  busy: boolean;
  onSave: (changes: { display_name: string; is_active: boolean }) => void;
};

function FamilyMemberRow({ member, busy, onSave }: RowProps) {
  const [displayName, setDisplayName] = useState(member.display_name);
  const [isActive, setIsActive] = useState(member.is_active);

  return (
    <Card
      as="article"
      padding={4}
      borderRadius="medium"
      className="admin-subpanel admin-member-card"
      attributes={{ "aria-label": `Family member ${member.display_name}` }}
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
            {member.display_name}
          </Text>
          <Badge color={isActive ? "positive" : "neutral"} variant="faded">
            {isActive ? "Active" : "Inactive"}
          </Badge>
        </View>
        <View gap={2}>
          <FormControl id={`family-member-name-${member.id}`}>
            <FormControl.Label>Display name</FormControl.Label>
            <TextField
              name="display_name"
              value={displayName}
              onChange={({ value }) => setDisplayName(value)}
              inputAttributes={{ required: true }}
            />
          </FormControl>
          <Switch
            name={`family-member-active-${member.id}`}
            checked={isActive}
            onChange={({ checked }) => setIsActive(checked)}
          >
            Active
          </Switch>
          <View direction="row">
            <Button
              disabled={busy}
              onClick={() =>
                onSave({
                  display_name: displayName,
                  is_active: isActive,
                })
              }
            >
              Save family member
            </Button>
          </View>
        </View>
      </View>
    </Card>
  );
}
