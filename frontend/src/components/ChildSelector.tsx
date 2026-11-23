import type { FamilyMember } from "../family/api";

type ChildSelectorProps = {
  members: FamilyMember[];
  selectedId?: number;
  onSelect: (member: FamilyMember) => void;
  onCancel?: () => void;
  busyId?: number;
};

export function ChildSelector({
  members,
  selectedId,
  onSelect,
  onCancel,
  busyId,
}: ChildSelectorProps) {
  return (
    <section className="child-selector-panel" aria-labelledby="child-selector-heading">
      <div className="section-heading-row">
        <div>
          <div className="section-kicker">Who&rsquo;s doing chores?</div>
          <h2 id="child-selector-heading">Choose a child</h2>
          <p className="section-lede">
            Pick your name to see this week&rsquo;s chore. You are not signing in.
          </p>
        </div>
        {onCancel && (
          <button type="button" className="text-button" onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>
      <div className="child-grid">
        {members.map((member) => (
          <button
            key={member.id}
            type="button"
            className={`child-option${member.id === selectedId ? " selected" : ""}`}
            aria-pressed={member.id === selectedId}
            disabled={busyId !== undefined}
            onClick={() => onSelect(member)}
          >
            <span className="child-monogram" aria-hidden="true">
              {member.display_name.slice(0, 1).toUpperCase()}
            </span>
            <span className="child-name">{member.display_name}</span>
            {member.id === selectedId && (
              <span className="child-current">Current</span>
            )}
          </button>
        ))}
      </div>
    </section>
  );
}
