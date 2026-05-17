/* global React, Icon */
const { useState, useRef, useEffect, useMemo, useCallback } = React;

/* ------- Icons used inline (extra ones not in the bank) ------- */
const InlineIcon = ({ d, size = 14, stroke = 1.6 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={stroke} strokeLinecap="round" strokeLinejoin="round">
    {Array.isArray(d) ? d.map((p, i) => <path key={i} d={p}/>) : <path d={d}/>}
  </svg>
);
const I = {
  chevron: (p) => <InlineIcon d="M9 6l6 6-6 6" {...p}/>,
  plus: (p) => <InlineIcon d={["M12 5v14","M5 12h14"]} {...p}/>,
  pencil: (p) => <InlineIcon d={["M12 20h9","M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4z"]} {...p}/>,
  trash: (p) => <InlineIcon d={["M3 6h18","M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2","M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"]} {...p}/>,
  more: () => <svg width={14} height={14} viewBox="0 0 24 24" fill="currentColor"><circle cx="6" cy="12" r="1.6"/><circle cx="12" cy="12" r="1.6"/><circle cx="18" cy="12" r="1.6"/></svg>,
  search: (p) => <InlineIcon d={["M21 21l-4.3-4.3"]} stroke={1.8} {...p}/>,
  searchFull: (p) => <InlineIcon d={["M21 21l-4.3-4.3"]} {...p}/>,
  upload: (p) => <InlineIcon d={["M3 15v4a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-4","M17 8l-5-5-5 5","M12 3v12"]} {...p}/>,
  download: (p) => <InlineIcon d={["M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4","M7 10l5 5 5-5","M12 15V3"]} {...p}/>,
  filter: (p) => <InlineIcon d={["M3 5h18l-7 9v6l-4-2v-4z"]} {...p}/>,
  cog: (p) => <InlineIcon d={["M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h0a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v0a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z","M12 9a3 3 0 1 1 0 6 3 3 0 0 1 0-6z"]} {...p}/>,
  sliders: (p) => <InlineIcon d={["M4 21v-7","M4 10V3","M12 21v-9","M12 8V3","M20 21v-5","M20 12V3","M1 14h6","M9 8h6","M17 16h6"]} {...p}/>,
  cols: (p) => <InlineIcon d={["M3 4h18v16H3z","M9 4v16","M15 4v16"]} {...p}/>,
  building: (p) => <InlineIcon d={["M3 21h18","M5 21V7l8-4v18","M19 21V11l-6-4","M9 9v.01","M9 13v.01","M9 17v.01"]} {...p}/>,
  folder: (p) => <InlineIcon d={["M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"]} {...p}/>,
  factory: (p) => <InlineIcon d={["M2 20V11l5 3V11l5 3V11l5 3V8l3-3v15z","M6 20v-3","M11 20v-3","M16 20v-3"]} {...p}/>,
  shield: (p) => <InlineIcon d={["M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"]} {...p}/>,
  briefcase: (p) => <InlineIcon d={["M3 8h18v12H3z","M8 8V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v3"]} {...p}/>,
  store: (p) => <InlineIcon d={["M3 9l1.5-5h15L21 9","M3 9v11h18V9","M3 9a3 3 0 0 0 6 0 3 3 0 0 0 6 0 3 3 0 0 0 6 0"]} {...p}/>,
  truck: (p) => <InlineIcon d={["M1 6h13v11H1z","M14 9h4l3 3v5h-7","M5.5 21a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5z","M17.5 21a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5z"]} {...p}/>,
  users: (p) => <InlineIcon d={["M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2","M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z","M22 21v-2a4 4 0 0 0-3-3.87","M17 3.13a4 4 0 0 1 0 7.75"]} {...p}/>,
  tools: (p) => <InlineIcon d={["M14.7 6.3a4 4 0 0 0 5.6 5.6l-7.07 7.07a2 2 0 0 1-2.83 0l-2.8-2.8a2 2 0 0 1 0-2.83zM3 21l3-3"]} {...p}/>,
  grip: () => <svg width={12} height={12} viewBox="0 0 12 12" fill="currentColor" aria-hidden><circle cx="3" cy="3" r="1"/><circle cx="3" cy="6" r="1"/><circle cx="3" cy="9" r="1"/><circle cx="9" cy="3" r="1"/><circle cx="9" cy="6" r="1"/><circle cx="9" cy="9" r="1"/></svg>,
  card: (p) => <InlineIcon d={["M3 6h18v12H3z","M3 10h18"]} {...p}/>,
  bluetooth: (p) => <InlineIcon d={["M7 7l10 10-5 4V3l5 4L7 17"]} {...p}/>,
  finger: (p) => <InlineIcon d={["M5.5 9.5a8 8 0 0 1 14 0","M3 14c.5-2.5 2-5 4.5-6.5","M9 22c-1-2-1-4-1-6a4 4 0 0 1 8 0c0 1 0 2 .5 3","M12 12c0 4 1 7 3 9","M21 14c0-3-1-6-3-7"]} {...p}/>,
  face: (p) => <InlineIcon d={["M3 7V5a2 2 0 0 1 2-2h2","M17 3h2a2 2 0 0 1 2 2v2","M21 17v2a2 2 0 0 1-2 2h-2","M7 21H5a2 2 0 0 1-2-2v-2","M9 10v.01","M15 10v.01","M9 15c1 1 2 1.5 3 1.5s2-.5 3-1.5"]} {...p}/>,
  badge: (p) => <InlineIcon d={["M12 2l3 3h4v4l3 3-3 3v4h-4l-3 3-3-3H5v-4l-3-3 3-3V5h4z","M9 12l2 2 4-4"]} {...p}/>,
  chevDown: (p) => <InlineIcon d={["M6 9l6 6 6-6"]} {...p}/>,
  chevRight: (p) => <InlineIcon d={["M9 6l6 6-6 6"]} {...p}/>,
  chevLeft: (p) => <InlineIcon d={["M15 18l-6-6 6-6"]} {...p}/>,
  chevFirst: (p) => <InlineIcon d={["M11 18l-6-6 6-6","M19 18l-6-6 6-6"]} {...p}/>,
  chevLast: (p) => <InlineIcon d={["M13 18l6-6-6-6","M5 18l6-6-6-6"]} {...p}/>,
  x: (p) => <InlineIcon d={["M6 6l12 12","M6 18L18 6"]} {...p}/>,
  copy: (p) => <InlineIcon d={["M9 9h11v11H9z","M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"]} {...p}/>,
  arrowUpDown: (p) => <InlineIcon d={["M7 16V4","M3 8l4-4 4 4","M17 8v12","M21 16l-4 4-4-4"]} {...p}/>,
  arrowRight: (p) => <InlineIcon d={["M5 12h14","M13 5l7 7-7 7"]} {...p}/>,
  swatch: (p) => <InlineIcon d={["M2 2h7v7H2z","M13 2h9v9h-9z","M2 13h9v9H2z","M16.5 16.5l3 3","M19.5 16.5l-3 3"]} {...p}/>,
  check: (p) => <InlineIcon d={["M5 12.5l4 4L19 7"]} {...p}/>,
  alert: (p) => <InlineIcon d={["M10.3 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z","M12 9v4","M12 17h.01"]} {...p}/>,
};
window.I = I;
