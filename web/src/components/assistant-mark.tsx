const WAVE = "q3 -2 6 0 t6 0 t6 0 t6 0 t6 0 t6 0 t6 0 t6 0";

// Three waves across a sea-blue tile. While the assistant works they roll and a ripple
// spreads from the tile; on the latest reply they keep drifting slowly; older replies
// stay still.
export function AssistantMark({ state }: { state: "working" | "idle" | "still" }) {
  return (
    <span className={`mark relative size-7 shrink-0 is-${state}`} aria-hidden="true">
      <span className="grid size-7 place-items-center overflow-hidden rounded-lg bg-baltic">
        <svg viewBox="0 0 24 24" className="size-7">
          <g fill="none" stroke="white" strokeWidth="1.6" strokeLinecap="round">
            <g className="mark-swell">
              <path className="mark-wave" d={`M0 8 ${WAVE}`} opacity="0.55" />
            </g>
            <g className="mark-swell">
              <path className="mark-wave" d={`M0 12 ${WAVE}`} />
            </g>
            <g className="mark-swell">
              <path className="mark-wave" d={`M0 16 ${WAVE}`} opacity="0.75" />
            </g>
          </g>
        </svg>
      </span>
    </span>
  );
}
