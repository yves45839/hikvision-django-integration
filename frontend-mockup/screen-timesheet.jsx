/* === Timesheet validation screen — focus parcours === */
/* eslint-disable */

const tsStyles = {
  layout: { display: "grid", gridTemplateColumns: "1fr", gap: 16 },
  banner: {
    background: "var(--warn-soft)",
    border: "1px solid oklch(0.85 0.08 75)",
    borderRadius: 12,
    padding: "14px 18px",
    display: "flex", alignItems: "center", gap: 14,
    marginBottom: 16,
  },
  bannerIcn: {
    width: 36, height: 36, borderRadius: 10,
    background: "var(--warn)", color: "white",
    display: "grid", placeItems: "center", flexShrink: 0,
  },
  segctrl: {
    display: "inline-flex", border: "1px solid var(--line)",
    borderRadius: 9, overflow: "hidden", background: "var(--surface)",
  },
  segBtn: {
    border: 0, background: "transparent", padding: "7px 14px",
    fontSize: 13, color: "var(--ink-3)", cursor: "pointer",
    fontWeight: 500, fontFamily: "inherit",
  },
  segOn: { background: "var(--ink)", color: "white", fontWeight: 600 },
  rowCard: {
    background: "var(--surface)", border: "1px solid var(--line)",
    borderRadius: 12, padding: "16px 20px", marginBottom: 10,
    display: "grid", gridTemplateColumns: "1.4fr 2.4fr 1fr auto",
    gap: 24, alignItems: "center",
  },
  rowSelected: {
    background: "var(--brand-soft)", borderColor: "var(--brand)",
  },
  timeline: { position: "relative", height: 50 },
  tlTrack: {
    position: "absolute", left: 0, right: 0, top: 22, height: 6,
    background: "var(--surface-3)", borderRadius: 4,
  },
  tlExpected: {
    position: "absolute", top: 22, height: 6, borderRadius: 4,
    background: "var(--brand)", opacity: 0.3,
  },
  tlActual: {
    position: "absolute", top: 22, height: 6, borderRadius: 4,
    background: "var(--brand)",
  },
  tlAnomaly: { background: "var(--warn)" },
  tlMarker: {
    position: "absolute", top: 14, width: 22, height: 22,
    borderRadius: "50%", background: "white", border: "2px solid var(--brand)",
    fontSize: 10, fontWeight: 700, display: "grid", placeItems: "center",
    color: "var(--brand-ink)",
  },
  tlScale: { position: "absolute", left: 0, right: 0, bottom: 0,
    display: "flex", justifyContent: "space-between",
    fontSize: 10, color: "var(--ink-4)", fontFamily: "var(--font-mono)" },
  delta: {
    display: "inline-flex", alignItems: "center", gap: 4,
    padding: "3px 9px", fontSize: 12, fontWeight: 600,
    borderRadius: 999, fontFamily: "var(--font-mono)",
  },
};

