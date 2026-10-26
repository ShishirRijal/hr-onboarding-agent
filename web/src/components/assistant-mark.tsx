const WAVE = "q3 -2 6 0 t6 0 t6 0 t6 0 t6 0 t6 0 t6 0 t6 0";

// Three waves across a sea-blue tile. They flow while the assistant is working and
// settle when the answer is complete.
export function AssistantMark({ active }: { active: boolean }) {
  return (
    <span
      className={`mark grid size-7 shrink-0 place-items-center overflow-hidden rounded-lg bg-baltic ${
        active ? "is-active" : ""
      }`}
      aria-hidden="true"
    >
      <svg viewBox="0 0 24 24" className="size-7">
        <g fill="none" stroke="white" strokeWidth="1.6" strokeLinecap="round">
          <path className="mark-wave" d={`M0 8 ${WAVE}`} opacity="0.55" />
          <path className="mark-wave" d={`M0 12 ${WAVE}`} />
          <path className="mark-wave" d={`M0 16 ${WAVE}`} opacity="0.75" />
        </g>
      </svg>
    </span>
  );
}
