/* === Absences & leave requests screen === */
/* eslint-disable */

const abStyles = {
  layout: { display: "grid", gridTemplateColumns: "1fr 320px", gap: 18, alignItems: "flex-start" },
  reqCard: {
    background: "var(--surface)", border: "1px solid var(--line)",
    borderRadius: 12, padding: "18px 20px", marginBottom: 12,
    display: "grid", gridTemplateColumns: "1fr auto", gap: 16,
    alignItems: "flex-start",
  },
  reqSelected: { borderColor: "var(--brand)", boxShadow: "0 0 0 3px var(--brand-soft)" },
  bar: {
    height: 28, borderRadius: 6, background: "var(--surface-3)",
    position: "relative", overflow: "hidden", marginTop: 8,
  },
  barFill: {
    position: "absolute", top: 0, bottom: 0,
    background: "var(--absence-soft)",
    border: "1px solid oklch(0.85 0.06 25)",
    borderRadius: 6, display: "flex", alignItems: "center",
    paddingLeft: 8, fontSize: 11, fontWeight: 600, color: "oklch(0.4 0.12 25)",
  },
  miniCal: {
    display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 4,
    fontSize: 11,
  },
  calDay: {
    aspectRatio: "1", display: "grid", placeItems: "center",
    borderRadius: 6, background: "var(--surface-2)", color: "var(--ink-3)",
    fontWeight: 500,
  },
  calLeave: { background: "var(--absence-soft)", color: "oklch(0.4 0.12 25)", fontWeight: 700 },
  calConflict: { background: "var(--danger-soft)", color: "var(--danger-ink)", fontWeight: 700, border: "1px solid var(--danger)" },
  calToday: { outline: "2px solid var(--brand)", outlineOffset: -2 },
};

