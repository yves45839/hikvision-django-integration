/* === Employees screen === */
/* eslint-disable */

const empStyles = {
  filters: { display: "flex", gap: 10, marginBottom: 16, alignItems: "center", flexWrap: "wrap" },
  filterPill: {
    display: "inline-flex", alignItems: "center", gap: 6,
    height: 34, padding: "0 12px", borderRadius: 8,
    border: "1px solid var(--line)", background: "var(--surface)",
    fontSize: 13, color: "var(--ink-2)", cursor: "pointer",
  },
  layout: { display: "grid", gridTemplateColumns: "1fr 360px", gap: 16, alignItems: "flex-start" },
  searchBar: {
    height: 38, borderRadius: 10, border: "1px solid var(--line)",
    background: "var(--surface)", display: "flex", alignItems: "center",
    padding: "0 12px", gap: 9, marginBottom: 12, fontSize: 13.5, color: "var(--ink-3)",
    flex: 1,
  },
};

function EmployeesScreen({ lang }) {
  const tt = (k) => I18N[lang][k];
  const employees = [
    { id: 1, name: "Salim Ouhmane", initials: "SO", color: "oklch(0.6 0.13 25)", role: lang==="en"?"Lead guard":"Agent senior", dept: lang==="en"?"Security · HQ":"Sécurité · Siège", matricule: "SP-0142", shift: "06:00 — 14:00", status: "active", balance: "12 j" },
    { id: 2, name: "Yasmina El Bahri", initials: "YE", color: "oklch(0.55 0.12 280)", role: lang==="en"?"Receptionist":"Hôtesse d'accueil", dept: lang==="en"?"Reception · HQ":"Accueil · Siège", matricule: "SP-0218", shift: "08:30 — 17:30", status: "leave", balance: "5 j" },
    { id: 3, name: "N'Guessan Anderson", initials: "NA", color: "oklch(0.5 0.11 165)", role: lang==="en"?"Site supervisor":"Chef de site", dept: lang==="en"?"Operations · LiSI":"Opérations · LiSI", matricule: "SP-0091", shift: "14:00 — 22:00", status: "active", balance: "18 j" },
    { id: 4, name: "Léa Maréchal", initials: "LM", color: "oklch(0.62 0.14 45)", role: lang==="en"?"HR coordinator":"Coordinatrice RH", dept: lang==="en"?"People":"Ressources humaines", matricule: "SP-0307", shift: "09:00 — 18:00", status: "remote", balance: "9 j" },
    { id: 5, name: "Karim Benhaddou", initials: "KB", color: "oklch(0.55 0.13 220)", role: lang==="en"?"Night guard":"Agent de nuit", dept: lang==="en"?"Security · Riviera":"Sécurité · Riviera", matricule: "SP-0156", shift: "22:00 — 06:00", status: "active", balance: "2 j" },
    { id: 6, name: "Aïcha Diop", initials: "AD", color: "oklch(0.5 0.12 305)", role: lang==="en"?"Operator":"Opératrice", dept: lang==="en"?"Operations · Treichville":"Opérations · Treichville", matricule: "SP-0263", shift: "08:00 — 16:00", status: "anomaly", balance: "14 j" },
    { id: 7, name: "Marc Belkacem", initials: "MB", color: "oklch(0.55 0.13 130)", role: lang==="en"?"Trainee guard":"Agent stagiaire", dept: lang==="en"?"Security · HQ":"Sécurité · Siège", matricule: "SP-0341", shift: "08:00 — 16:00", status: "probation", balance: "0 j" },
  ];

  const statusChip = (s) => {
    const map = {
      active: { cl: "success", t: lang==="en"?"On shift":"En service" },
      leave: { cl: "absence", t: lang==="en"?"On leave":"En congé" },
      remote: { cl: "info", t: lang==="en"?"Remote":"Télétravail" },
      anomaly: { cl: "warn", t: lang==="en"?"Anomaly":"Anomalie" },
      probation: { cl: "brand", t: lang==="en"?"Probation":"Période d'essai" },
    };
    const m = map[s];
    return <span className={"chip " + m.cl}><span className="dot" />{m.t}</span>;
  };

  return (
    <div className="page">
      <div className="ph">
        <div>
          <h1>{tt("employees")}</h1>
          <p>{lang === "en" ? "45 active people across 3 sites" : "45 personnes actives réparties sur 3 sites"}</p>
        </div>
        <div className="ph-actions">
          <button className="btn"><Icon name="download" />{tt("export")}</button>
          <button className="btn primary"><Icon name="plus" />{lang==="en"?"Add employee":"Ajouter"}</button>
        </div>
      </div>

      <div style={{ display: "flex", gap: 10, marginBottom: 14, alignItems: "center" }}>
        <div style={empStyles.searchBar}>
          <Icon name="search" />
          <span>{lang === "en" ? "Search by name, badge, role…" : "Rechercher par nom, badge, poste…"}</span>
        </div>
        <button style={empStyles.filterPill}><Icon name="filter" />{tt("allDepts")}<Icon name="chevronDown" /></button>
        <button style={empStyles.filterPill}>{tt("allStatuses")}<Icon name="chevronDown" /></button>
        <button style={empStyles.filterPill}>{tt("nameAsc")}<Icon name="chevronDown" /></button>
      </div>

      <div style={empStyles.layout}>
        <div className="card">
          <table className="tbl">
            <thead>
              <tr>
                <th style={{ width: "32%" }}>{tt("employee")}</th>
                <th>{tt("role")}</th>
                <th>{lang==="en"?"Today's shift":"Quart aujourd'hui"}</th>
                <th>{tt("status")}</th>
                <th style={{ textAlign: "right" }}>{lang==="en"?"Leave balance":"Solde congés"}</th>
              </tr>
            </thead>
            <tbody>
              {employees.map((e, i) => (
                <tr key={e.id} style={ i === 2 ? { background: "var(--brand-soft)" } : {}}>
                  <td>
                    <div className="row">
                      <div className="av" style={{ background: e.color }}>{e.initials}</div>
                      <div className="col" style={{ gap: 1 }}>
                        <div style={{ fontWeight: 600, color: "var(--ink)" }}>{e.name}</div>
                        <div className="smaller muted mono">{e.matricule}</div>
                      </div>
                    </div>
                  </td>
                  <td>
                    <div style={{ fontWeight: 500 }}>{e.role}</div>
                    <div className="smaller muted">{e.dept}</div>
                  </td>
                  <td className="mono">{e.shift}</td>
                  <td>{statusChip(e.status)}</td>
                  <td style={{ textAlign: "right", fontWeight: 600 }}>{e.balance}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Profile drawer (inline, not overlay) */}
        <div className="card">
          <div style={{ padding: 22, borderBottom: "1px solid var(--line)", display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center" }}>
            <div className="av lg" style={{ background: "oklch(0.5 0.11 165)", width: 60, height: 60, fontSize: 18 }}>NA</div>
            <div style={{ fontFamily: "var(--font-display)", fontSize: 17, fontWeight: 600, marginTop: 12 }}>N'Guessan Anderson</div>
            <div style={{ fontSize: 12.5, color: "var(--ink-3)", marginTop: 2 }}>{lang==="en"?"Site supervisor":"Chef de site"} · LiSI</div>
            <div style={{ display: "flex", gap: 6, marginTop: 12 }}>
              <span className="chip success"><span className="dot" />{lang==="en"?"On shift":"En service"}</span>
              <span className="chip">SP-0091</span>
            </div>
          </div>
          <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--line)" }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-4)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 10 }}>{lang==="en"?"This week":"Cette semaine"}</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <div>
                <div style={{ fontFamily: "var(--font-display)", fontSize: 22, fontWeight: 600 }}>40<span style={{ fontSize: 13, color: "var(--ink-3)", fontWeight: 400 }}>h</span></div>
                <div style={{ fontSize: 11.5, color: "var(--ink-3)" }}>{lang==="en"?"Worked":"Travaillées"}</div>
              </div>
              <div>
                <div style={{ fontFamily: "var(--font-display)", fontSize: 22, fontWeight: 600 }}>3.5<span style={{ fontSize: 13, color: "var(--ink-3)", fontWeight: 400 }}>h</span></div>
                <div style={{ fontSize: 11.5, color: "var(--ink-3)" }}>{lang==="en"?"Overtime":"Heures sup."}</div>
              </div>
              <div>
                <div style={{ fontFamily: "var(--font-display)", fontSize: 22, fontWeight: 600 }}>0</div>
                <div style={{ fontSize: 11.5, color: "var(--ink-3)" }}>{lang==="en"?"Late":"Retards"}</div>
              </div>
              <div>
                <div style={{ fontFamily: "var(--font-display)", fontSize: 22, fontWeight: 600 }}>18<span style={{ fontSize: 13, color: "var(--ink-3)", fontWeight: 400 }}>j</span></div>
                <div style={{ fontSize: 11.5, color: "var(--ink-3)" }}>{lang==="en"?"Leave bal.":"Solde congés"}</div>
              </div>
            </div>
          </div>
          <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--line)" }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-4)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 10 }}>{lang==="en"?"Access groups":"Groupes d'accès"}</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              <span className="chip brand">LiSI · Bureaux</span>
              <span className="chip brand">LiSI · PC sécurité</span>
              <span className="chip">HQ · Visiteurs</span>
            </div>
          </div>
          <div style={{ padding: "14px 20px", display: "flex", gap: 8 }}>
            <button className="btn sm" style={{ flex: 1 }}>{tt("edit")}</button>
            <button className="btn sm primary" style={{ flex: 1 }}>{tt("viewProfile")}</button>
          </div>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { EmployeesScreen });
