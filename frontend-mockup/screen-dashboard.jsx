/* === Manager Dashboard === */
/* eslint-disable */

const dashStyles = {
  hero: {
    background: "linear-gradient(135deg, oklch(0.96 0.025 165), oklch(0.94 0.03 145))",
    border: "1px solid var(--line)",
    borderRadius: 16,
    padding: "26px 28px",
    marginBottom: 22,
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 24,
  },
  heroTitle: {
    fontFamily: "var(--font-display)",
    fontSize: 22,
    fontWeight: 600,
    letterSpacing: "-0.02em",
    margin: 0,
    color: "var(--ink)",
  },
  heroSub: { color: "var(--ink-2)", fontSize: 13.5, margin: "4px 0 0" },
  kpiGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(4, 1fr)",
    gap: 14,
    marginBottom: 22,
  },
  kpi: {
    background: "var(--surface)",
    border: "1px solid var(--line)",
    borderRadius: 14,
    padding: "18px 20px",
    boxShadow: "var(--shadow-sm)",
  },
  kpiLabel: { fontSize: 12, color: "var(--ink-3)", fontWeight: 500, marginBottom: 8, display: "flex", alignItems: "center", gap: 6 },
  kpiValueRow: { display: "flex", alignItems: "baseline", gap: 8, marginBottom: 4 },
  kpiValue: { fontFamily: "var(--font-display)", fontSize: 28, fontWeight: 600, letterSpacing: "-0.02em", color: "var(--ink)" },
  kpiOf: { fontSize: 14, color: "var(--ink-3)" },
  kpiTrend: { fontSize: 11.5, color: "var(--ink-3)", display: "flex", alignItems: "center", gap: 4 },
  kpiBar: { marginTop: 12, height: 4, background: "var(--surface-3)", borderRadius: 4, overflow: "hidden" },
  kpiBarFill: { height: "100%", background: "var(--brand)", borderRadius: 4 },
  twoCol: { display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 18 },
  actionRow: {
    display: "flex", alignItems: "center", justifyContent: "space-between",
    padding: "14px 20px", borderBottom: "1px solid var(--line)", gap: 14,
  },
  actionMeta: { display: "flex", alignItems: "center", gap: 12, minWidth: 0 },
  actionIcn: {
    width: 36, height: 36, borderRadius: 10,
    background: "var(--warn-soft)", color: "var(--warn-ink)",
    display: "grid", placeItems: "center", flexShrink: 0,
  },
  actionTitle: { fontSize: 13.5, fontWeight: 600, color: "var(--ink)", marginBottom: 2 },
  actionSub: { fontSize: 12, color: "var(--ink-3)" },
  presence: { display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 6, marginTop: 10 },
  presenceCol: { textAlign: "center" },
  presenceDay: { fontSize: 10.5, color: "var(--ink-4)", fontWeight: 600, letterSpacing: "0.05em", textTransform: "uppercase", marginBottom: 6 },
  presenceBar: { background: "var(--surface-3)", borderRadius: 6, height: 64, position: "relative", overflow: "hidden" },
  presenceFill: { position: "absolute", left: 0, right: 0, bottom: 0, background: "var(--brand)", borderRadius: "0 0 6px 6px" },
  presenceVal: { fontSize: 12, fontWeight: 600, marginTop: 6, color: "var(--ink)" },
  leaveItem: { display: "flex", alignItems: "center", gap: 12, padding: "12px 0", borderBottom: "1px solid var(--line)" },
  leaveDate: {
    width: 44, textAlign: "center",
    background: "var(--absence-soft)", borderRadius: 8, padding: "5px 0",
    color: "oklch(0.4 0.12 25)", fontWeight: 600,
  },
  leaveDay: { fontSize: 17, fontWeight: 700, lineHeight: 1, fontFamily: "var(--font-display)" },
  leaveMon: { fontSize: 9.5, textTransform: "uppercase", letterSpacing: "0.06em", marginTop: 1 },
};