function TimesheetScreen({ lang }) {
  const tt = (k) => I18N[lang][k];

  const items = [
    {
      id: 1, name: "Salim Ouhmane", initials: "SO", color: "oklch(0.6 0.13 25)",
      date: "Ven. 30 avr.", dateEN: "Fri Apr 30",
      reason: lang==="en"?"Late arrival · Camera #2 · 06:24":"Arrivée tardive · Caméra #2 · 06:24",
      expectStart: "06:00", expectEnd: "14:00",
      actualStart: "06:24", actualEnd: "14:05",
      delta: "+24 min", deltaType: "warn",
      severity: "warn", selected: false,
    },
    {
      id: 2, name: "Aïcha Diop", initials: "AD", color: "oklch(0.5 0.12 305)",
      date: "Ven. 30 avr.", dateEN: "Fri Apr 30",
      reason: lang==="en"?"No clock-out detected · auto-closed at shift end":"Pas de pointage de sortie · clôture auto en fin de quart",
      expectStart: "08:00", expectEnd: "16:00",
      actualStart: "07:58", actualEnd: "—",
      delta: lang==="en"?"missing":"manquant", deltaType: "danger",
      severity: "danger", selected: true,
    },
    {
      id: 3, name: "Karim Benhaddou", initials: "KB", color: "oklch(0.55 0.13 220)",
      date: "Jeu. 29 avr.", dateEN: "Thu Apr 29",
      reason: lang==="en"?"Extended overtime · +42 min":"Heures sup. prolongées · +42 min",
      expectStart: "22:00", expectEnd: "06:00",
      actualStart: "22:00", actualEnd: "06:42",
      delta: "+42 min", deltaType: "info",
      severity: "info", selected: false,
    },
    {
      id: 4, name: "N'Guessan Anderson", initials: "NA", color: "oklch(0.5 0.11 165)",
      date: "Jeu. 29 avr.", dateEN: "Thu Apr 29",
      reason: lang==="en"?"Long break · 1h42 instead of 1h":"Pause longue · 1h42 au lieu de 1h",
      expectStart: "14:00", expectEnd: "22:00",
      actualStart: "14:00", actualEnd: "22:00",
      delta: "+42 min", deltaType: "warn",
      severity: "warn", selected: false,
    },
    {
      id: 5, name: "Yasmina El Bahri", initials: "YE", color: "oklch(0.55 0.12 280)",
      date: "Mer. 28 avr.", dateEN: "Wed Apr 28",
      reason: lang==="en"?"Early clock-out · −18 min":"Sortie anticipée · −18 min",
      expectStart: "08:30", expectEnd: "17:30",
      actualStart: "08:30", actualEnd: "17:12",
      delta: "−18 min", deltaType: "warn",
      severity: "warn", selected: false,
    },
  ];

  // map HH:MM in [00..24] to percentage of [04:00..24:00] window for visual
  const toPct = (t) => {
    if (t === "—") return null;
    const [h, m] = t.split(":").map(Number);
    let v = h + m/60;
    // normalize night shifts (22 → next 6) to a 0..28 axis
    if (v < 4) v += 24;
    return ((v - 4) / 24) * 100;
  };

  return (
    <div className="page">
      <div className="ph">
        <div>
          <h1>{tt("timesheet")}</h1>
          <p>{lang === "en"
            ? "5 anomalies require validation across the last 7 days"
            : "5 anomalies à valider sur les 7 derniers jours"}</p>
        </div>
        <div className="ph-actions">
          <button className="btn">{tt("export")}</button>
          <button className="btn primary"><Icon name="check" />{tt("approveAll")} (5)</button>
        </div>
      </div>

      <div style={tsStyles.banner}>
        <div style={tsStyles.bannerIcn}><Icon name="sparkle" /></div>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 600, fontSize: 13.5, color: "var(--warn-ink)" }}>
            {lang === "en"
              ? "AI suggestion: 3 of 5 anomalies match a recurring pattern"
              : "Suggestion IA : 3 des 5 anomalies suivent un schéma récurrent"}
          </div>
          <div style={{ fontSize: 12, color: "var(--warn-ink)", marginTop: 2, opacity: 0.85 }}>
            {lang === "en"
              ? "Late arrivals on Fridays for SO and KB during the last 4 weeks. Suggest adjusting shift start by 15 min."
              : "Arrivées tardives le vendredi pour SO et KB sur les 4 dernières semaines. Décaler le début de quart de 15 min ?"}
          </div>
        </div>
        <button className="btn sm">{lang === "en" ? "Review pattern" : "Voir l'analyse"}</button>
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
        <div style={tsStyles.segctrl}>
          <button style={{...tsStyles.segBtn, ...tsStyles.segOn}}>{lang==="en"?"Anomalies":"Anomalies"} <span style={{opacity: 0.6, marginLeft: 4}}>5</span></button>
          <button style={tsStyles.segBtn}>{lang==="en"?"Auto-validated":"Auto-validés"} <span style={{opacity: 0.6, marginLeft: 4}}>183</span></button>
          <button style={tsStyles.segBtn}>{lang==="en"?"All":"Tous"} <span style={{opacity: 0.6, marginLeft: 4}}>188</span></button>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span style={{ fontSize: 12.5, color: "var(--ink-3)" }}>{lang==="en"?"Last 7 days":"7 derniers jours"}</span>
          <Icon name="chevronDown" />
        </div>
      </div>

      <div>
        {items.map((it) => {
          const expS = toPct(it.expectStart);
          const expE = toPct(it.expectEnd);
          const actS = toPct(it.actualStart);
          const actE = toPct(it.actualEnd) ?? expE;
          const isMissing = it.actualEnd === "—";
          return (
            <div key={it.id} style={{...tsStyles.rowCard, ...(it.selected ? tsStyles.rowSelected : {})}}>
              <div className="row" style={{ minWidth: 0 }}>
                <div className="av" style={{ background: it.color }}>{it.initials}</div>
                <div className="col" style={{ gap: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 600 }}>{it.name}</div>
                  <div className="smaller muted">{lang === "en" ? it.dateEN : it.date} · {it.reason}</div>
                </div>
              </div>

              <div style={tsStyles.timeline}>
                <div style={tsStyles.tlTrack} />
                <div style={{
                  ...tsStyles.tlExpected,
                  left: `${expS}%`, width: `${expE - expS}%`
                }} />
                {!isMissing ? (
                  <div style={{
                    ...tsStyles.tlActual,
                    ...(it.severity !== "info" ? tsStyles.tlAnomaly : {}),
                    left: `${actS}%`, width: `${actE - actS}%`
                  }} />
                ) : (
                  <div style={{
                    ...tsStyles.tlActual,
                    background: "repeating-linear-gradient(90deg, var(--danger), var(--danger) 6px, transparent 6px, transparent 12px)",
                    left: `${actS}%`, width: `${actE - actS}%`,
                    opacity: 0.7,
                  }} />
                )}
                <div style={{...tsStyles.tlMarker, left: `calc(${actS}% - 11px)`,
                  borderColor: it.severity === "warn" ? "var(--warn)" : it.severity === "danger" ? "var(--danger)" : "var(--brand)",
                  color: it.severity === "warn" ? "var(--warn-ink)" : it.severity === "danger" ? "var(--danger-ink)" : "var(--brand-ink)"
                }}>
                  {it.actualStart.split(":")[0]}
                </div>
                <div style={tsStyles.tlScale}>
                  <span>04:00</span><span>10:00</span><span>16:00</span><span>22:00</span><span>04:00</span>
                </div>
              </div>

              <div className="col" style={{ gap: 4 }}>
                <div className="smaller muted">{tt("expected")} <span className="mono" style={{ color: "var(--ink-2)" }}>{it.expectStart}–{it.expectEnd}</span></div>
                <div className="smaller">
                  {tt("actual")} <span className="mono" style={{ color: "var(--ink)", fontWeight: 600 }}>{it.actualStart}–{it.actualEnd}</span>
                  {" "}
                  <span style={{
                    ...tsStyles.delta,
                    background: it.deltaType === "danger" ? "var(--danger-soft)" :
                                it.deltaType === "warn" ? "var(--warn-soft)" : "var(--info-soft)",
                    color: it.deltaType === "danger" ? "var(--danger-ink)" :
                           it.deltaType === "warn" ? "var(--warn-ink)" : "oklch(0.35 0.1 240)",
                  }}>{it.delta}</span>
                </div>
              </div>

              <div style={{ display: "flex", gap: 6 }}>
                <button className="btn sm" title={tt("reject")}><Icon name="x" /></button>
                <button className="btn sm">{tt("edit")}</button>
                <button className="btn sm primary"><Icon name="check" />{tt("approve")}</button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

Object.assign(window, { TimesheetScreen });
