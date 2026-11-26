import { useCallback, useEffect, useId, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Loader,
  Text,
  View,
} from "reshaped";
import { ApiError } from "../api/client";
import {
  claimChore,
  getAvailableChores,
  getClaimedChores,
  setClaimCompletion,
  type AvailableChore,
  type ClaimableChores,
  type ClaimedChores,
  type DailyChoreClaim,
} from "./api";

const LOAD_ERROR =
  "We couldn't load the extra chores. Check your connection and try again.";
const CLAIM_ERROR =
  "We couldn't claim that chore. Check your connection and try again.";
const COMPLETION_ERROR =
  "We couldn't save that change. Check your connection and try again.";

type Status = "loading" | "ready" | "error";

function messageFor(reason: unknown, fallback: string): string {
  return reason instanceof ApiError ? reason.message : fallback;
}

const dayFormatter = new Intl.DateTimeFormat("en", {
  month: "short",
  day: "numeric",
  timeZone: "UTC",
});

function formatClaimDate(value: string): string {
  const [year, month, day] = value.split("-").map(Number);
  return dayFormatter.format(new Date(Date.UTC(year, month - 1, day)));
}

type Props = {
  familyMemberId: number;
  onStatsChange?: () => void;
};

export function ChoreClaims({ familyMemberId, onStatsChange }: Props) {
  const headingId = useId();
  const availableHeadingId = useId();
  const claimedHeadingId = useId();

  const [available, setAvailable] = useState<AvailableChore[]>([]);
  const [claims, setClaims] = useState<DailyChoreClaim[]>([]);
  const [claimDate, setClaimDate] = useState("");
  const [status, setStatus] = useState<Status>("loading");
  const [loadError, setLoadError] = useState("");
  const [conflict, setConflict] = useState("");
  const [actionError, setActionError] = useState("");
  const [busyChoreId, setBusyChoreId] = useState<number | null>(null);
  const [completingId, setCompletingId] = useState<number | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const applyData = useCallback(
    (avail: ClaimableChores, claimed: ClaimedChores) => {
      setAvailable(avail.chores);
      setClaimDate(avail.claim_date);
      setClaims(claimed.claims);
    },
    [],
  );

  useEffect(() => {
    const controller = new AbortController();
    setStatus("loading");
    setLoadError("");
    setConflict("");
    setActionError("");

    Promise.all([
      getAvailableChores(familyMemberId, controller.signal),
      getClaimedChores(familyMemberId, controller.signal),
    ])
      .then(([avail, claimed]) => {
        if (controller.signal.aborted) return;
        applyData(avail, claimed);
        setStatus("ready");
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setLoadError(messageFor(reason, LOAD_ERROR));
        setStatus("error");
      });

    return () => controller.abort();
  }, [familyMemberId, reloadKey, applyData]);

  const refresh = useCallback(async () => {
    try {
      const [avail, claimed] = await Promise.all([
        getAvailableChores(familyMemberId),
        getClaimedChores(familyMemberId),
      ]);
      applyData(avail, claimed);
    } catch {
      // Keep the current lists if the refresh itself fails.
    }
  }, [familyMemberId, applyData]);

  async function handleClaim(choreId: number) {
    if (busyChoreId !== null) return;
    setBusyChoreId(choreId);
    setConflict("");
    setActionError("");
    try {
      await claimChore({ familyMemberId, choreId });
      await refresh();
      onStatsChange?.();
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 409) {
        setConflict(
          `That chore is no longer available to claim. Here's the updated list. ${reason.message}`,
        );
        await refresh();
      } else {
        setActionError(messageFor(reason, CLAIM_ERROR));
      }
    } finally {
      setBusyChoreId(null);
    }
  }

  async function handleCompletion(claim: DailyChoreClaim, isCompleted: boolean) {
    if (completingId !== null) return;
    setCompletingId(claim.id);
    setActionError("");
    try {
      await setClaimCompletion({
        familyMemberId,
        claimId: claim.id,
        isCompleted,
      });
      setClaims((current) =>
        current.map((entry) =>
          entry.id === claim.id
            ? { ...entry, is_completed: isCompleted }
            : entry,
        ),
      );
      onStatsChange?.();
    } catch (reason) {
      setActionError(messageFor(reason, COMPLETION_ERROR));
    } finally {
      setCompletingId(null);
    }
  }

  return (
    <View
      as="section"
      gap={3}
      className="chore-claims"
      attributes={{ "aria-labelledby": headingId }}
    >
      <View gap={1}>
        <div className="section-kicker">One-day extras</div>
        <Text
          as="h2"
          variant="headline-2"
          attributes={{ id: headingId }}
        >
          Extra chores today
        </Text>
        <Text color="neutral-faded">
          One-day extras for today only &mdash; these don&apos;t change your
          weekly chore. These are additional chores just for today, not
          recurring assignments. After 8:00 pm, a chore another child hasn&apos;t
          finished also becomes available to claim.
        </Text>
      </View>

      {conflict && (
        <Alert color="warning" title="Couldn't claim that chore">
          {conflict}
        </Alert>
      )}

      {actionError && (
        <Alert color="critical" title="Couldn't save that change">
          {actionError}
        </Alert>
      )}

      <Card
        as="section"
        padding={4}
        borderRadius="large"
        className="chore-claims-card"
        attributes={{ "aria-labelledby": availableHeadingId }}
      >
        <View gap={3}>
          <View gap={1}>
            <Text
              as="h3"
              variant="headline-3"
              attributes={{ id: availableHeadingId }}
            >
              Available today
            </Text>
            {claimDate && (
              <Text variant="caption-1" color="neutral-faded">
                For {formatClaimDate(claimDate)}
              </Text>
            )}
          </View>

          {status === "loading" && (
            <View
              align="center"
              gap={2}
              padding={4}
              attributes={{ role: "status" }}
              className="chore-claims-status"
            >
              <Loader ariaLabel="Loading available chores" />
              <Text color="neutral-faded">Loading extra chores&hellip;</Text>
            </View>
          )}

          {status === "error" && (
            <Alert
              color="critical"
              title="Extra chores are unavailable"
              actionsSlot={
                <Button
                  variant="outline"
                  onClick={() => setReloadKey((value) => value + 1)}
                >
                  Try again
                </Button>
              }
            >
              {loadError}
            </Alert>
          )}

          {status === "ready" && available.length === 0 && (
            <Alert color="neutral" title="Nothing to claim">
              No extra chores available right now.
            </Alert>
          )}

          {status === "ready" && available.length > 0 && (
            <View
              as="ul"
              gap={2}
              className="chore-claims-list"
              attributes={{ "aria-label": "Available extra chores" }}
            >
              {available.map((chore) => (
                <View.Item as="li" key={chore.id}>
                  <div className="chore-claims-item">
                    <div className="chore-claims-copy">
                      <Text weight="medium">{chore.name}</Text>
                      {chore.description && (
                        <Text variant="caption-1" color="neutral-faded">
                          {chore.description}
                        </Text>
                      )}
                      <View direction="row" gap={2} wrap align="center">
                        <Text variant="caption-1" color="neutral-faded">
                          Weight {chore.weight}
                        </Text>
                        {chore.assigned_to !== null && (
                          <Text
                            variant="caption-1"
                            className="chore-claims-note"
                          >
                            {chore.assigned_to}&apos;s unfinished chore
                          </Text>
                        )}
                      </View>
                    </div>
                    <Button
                      variant="solid"
                      disabled={busyChoreId !== null}
                      onClick={() => void handleClaim(chore.id)}
                    >
                      Claim
                    </Button>
                  </div>
                </View.Item>
              ))}
            </View>
          )}
        </View>
      </Card>

      <Card
        as="section"
        padding={4}
        borderRadius="large"
        className="chore-claims-card"
        attributes={{ "aria-labelledby": claimedHeadingId }}
      >
        <View gap={3}>
          <Text
            as="h3"
            variant="headline-3"
            attributes={{ id: claimedHeadingId }}
          >
            Claimed today
          </Text>

          {status !== "ready" && (
            <Alert color="neutral" title="Claimed chores">
              Your claimed chores will appear here once they load.
            </Alert>
          )}

          {status === "ready" && claims.length === 0 && (
            <Alert color="neutral" title="No claims yet">
              You haven&apos;t claimed any extra chores today.
            </Alert>
          )}

          {status === "ready" && claims.length > 0 && (
            <View
              as="ul"
              gap={2}
              className="chore-claims-list"
              attributes={{ "aria-label": "Claimed extra chores" }}
            >
              {claims.map((claim) => (
                <View.Item as="li" key={claim.id}>
                  <div className="chore-claims-item">
                    <div className="chore-claims-copy">
                      <Text weight="medium">{claim.chore_name}</Text>
                      {claim.chore_description && (
                        <Text variant="caption-1" color="neutral-faded">
                          {claim.chore_description}
                        </Text>
                      )}
                    </div>
                    <Checkbox
                      name={"claim-" + claim.id}
                      value={String(claim.id)}
                      checked={claim.is_completed}
                      disabled={completingId !== null}
                      onChange={({ checked }) =>
                        void handleCompletion(claim, checked)
                      }
                    >
                      Mark done
                    </Checkbox>
                  </div>
                </View.Item>
              ))}
            </View>
          )}
        </View>
      </Card>
    </View>
  );
}
