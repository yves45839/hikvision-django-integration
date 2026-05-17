/* === Diagnostic + System overview slide === */
/* eslint-disable */

const dgStyles = {
  page: { padding: "32px 40px", maxWidth: 1440, margin: "0 auto" },
  hero: { marginBottom: 28 },
  twoCol: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18, marginBottom: 22 },
  col3: { display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 14, marginBottom: 22 },
  diag: {
    background: "var(--surface)", border: "1px solid var(--line)",
    borderRadius: 14, padding: "20px 22px",
  },
  pillRow: { display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 },
  swatchGrid: { display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 8, marginTop: 10 },
  swatch: { borderRadius: 8, padding: "20px 12px 10px", color: "white", fontSize: 11, fontWeight: 600, fontFamily: "var(--font-mono)" },
  typeRow: { padding: "10px 0", borderBottom: "1px solid var(--line)" },
};

function DiagnosticScreen({ lang }) {
  const findings = lang === "en" ? [
    { sev: "danger", t: "Permanent dark theme", d: "Industry HR ERPs default to light. Dark adds cognitive load on dense tables, fights brand colors, and signals 'security ops' instead of 'people ops'." },
    { sev: "warn", t: "Dashboard ≠ manager dashboard", d: "Current home is an access-events feed. A team manager needs: actions to take today, who's present, anomalies to validate. Reorder by intent." },
    { sev: "warn", t: "Planning entry is empty boxes", d: "Three large empty placeholders ('Timetable', 'Shift', 'Shift Schedule') with no semantic meaning to a manager. No weekly grid, no coverage view." },
    { sev: "warn", t: "Tech vocabulary leaks to UI", d: "'Timetable', 'Shift Schedule', 'tenant', 'webhook', 'gateway' belong to ops dashboards, not HR managers. Rename to 'Schedule', 'Shifts', 'Site'." },
    { sev: "info", t: "No clear validation flow", d: "Time anomalies and leave requests are scattered. Manager journey expects a single 'inbox' with batch validation, AI suggestions, and conflict warnings." },
    { sev: "info", t: "Sidebar groups are ops-first", d: "Pilotage / Infrastructure dominate. RH section needs more weight + dedicated 'Time off' and 'Timesheets'." },
  ] : [
    { sev: "danger", t: "Thème sombre permanent", d: "Les ERP RH du marché sont en thème clair par défaut. Le sombre alourdit la charge cognitive sur les tableaux denses et signale 'supervision sécurité' plutôt que 'gestion RH'." },
    { sev: "warn", t: "Dashboard ≠ tableau de bord manager", d: "L'accueil actuel est un flux d'événements d'accès. Un manager d'équipe a besoin : actions du jour, présence, anomalies à valider. Réordonner par intention." },
    { sev: "warn", t: "Planning vide à l'entrée", d: "Trois grosses cases vides ('Timetable', 'Shift', 'Shift Schedule') sans sens métier. Pas de grille hebdomadaire, pas de vue couverture." },
    { sev: "warn", t: "Vocabulaire technique en surface", d: "'Timetable', 'Shift Schedule', 'tenant', 'webhook', 'gateway' relèvent du backend, pas du manager RH. Renommer en 'Planning', 'Quarts', 'Site'." },
    { sev: "info", t: "Pas de parcours de validation clair", d: "Anomalies pointage et demandes congés sont éparses. Le parcours manager attend une 'boîte de réception' unique avec validation par lot, suggestions IA, alertes de conflit." },
    { sev: "info", t: "Sidebar trop ops, pas assez RH", d: "Pilotage / Infrastructure dominent. La section RH a besoin de plus de poids + 'Absences' et 'Validation pointages' dédiés." },
  ];

  const principles = lang === "en" ? [
    { t: "Light, warm, human", d: "Default light theme. Subtle warm neutrals. Color reserved for status, not chrome." },
    { t: "Manager-intent first", d: "Every screen opens on what the manager must decide today, not raw data feeds." },
    { t: "Batch validation", d: "Time anomalies and leave requests share one validation pattern: bulk approve, single-click reject, AI suggestions." },
    { t: "Conflict-aware", d: "Schedules and leave requests show coverage drops, overlaps, balance impact — inline, not after submission." },
    { t: "Bilingual ops", d: "FR/EN toggle in topbar. All HR vocabulary localized; technical terms removed from manager-facing surfaces." },
  ] : [
    { t: "Clair, chaud, humain", d: "Thème clair par défaut. Neutres légèrement chauds. Couleur réservée au statut, pas au décor." },
    { t: "Intention manager d'abord", d: "Chaque écran s'ouvre sur ce que le manager doit décider aujourd'hui, pas sur un flux de données." },
    { t: "Validation par lot", d: "Anomalies de pointage et demandes de congés partagent un même pattern : valider en masse, refuser en un clic, suggestions IA." },
    { t: "Conscient des conflits", d: "Plannings et congés affichent les ruptures de couverture, chevauchements, impact solde — en ligne, pas après soumission." },
    { t: "Opérations bilingues", d: "Toggle FR/EN dans la topbar. Vocabulaire RH localisé ; termes techniques retirés des surfaces manager." },
  ];

  return (
    <div style={dgStyles.page}>
      <div style={dgStyles.hero}>
        <div style={{ fontSize: 12, fontWeight: 600, color: "var(--brand-ink)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>
          {lang === "en" ? "Redesign proposal" : "Proposition de refonte"}
        </div>
        <h1 style={{ fontFamily: "var(--font-display)", fontSize: 32, fontWeight: 600, letterSpacing: "-0.025em", margin: "0 0 6px" }}>
          {lang === "en"
            ? "From ops console to manager-first HR ERP"
            : "D'un console d'exploitation vers un ERP RH orienté manager"}
        </h1>
        <p style={{ fontSize: 15, color: "var(--ink-2)", margin: 0, maxWidth: 720, lineHeight: 1.55 }}>
          {lang === "en"
            ? "5 redesigned screens · light theme · BambooHR-meets-Sage HR aesthetic. Functional scope preserved (people, schedule, time, access, devices); information architecture and validation flows reshaped around the team-manager persona."
            : "5 écrans repensés · thème clair · esthétique inspirée BambooHR / Sage HR. Périmètre fonctionnel préservé (personnes, planning, temps, accès, appareils) ; architecture de l'information et parcours de validation réorganisés autour du persona manager d'équipe."}
        </p>
      </div>

      <div style={dgStyles.twoCol}>
        <div style={dgStyles.diag}>
          <h3 style={{ margin: "0 0 4px", fontFamily: "var(--font-display)", fontSize: 16 }}>
            {lang === "en" ? "Diagnostic — what we observed" : "Diagnostic — ce que l'on observe"}
          </h3>
          <p className="muted smaller" style={{ margin: "0 0 14px" }}>
            {lang === "en" ? "From the current SecurePoint frontend" : "À partir du frontend SecurePoint actuel"}
          </p>
          {findings.map((f, i) => (
            <div key={i} style={{ display: "flex", gap: 12, padding: "10px 0", borderTop: i === 0 ? 0 : "1px solid var(--line)" }}>
              <span className={"chip " + (f.sev === "danger" ? "danger" : f.sev === "warn" ? "warn" : "info")} style={{ flexShrink: 0, alignSelf: "flex-start", marginTop: 2 }}>
                <span className="dot" />
                {f.sev === "danger" ? (lang==="en"?"Critical":"Critique") : f.sev === "warn" ? (lang==="en"?"Major":"Majeur") : "Info"}
              </span>
              <div>
                <div style={{ fontSize: 13.5, fontWeight: 600 }}>{f.t}</div>
                <div className="smaller muted" style={{ marginTop: 2, lineHeight: 1.5 }}>{f.d}</div>
              </div>
            </div>
          ))}
        </div>

        <div style={dgStyles.diag}>
          <h3 style={{ margin: "0 0 4px", fontFamily: "var(--font-display)", fontSize: 16 }}>
            {lang === "en" ? "Design principles" : "Principes de design"}
          </h3>
          <p className="muted smaller" style={{ margin: "0 0 14px" }}>
            {lang === "en" ? "What guides every redesigned screen" : "Ce qui guide chaque écran refondu"}
          </p>
          {principles.map((p, i) => (
            <div key={i} style={{ display: "flex", gap: 12, padding: "10px 0", borderTop: i === 0 ? 0 : "1px solid var(--line)", alignItems: "flex-start" }}>
              <div style={{ width: 24, height: 24, borderRadius: 6, background: "var(--brand-soft)", color: "var(--brand-ink)", display: "grid", placeItems: "center", fontFamily: "var(--font-display)", fontSize: 12, fontWeight: 700, flexShrink: 0 }}>{i+1}</div>
              <div>
                <div style={{ fontSize: 13.5, fontWeight: 600 }}>{p.t}</div>
                <div className="smaller muted" style={{ marginTop: 2, lineHeight: 1.5 }}>{p.d}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div style={dgStyles.col3}>
        <div style={dgStyles.diag}>
          <div style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-4)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
            {lang === "en" ? "Color system" : "Couleurs"}
          </div>
          <h4 style={{ margin: "4px 0 0", fontSize: 14, fontWeight: 600 }}>
            {lang === "en" ? "Sage as primary, status colors reserved" : "Vert sauge primaire, couleurs réservées au statut"}
          </h4>
          <div style={dgStyles.swatchGrid}>
            <div style={{...dgStyles.swatch, background: "var(--brand)"}}>brand</div>
            <div style={{...dgStyles.swatch, background: "var(--success)"}}>success</div>
            <div style={{...dgStyles.swatch, background: "var(--warn)", color: "var(--warn-ink)"}}>warn</div>
            <div style={{...dgStyles.swatch, background: "var(--danger)"}}>danger</div>
            <div style={{...dgStyles.swatch, background: "var(--info)"}}>info</div>
            <div style={{...dgStyles.swatch, background: "var(--absence)"}}>absence</div>
          </div>
          <div className="smaller muted" style={{ marginTop: 10, lineHeight: 1.5 }}>
            {lang === "en"
              ? "All accents share constant chroma 0.12–0.18 and lightness 0.6–0.7 for visual consistency in chips and badges."
              : "Tous les accents partagent une chroma constante 0.12–0.18 et luminosité 0.6–0.7 pour une cohérence des chips et badges."}
          </div>
        </div>

        <div style={dgStyles.diag}>
          <div style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-4)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
            {lang === "en" ? "Type" : "Typographie"}
          </div>
          <h4 style={{ margin: "4px 0 0", fontSize: 14, fontWeight: 600 }}>Inter + Inter Tight</h4>
          <div style={dgStyles.typeRow}>
            <div style={{ fontFamily: "var(--font-display)", fontSize: 24, fontWeight: 600, letterSpacing: "-0.02em" }}>Display 24/600</div>
            <div className="smaller muted">{lang==="en"?"H1, hero, KPI numbers":"Titres, hero, KPI"}</div>
          </div>
          <div style={dgStyles.typeRow}>
            <div style={{ fontSize: 15, fontWeight: 600 }}>Heading 15/600</div>
            <div className="smaller muted">{lang==="en"?"Card titles":"Titres de carte"}</div>
          </div>
          <div style={dgStyles.typeRow}>
            <div style={{ fontSize: 14 }}>Body 14/400 — Validation pointages</div>
            <div className="smaller muted">{lang==="en"?"Default body":"Corps par défaut"}</div>
          </div>
          <div style={{ ...dgStyles.typeRow, borderBottom: 0 }}>
            <div className="mono" style={{ fontSize: 12.5 }}>Mono 12.5 — 06:24 → 14:05</div>
            <div className="smaller muted">{lang==="en"?"Times, IDs, deltas":"Heures, identifiants, écarts"}</div>
          </div>
        </div>

        <div style={dgStyles.diag}>
          <div style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-4)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
            {lang === "en" ? "Information architecture" : "Architecture de l'information"}
          </div>
          <h4 style={{ margin: "4px 0 12px", fontSize: 14, fontWeight: 600 }}>
            {lang === "en" ? "Sidebar restructured" : "Sidebar restructurée"}
          </h4>
          <div style={{ fontSize: 12, lineHeight: 1.7 }}>
            <div><strong style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: "0.07em", color: "var(--ink-4)" }}>{lang==="en"?"Operations":"Pilotage"}</strong></div>
            <div className="muted">Dashboard · {lang==="en"?"Access logs":"Journaux"} · {lang==="en"?"Reports":"Rapports"}</div>
            <div style={{ marginTop: 8 }}><strong style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: "0.07em", color: "var(--brand-ink)" }}>{lang==="en"?"People (expanded)":"RH (renforcé)"}</strong></div>
            <div style={{ color: "var(--brand-ink)", fontWeight: 600 }}>
              {lang==="en"?"Team · Schedule · Timesheets · Time off":"Équipe · Planning · Validation pointages · Absences"}
            </div>
            <div style={{ marginTop: 8 }}><strong style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: "0.07em", color: "var(--ink-4)" }}>{lang==="en"?"Infrastructure":"Infrastructure"}</strong></div>
            <div className="muted">{lang==="en"?"Devices":"Appareils"}</div>
            <div style={{ marginTop: 8 }}><strong style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: "0.07em", color: "var(--ink-4)" }}>{lang==="en"?"Admin":"Administration"}</strong></div>
            <div className="muted">{lang==="en"?"Settings":"Paramètres"}</div>
          </div>
          <div className="smaller muted" style={{ marginTop: 14, lineHeight: 1.5 }}>
            {lang==="en"
              ? "+2 dedicated entries for the manager journey. Technical sections demoted, not removed."
              : "+2 entrées dédiées au parcours manager. Sections techniques rétrogradées, pas supprimées."}
          </div>
        </div>
      </div>

      <div style={{ ...dgStyles.diag, background: "var(--brand-soft)", border: "1px solid oklch(0.85 0.06 165)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div style={{ width: 44, height: 44, borderRadius: 12, background: "var(--brand)", color: "white", display: "grid", placeItems: "center", flexShrink: 0 }}>
            <Icon name="chevronRight" />
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 600, fontSize: 14, color: "var(--brand-ink)" }}>
              {lang === "en" ? "How to read what's next" : "Comment lire la suite"}
            </div>
            <div className="smaller" style={{ color: "var(--brand-ink)", opacity: 0.85, marginTop: 2 }}>
              {lang === "en"
                ? "Five fullscreen artboards follow: Manager dashboard → Team list → Timesheet validation (focus journey) → Weekly schedule → Time off requests. Click any artboard to enter focus mode."
                : "Cinq maquettes plein écran suivent : Dashboard manager → Liste équipe → Validation pointages (parcours focus) → Planning hebdo → Demandes de congés. Cliquez une maquette pour le mode focus."}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { DiagnosticScreen });
