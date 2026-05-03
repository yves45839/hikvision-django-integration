/* === Planning weekly screen === */
/* eslint-disable */

const plStyles = {
  toolbar: {
    display: "flex", alignItems: "center", justifyContent: "space-between",
    marginBottom: 14, gap: 12,
  },
  weekNav: { display: "flex", alignItems: "center", gap: 8 },
  weekBtn: {
    width: 30, height: 30, borderRadius: 7,
    border: "1px solid var(--line)", background: "var(--surface)",
    display: "grid", placeItems: "center", cursor: "pointer", color: "var(--ink-2)",
  },
  weekLabel: {
    fontFamily: "var(--font-display)", fontSize: 15, fontWeight: 600,
    padding: "0 10px", color: "var(--ink)",
  },
  grid: {
    display: "grid",
    gridTemplateColumns: "180px repeat(7, 1fr)",
    background: "var(--surface)", border: "1px solid var(--line)",
    borderRadius: 14, overflow: "hidden", boxShadow: "var(--shadow-sm)",
  },
  hd: {
    padding: "12px 14px", fontSize: 12, color: "var(--ink-3)",
    fontWeight: 600, borderBottom: "1px solid var(--line)",
    borderRight: "1px solid var(--line)", background: "var(--surface-2)",
  },
  hdDay: {
    padding: "10px 12px", textAlign: "center",
    borderBottom: "1px solid var(--line)", borderRight: "1px solid var(--line)",
    background: "var(--surface-2)",
  },
  cell: {
    padding: 8, minHeight: 96,
    borderBottom: "1px solid var(--line)", borderRight: "1px solid var(--line)",
    position: "relative",
  },
  empCell: {
    padding: "12px 14px", display: "flex", alignItems: "center", gap: 10,
    borderBottom: "1px solid var(--line)", borderRight: "1px solid var(--line)",
    background: "var(--surface-2)",
  },
  shift: {
    borderRadius: 7, padding: "6px 9px", marginBottom: 4,
    fontSize: 11.5, fontWeight: 600, lineHeight: 1.3,
    cursor: "pointer", border: "1px solid transparent",
  },
  hours: { fontFamily: "var(--font-mono)", fontSize: 10.5, fontWeight: 500, opacity: 0.85, marginTop: 1, letterSpacing: "-0.01em" },
};

function PlanningScreen({ lang }) {
  const tt = (k) => I18N[lang][k];
  const days = lang === "en"
    ? ["Mon 04","Tue 05","Wed 06","Thu 07","Fri 08","Sat 09","Sun 10"]
    : ["Lun 04","Mar 05","Mer 06","Jeu 07","Ven 08","Sam 09","Dim 10"];

  // Shift palette
  const SHIFTS = {
    morning: { bg: "oklch(0.96 0.04 165)", border: "oklch(0.85 0.06 165)", ink: "var(--brand-ink)", label: "06–14" },
    day: { bg: "oklch(0.96 0.04 240)", border: "oklch(0.85 0.06 240)", ink: "oklch(0.35 0.1 240)", label: "08–16" },
    evening: { bg: "oklch(0.96 0.04 60)", border: "oklch(0.85 0.06 60)", ink: "oklch(0.4 0.1 60)", label: "14–22" },
    night: { bg: "oklch(0.94 0.04 290)", border: "oklch(0.82 0.06 290)", ink: "oklch(0.35 0.1 290)", label: "22–06" },
    off: null,
    leave: { bg: "var(--absence-soft)", border: "oklch(0.85 0.06 25)", ink: "oklch(0.4 0.12 25)", label: lang==="en"?"Leave":"Congé" },
  };

  // 6 employees x 7 days
  const team = [
    { name: "Salim Ouhmane", initials: "SO", color: "oklch(0.6 0.13 25)", role: lang==="en"?"Lead guard":"Agent senior", h: 40, days: ["morning","morning","off","morning","morning","off","off"] },
    { name: "Yasmina El Bahri", initials: "YE", color: "oklch(0.55 0.12 280)", role: lang==="en"?"Receptionist":"Hôtesse", h: 36, days: ["day","day","leave","leave","leave","off","off"] },
    { name: "N'Guessan Anderson", initials: "NA", color: "oklch(0.5 0.11 165)", role: lang==="en"?"Site sup.":"Chef site", h: 40, days: ["evening","evening","evening","off","evening","evening","off"] },
    { name: "Karim Benhaddou", initials: "KB", color: "oklch(0.55 0.13 220)", role: lang==="en"?"Night guard":"Agent nuit", h: 40, days: ["night","off","night","night","off","night","night"] },
    { name: "Aïcha Diop", initials: "AD", color: "oklch(0.5 0.12 305)", role: lang==="en"?"Operator":"Opératrice", h: 32, days: ["day","day","off","day","day","off","off"] },
    { name: "Marc Belkacem", initials: "MB", color: "oklch(0.55 0.13 130)", role: lang==="en"?"Trainee":"Stagiaire", h: 40, days: ["morning","morning","morning","morning","off","off","off"] },
  ];

  return (
    <div className="page">
      <div className="ph">
        <div>
          <h1>{tt("planning")}</h1>
          <p>{lang === "en" ? "HQ · Casablanca · 6 people scheduled" : "Siège · Casablanca · 6 personnes planifiées"}</p>
        </div>
        <div className="ph-actions">
          <button className="btn"><Icon name="sparkle" />{lang === "en" ? "AI fill gaps" : "Remplir auto."}</button>
          <button className="btn">{lang === "en" ? "Copy last week" : "Copier sem. dernière"}</button>
          <button className="btn primary"><Icon name="check" />{tt("publish")}</button>
        </div>
      </div>

      <div style={plStyles.toolbar}>
        <div style={plStyles.weekNav}>
          <button style={plStyles.weekBtn}><Icon name="chevronLeft" /></button>
          <div style={plStyles.weekLabel}>{tt("weekOf")} {lang === "en" ? "May 4" : "4 mai"} — 10 {lang === "en" ? "May" : "mai"} 2026</div>
          <button style={plStyles.weekBtn}><Icon name="chevronRight" /></button>
          <button className="btn sm" style={{ marginLeft: 6 }}>{lang === "en" ? "This week" : "Cette semaine"}</button>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <div style={{ display: "flex", gap: 10, fontSize: 11.5, color: "var(--ink-3)", marginRight: 12 }}>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}><span style={{ width: 10, height: 10, background: SHIFTS.morning.bg, border: `1px solid ${SHIFTS.morning.border}`, borderRadius: 3 }} />6–14</span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}><span style={{ width: 10, height: 10, background: SHIFTS.day.bg, border: `1px solid ${SHIFTS.day.border}`, borderRadius: 3 }} />8–16</span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}><span style={{ width: 10, height: 10, background: SHIFTS.evening.bg, border: `1px solid ${SHIFTS.evening.border}`, borderRadius: 3 }} />14–22</span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}><span style={{ width: 10, height: 10, background: SHIFTS.night.bg, border: `1px solid ${SHIFTS.night.border}`, borderRadius: 3 }} />22–06</span>
          </div>
        </div>
      </div>

      <div style={plStyles.grid}>
        <div style={plStyles.hd}>{lang === "en" ? "Team member" : "Collaborateur"}</div>
        {days.map((d, i) => (
          <div key={i} style={{...plStyles.hdDay, borderRight: i === 6 ? 0 : "1px solid var(--line)"}}>
            <div style={{ fontSize: 11, color: "var(--ink-4)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em" }}>
              {d.split(" ")[0]}
            </div>
            <div style={{ fontFamily: "var(--font-display)", fontSize: 16, fontWeight: 600, marginTop: 1 }}>
              {d.split(" ")[1]}
            </div>
          </div>
        ))}

        {team.map((m, ri) => (
          <React.Fragment key={ri}>
            <div style={{...plStyles.empCell, borderBottom: ri === team.length - 1 ? 0 : "1px solid var(--line)"}}>
              <div className="av sm" style={{ background: m.color }}>{m.initials}</div>
              <div className="col" style={{ gap: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12.5, fontWeight: 600 }}>{m.name}</div>
                <div style={{ fontSize: 10.5, color: "var(--ink-3)" }}>{m.role} · <span className="mono">{m.h}h</span></div>
              </div>
            </div>
            {m.days.map((s, ci) => {
              const sh = SHIFTS[s];
              const isLast = ri === team.length - 1;
              const isLastCol = ci === 6;
              return (
                <div key={ci} style={{
                  ...plStyles.cell,
                  borderBottom: isLast ? 0 : "1px solid var(--line)",
                  borderRight: isLastCol ? 0 : "1px solid var(--line)",
                  background: ci >= 5 ? "var(--surface-2)" : "var(--surface)",
                }}>
                  {sh && (
                    <div style={{
                      ...plStyles.shift,
                      background: sh.bg, borderColor: sh.border, color: sh.ink,
                    }}>
                      {sh.label}
                      {s !== "leave" && <div style={plStyles.hours}>8h</div>}
                    </div>
                  )}
                  {!sh && (
                    <div style={{ fontSize: 11, color: "var(--ink-4)", padding: "8px 4px", textAlign: "center" }}>—</div>
                  )}
                </div>
              );
            })}
          </React.Fragment>
        ))}

        {/* Coverage row */}
        <div style={{...plStyles.empCell, borderBottom: 0, fontWeight: 600, fontSize: 12, color: "var(--ink-2)"}}>
          {lang === "en" ? "Coverage / 6" : "Couverture / 6"}
        </div>
        {[5, 5, 4, 5, 4, 2, 1].map((c, i) => {
          const ok = c >= 4;
          return (
            <div key={i} style={{
              ...plStyles.cell, minHeight: 0, padding: "10px 8px",
              borderBottom: 0, borderRight: i === 6 ? 0 : "1px solid var(--line)",
              background: i >= 5 ? "var(--surface-2)" : "var(--surface)",
              textAlign: "center",
            }}>
              <span className={"chip " + (ok ? "success" : c >= 2 ? "warn" : "danger")} style={{ display: "inline-flex" }}>
                <span className="dot" />{c}/6
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

Object.assign(window, { PlanningScreen });