function AbsencesScreen({ lang }) {
  const tt = (k) => I18N[lang][k];
  const requests = [
    {
      id: 1, name: "Salim Ouhmane", initials: "SO", color: "oklch(0.6 0.13 25)",
      type: lang==="en"?"Paid leave":"Congés payés", chip: "absence",
      from: "06/05", to: "10/05", days: 5,
      requestedOn: lang==="en"?"3 days ago":"il y a 3 jours",
      reason: lang==="en"?"Family event in Marrakech":"Événement familial à Marrakech",
      conflict: false, balance: { used: 7, total: 25 }, selected: false,
    },
    {
      id: 2, name: "Yasmina El Bahri", initials: "YE", color: "oklch(0.55 0.12 280)",
      type: lang==="en"?"Paid leave":"Congés payés", chip: "absence",
      from: "06/05", to: "08/05", days: 3,
      requestedOn: lang==="en"?"yesterday":"hier",
      reason: lang==="en"?"Personal matters":"Affaires personnelles",
      conflict: true, balance: { used: 12, total: 25 }, selected: true,
    },
    {
      id: 3, name: "Karim Benhaddou", initials: "KB", color: "oklch(0.55 0.13 220)",
      type: lang==="en"?"Sick leave":"Maladie", chip: "warn",
      from: "30/04", to: "02/05", days: 3,
      requestedOn: lang==="en"?"this morning":"ce matin",
      reason: lang==="en"?"Medical certificate attached":"Certificat médical joint",
      conflict: false, balance: { used: 4, total: 25 }, selected: false,
    },
  ];

  return (
    <div className="page">
      <div className="ph">
        <div>
          <h1>{tt("absences")}</h1>
          <p>{lang === "en" ? "3 pending requests · 4 people on leave today" : "3 demandes en attente · 4 personnes en congé aujourd'hui"}</p>
        </div>
        <div className="ph-actions">
          <button className="btn">{lang==="en"?"Leave policy":"Règles de congé"}</button>
          <button className="btn primary"><Icon name="plus" />{lang==="en"?"New request":"Nouvelle demande"}</button>
        </div>
      </div>

      <div className="tabs">
        <button className="on">{tt("pending")} <span style={{ marginLeft: 4, opacity: 0.6 }}>3</span></button>
        <button>{tt("approved")} <span style={{ marginLeft: 4, opacity: 0.6 }}>27</span></button>
        <button>{tt("refused")} <span style={{ marginLeft: 4, opacity: 0.6 }}>2</span></button>
        <button>{lang==="en"?"All":"Toutes"} <span style={{ marginLeft: 4, opacity: 0.6 }}>32</span></button>
      </div>

      <div style={abStyles.layout}>
        <div>
          {requests.map((r) => (
            <div key={r.id} style={{ ...abStyles.reqCard, ...(r.selected ? abStyles.reqSelected : {}) }}>
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
                  <div className="av" style={{ background: r.color }}>{r.initials}</div>
                  <div className="col" style={{ gap: 1 }}>
                    <div style={{ fontWeight: 600, fontSize: 14 }}>{r.name}</div>
                    <div className="smaller muted">{tt("requestedOn")} {r.requestedOn}</div>
                  </div>
                  <span className={"chip " + r.chip} style={{ marginLeft: 8 }}><span className="dot" />{r.type}</span>
                  {r.conflict && <span className="chip danger"><span className="dot" />{lang==="en"?"Conflict":"Conflit"}</span>}
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16, marginBottom: 8, padding: "10px 0", borderTop: "1px solid var(--line)", borderBottom: "1px solid var(--line)" }}>
                  <div>
                    <div className="smaller muted">{tt("period")}</div>
                    <div className="mono" style={{ fontWeight: 600, marginTop: 2 }}>{r.from} → {r.to}</div>
                  </div>
                  <div>
                    <div className="smaller muted">{tt("duration")}</div>
                    <div style={{ fontWeight: 600, marginTop: 2 }}>{r.days} {lang==="en"?"days":"jours"}</div>
                  </div>
                  <div>
                    <div className="smaller muted">{tt("balance")}</div>
                    <div style={{ marginTop: 4 }}>
                      <div style={{ fontSize: 12, fontWeight: 600 }}>{r.balance.used + r.days} / {r.balance.total} {lang==="en"?"days":"j"}</div>
                      <div style={{ height: 4, background: "var(--surface-3)", borderRadius: 4, marginTop: 3, overflow: "hidden" }}>
                        <div style={{ height: "100%", width: `${(r.balance.used / r.balance.total) * 100}%`, background: "var(--brand)" }} />
                        <div style={{ height: 4, marginTop: -4, width: `${((r.balance.used + r.days) / r.balance.total) * 100}%`, background: "transparent", borderRight: "2px solid var(--absence)" }} />
                      </div>
                    </div>
                  </div>
                </div>

                <div className="smaller muted" style={{ marginBottom: 10 }}>"{r.reason}"</div>

                {r.conflict && (
                  <div style={{ background: "var(--danger-soft)", border: "1px solid oklch(0.85 0.06 25)", borderRadius: 8, padding: "8px 12px", display: "flex", alignItems: "center", gap: 10, fontSize: 12 }}>
                    <Icon name="alert" className="" />
                    <span style={{ color: "var(--danger-ink)" }}>
                      {lang === "en"
                        ? "Overlaps with Salim's request (06–10/05). Reception coverage drops below 2 minimum on 06–08/05."
                        : "Chevauche la demande de Salim (06–10/05). Couverture accueil sous le minimum (2) du 06 au 08/05."}
                    </span>
                  </div>
                )}
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: 8, alignItems: "stretch", minWidth: 110 }}>
                <button className="btn primary"><Icon name="check" />{tt("approve")}</button>
                <button className="btn"><Icon name="x" />{tt("reject")}</button>
                <button className="btn ghost sm">{lang==="en"?"Discuss":"Discuter"}</button>
              </div>
            </div>
          ))}
        </div>

        {/* Side: team availability */}
        <div className="card">
          <div className="card-h">
            <div>
              <h3>{lang==="en"?"Team availability":"Disponibilité équipe"}</h3>
              <div className="sub">{lang==="en"?"May 2026":"Mai 2026"}</div>
            </div>
          </div>
          <div className="card-b">
            <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 4, fontSize: 10, color: "var(--ink-4)", fontWeight: 600, textAlign: "center", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 6 }}>
              {(lang==="en"?["M","T","W","T","F","S","S"]:["L","M","M","J","V","S","D"]).map((d,i) => <div key={i}>{d}</div>)}
            </div>
            <div style={abStyles.miniCal}>
              {Array.from({ length: 35 }).map((_, i) => {
                const day = i - 3;
                const isMonth = day >= 1 && day <= 31;
                const isToday = day === 3;
                const isLeave = [6,7,8,9,10].includes(day);
                const isConflict = [6,7,8].includes(day);
                let st = abStyles.calDay;
                if (isConflict) st = { ...st, ...abStyles.calConflict };
                else if (isLeave) st = { ...st, ...abStyles.calLeave };
                if (isToday) st = { ...st, ...abStyles.calToday };
                return (
                  <div key={i} style={{ ...st, opacity: isMonth ? 1 : 0.3 }}>
                    {isMonth ? day : ""}
                  </div>
                );
              })}
            </div>

            <div style={{ marginTop: 16, paddingTop: 14, borderTop: "1px solid var(--line)" }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-4)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 10 }}>
                {lang==="en"?"Balance summary":"Soldes équipe"}
              </div>
              {[
                { l: lang==="en"?"Paid leave":"Congés payés", v: "+3.2" , u: lang==="en"?"d/person":"j/pers." },
                { l: lang==="en"?"RTT":"RTT", v: "1.8", u: lang==="en"?"d/person":"j/pers." },
                { l: lang==="en"?"Sick (YTD)":"Maladie (cumul)", v: "12", u: lang==="en"?"days":"jours" },
              ].map((s, i) => (
                <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", fontSize: 12.5 }}>
                  <span>{s.l}</span>
                  <span><strong className="mono">{s.v}</strong> <span className="muted smaller">{s.u}</span></span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { AbsencesScreen });