function ManagerDashboard({ lang }) {
  const tt = (k) => I18N[lang][k];
  const presence = [
    { d: "Lun", v: 92, n: 41 }, { d: "Mar", v: 95, n: 43 }, { d: "Mer", v: 89, n: 40 },
    { d: "Jeu", v: 91, n: 41 }, { d: "Ven", v: 87, n: 39 }, { d: "Sam", v: 36, n: 16 }, { d: "Dim", v: 22, n: 10 },
  ];
  const presenceEN = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"];
  const dayLabels = lang === "en" ? presenceEN : presence.map(p => p.d);

  const actions = [
    { type: "anomaly", title: lang === "en" ? "7 time anomalies awaiting validation" : "7 anomalies de pointage à valider", sub: lang === "en" ? "Friday April 30 — 4 employees" : "Vendredi 30 avril — 4 employés", chip: "warn", chipLabel: tt("review") },
    { type: "leave", title: lang === "en" ? "3 leave requests pending" : "3 demandes de congés en attente", sub: lang === "en" ? "Including 1 overlapping with team minimum" : "Dont 1 chevauchant le seuil d'équipe", chip: "danger", chipLabel: lang === "en" ? "Conflict" : "Conflit" },
    { type: "shift", title: lang === "en" ? "2 unfilled shifts next week" : "2 quarts non couverts semaine prochaine", sub: lang === "en" ? "Reception · Tuesday May 5, 6am–2pm" : "Réception · mardi 5 mai, 06h–14h", chip: "info", chipLabel: tt("assign") },
    { type: "doc", title: lang === "en" ? "Contract review · M. Belkacem" : "Revue de contrat · M. Belkacem", sub: lang === "en" ? "Probation period ends in 6 days" : "Période d'essai termine dans 6 jours", chip: "brand", chipLabel: tt("review") },
  ];

  const upcomingLeave = [
    { d: "06", m: "MAI", name: "Salim Ouhmane", dur: "5 j", type: lang==="en"?"Paid leave":"Congés payés" },
    { d: "12", m: "MAI", name: "Yasmina El Bahri", dur: "1 j", type: lang==="en"?"Personal":"Personnel" },
    { d: "18", m: "MAI", name: "N'Guessan Anderson", dur: "3 j", type: lang==="en"?"Paid leave":"Congés payés" },
    { d: "22", m: "MAI", name: "Léa Maréchal", dur: "10 j", type: lang==="en"?"Sick leave":"Maladie" },
  ];

  return (
    <div className="page">
      <div style={dashStyles.hero}>
        <div>
          <h1 style={dashStyles.heroTitle}>{tt("welcome")}, Jamila 👋</h1>
          <p style={dashStyles.heroSub}>
            {lang === "en"
              ? "44 people on shift today across 3 sites. 7 actions need your attention."
              : "44 personnes en service aujourd'hui sur 3 sites. 7 actions vous attendent."}
          </p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn"><Icon name="download" />{tt("export")}</button>
          <button className="btn primary"><Icon name="plus" />{tt("quickAction")}</button>
        </div>
      </div>

      <div style={dashStyles.kpiGrid}>
        <Kpi label={tt("presentToday")} value="41" of="/ 45" trend="+2" trendDir="up" pct={91} />
        <Kpi label={tt("onLeave")} value="4" of={lang==="en"?"people":"pers."} sub={lang==="en"?"2 paid · 1 sick · 1 personal":"2 payés · 1 maladie · 1 perso"} accent="absence" />
        <Kpi label={tt("pendingTimeAnomalies")} value="7" of={lang==="en"?"to validate":"à valider"} sub={lang==="en"?"Oldest: 2 days":"Plus ancien : 2 j"} accent="warn" />
        <Kpi label={tt("pendingLeaveRequests")} value="3" of={lang==="en"?"requests":"demandes"} sub={lang==="en"?"1 conflict detected":"1 conflit détecté"} accent="danger" />
      </div>

      <div style={dashStyles.twoCol}>
        <div className="card">
          <div className="card-h">
            <div>
              <h3>{lang === "en" ? "Needs your attention" : "À traiter aujourd'hui"}</h3>
              <div className="sub">{lang === "en" ? "Sorted by urgency" : "Trié par urgence"}</div>
            </div>
            <button className="btn ghost sm">{lang === "en" ? "View all" : "Tout voir"} <Icon name="chevronRight" /></button>
          </div>
          {actions.map((a, i) => (
            <div key={i} style={{...dashStyles.actionRow, borderBottom: i === actions.length - 1 ? 0 : "1px solid var(--line)"}}>
              <div style={dashStyles.actionMeta}>
                <div style={{
                  ...dashStyles.actionIcn,
                  background: a.type === "anomaly" ? "var(--warn-soft)" :
                              a.type === "leave" ? "var(--absence-soft)" :
                              a.type === "shift" ? "var(--info-soft)" : "var(--brand-soft)",
                  color: a.type === "anomaly" ? "var(--warn-ink)" :
                         a.type === "leave" ? "oklch(0.4 0.12 25)" :
                         a.type === "shift" ? "oklch(0.35 0.1 240)" : "var(--brand-ink)"
                }}>
                  <Icon name={a.type === "anomaly" ? "alert" : a.type === "leave" ? "plane" : a.type === "shift" ? "calendar" : "clipboard"} />
                </div>
                <div style={{ minWidth: 0 }}>
                  <div style={dashStyles.actionTitle}>{a.title}</div>
                  <div style={dashStyles.actionSub}>{a.sub}</div>
                </div>
              </div>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <button className="btn sm">{a.chipLabel}</button>
              </div>
            </div>
          ))}
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          <div className="card">
            <div className="card-h">
              <div>
                <h3>{lang === "en" ? "Team presence · this week" : "Présence équipe · semaine"}</h3>
                <div className="sub">{lang === "en" ? "Avg. 87% on-site" : "Moy. 87% sur site"}</div>
              </div>
            </div>
            <div className="card-b" style={{ paddingTop: 8 }}>
              <div style={dashStyles.presence}>
                {presence.map((p, i) => (
                  <div key={i} style={dashStyles.presenceCol}>
                    <div style={dashStyles.presenceDay}>{dayLabels[i]}</div>
                    <div style={dashStyles.presenceBar}>
                      <div style={{...dashStyles.presenceFill, height: `${p.v}%`, background: i >= 5 ? "var(--ink-4)" : "var(--brand)" }} />
                    </div>
                    <div style={dashStyles.presenceVal}>{p.v}%</div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="card">
            <div className="card-h">
              <div>
                <h3>{tt("upcomingLeave")}</h3>
                <div className="sub">{lang === "en" ? "Next 30 days" : "30 prochains jours"}</div>
              </div>
              <button className="btn ghost sm"><Icon name="chevronRight" /></button>
            </div>
            <div className="card-b" style={{ padding: "4px 20px 12px" }}>
              {upcomingLeave.map((l, i) => (
                <div key={i} style={{...dashStyles.leaveItem, borderBottom: i === upcomingLeave.length - 1 ? 0 : "1px solid var(--line)"}}>
                  <div style={dashStyles.leaveDate}>
                    <div style={dashStyles.leaveDay}>{l.d}</div>
                    <div style={dashStyles.leaveMon}>{l.m}</div>
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 600 }}>{l.name}</div>
                    <div style={{ fontSize: 11.5, color: "var(--ink-3)" }}>{l.type} · {l.dur}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Kpi({ label, value, of, sub, trend, trendDir, pct, accent }) {
  const accentColor = {
    warn: "var(--warn)", danger: "var(--danger)",
    absence: "var(--absence)", undefined: "var(--brand)"
  }[accent];
  return (
    <div style={dashStyles.kpi}>
      <div style={dashStyles.kpiLabel}>{label}</div>
      <div style={dashStyles.kpiValueRow}>
        <div style={dashStyles.kpiValue}>{value}</div>
        <div style={dashStyles.kpiOf}>{of}</div>
      </div>
      <div style={dashStyles.kpiTrend}>
        {trend && <Icon name={trendDir === "up" ? "arrowUp" : "arrowDown"} />}
        {trend ? trend + (sub ? "" : "") : sub}
      </div>
      {pct !== undefined && (
        <div style={dashStyles.kpiBar}>
          <div style={{...dashStyles.kpiBarFill, width: `${pct}%`, background: accentColor}} />
        </div>
      )}
    </div>
  );
}

Object.assign(window, { ManagerDashboard });
