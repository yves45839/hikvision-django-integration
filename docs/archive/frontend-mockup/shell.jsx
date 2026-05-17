/* === Shared shell: Sidebar + Topbar === */
/* eslint-disable */

const I18N = {
  fr: {
    pilotage: "Pilotage",
    rh: "Ressources RH",
    infra: "Infrastructure",
    admin: "Administration",
    dashboard: "Tableau de bord",
    journals: "Journaux d'accès",
    reports: "Rapports",
    employees: "Équipe",
    planning: "Planning",
    absences: "Absences & congés",
    timesheet: "Validation pointages",
    devices: "Appareils",
    settings: "Paramètres",
    search: "Rechercher employé, badge, demande…",
    apiOnline: "API HikCentral connectée",
    quickAction: "Action rapide",
    today: "Aujourd'hui",
    thisWeek: "Cette semaine",
    needsAction: "À traiter",
    presentToday: "Présents aujourd'hui",
    onLeave: "En congé",
    pendingTimeAnomalies: "Anomalies pointages",
    pendingLeaveRequests: "Demandes en attente",
    overview: "Vue d'ensemble",
    teamView: "Mon équipe",
    activity: "Activité récente",
    upcomingLeave: "Congés à venir",
    quickActions: "Actions rapides",
    approveAll: "Tout valider",
    review: "Examiner",
    viewProfile: "Voir profil",
    approve: "Valider",
    reject: "Refuser",
    assign: "Affecter",
    edit: "Modifier",
    export: "Exporter",
    filter: "Filtrer",
    addEmployee: "Ajouter",
    publish: "Publier le planning",
    weekOf: "Semaine du",
    department: "Département",
    role: "Poste",
    status: "Statut",
    actions: "Actions",
    employee: "Employé",
    date: "Date",
    expected: "Attendu",
    actual: "Réel",
    delta: "Écart",
    type: "Type",
    period: "Période",
    duration: "Durée",
    requestedOn: "Demandé le",
    balance: "Solde",
    pending: "En attente",
    approved: "Validé",
    refused: "Refusé",
    auto: "Auto-validé",
    welcome: "Bonjour",
    summaryToday: "Voici votre journée",
    backToOverview: "Retour à la vue d'ensemble",
    save: "Enregistrer",
    cancel: "Annuler",
    nameAsc: "Nom (A → Z)",
    allDepts: "Tous départements",
    allStatuses: "Tous statuts",
  },
  en: {
    pilotage: "Operations",
    rh: "People",
    infra: "Infrastructure",
    admin: "Admin",
    dashboard: "Dashboard",
    journals: "Access logs",
    reports: "Reports",
    employees: "Team",
    planning: "Schedule",
    absences: "Time off",
    timesheet: "Timesheets",
    devices: "Devices",
    settings: "Settings",
    search: "Search employee, badge, request…",
    apiOnline: "HikCentral API online",
    quickAction: "Quick action",
    today: "Today",
    thisWeek: "This week",
    needsAction: "Needs action",
    presentToday: "Present today",
    onLeave: "On leave",
    pendingTimeAnomalies: "Time anomalies",
    pendingLeaveRequests: "Leave requests",
    overview: "Overview",
    teamView: "My team",
    activity: "Recent activity",
    upcomingLeave: "Upcoming leave",
    quickActions: "Quick actions",
    approveAll: "Approve all",
    review: "Review",
    viewProfile: "Profile",
    approve: "Approve",
    reject: "Reject",
    assign: "Assign",
    edit: "Edit",
    export: "Export",
    filter: "Filter",
    addEmployee: "Add",
    publish: "Publish schedule",
    weekOf: "Week of",
    department: "Department",
    role: "Role",
    status: "Status",
    actions: "Actions",
    employee: "Employee",
    date: "Date",
    expected: "Expected",
    actual: "Actual",
    delta: "Delta",
    type: "Type",
    period: "Period",
    duration: "Duration",
    requestedOn: "Requested",
    balance: "Balance",
    pending: "Pending",
    approved: "Approved",
    refused: "Refused",
    auto: "Auto-approved",
    welcome: "Hi",
    summaryToday: "Here's your day",
    backToOverview: "Back to overview",
    save: "Save",
    cancel: "Cancel",
    nameAsc: "Name (A → Z)",
    allDepts: "All departments",
    allStatuses: "All statuses",
  }
};

// Tiny inline icons (stroke). Lucide-ish.
const Icon = ({ name, className = "" }) => {
  const map = {
    home: "M3 12l9-9 9 9M5 10v10h14V10",
    grid: "M3 3h7v7H3zM14 3h7v7h-7zM14 14h7v7h-7zM3 14h7v7H3z",
    users: "M16 21v-2a4 4 0 00-4-4H6a4 4 0 00-4 4v2M9 11a4 4 0 100-8 4 4 0 000 8zM23 21v-2a4 4 0 00-3-3.87M17 3.13a4 4 0 010 7.75",
    calendar: "M19 4H5a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2V6a2 2 0 00-2-2zM16 2v4M8 2v4M3 10h18",
    clock: "M12 22a10 10 0 100-20 10 10 0 000 20zM12 6v6l4 2",
    plane: "M17.8 19.2L16 11l3.5-3.5C21 6 21.5 4 21 3c-1-.5-3 0-4.5 1.5L13 8 4.8 6.2c-.5-.1-.9.1-1.1.5l-.3.5c-.2.5-.1 1 .3 1.3L9 12l-2 3H4l-1 1 3 2 2 3 1-1v-3l3-2 3.5 5.3c.3.4.8.5 1.3.3l.5-.2c.4-.3.6-.7.5-1.2z",
    settings: "M12 15a3 3 0 100-6 3 3 0 000 6z M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 11-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 11-4 0v-.09a1.65 1.65 0 00-1-1.51 1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 11-2.83-2.83l.06-.06a1.65 1.65 0 00.33-1.82 1.65 1.65 0 00-1.51-1H3a2 2 0 110-4h.09a1.65 1.65 0 001.51-1 1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 112.83-2.83l.06.06a1.65 1.65 0 001.82.33h0a1.65 1.65 0 001-1.51V3a2 2 0 114 0v.09a1.65 1.65 0 001 1.51h0a1.65 1.65 0 001.82-.33l.06-.06a2 2 0 112.83 2.83l-.06.06a1.65 1.65 0 00-.33 1.82v0a1.65 1.65 0 001.51 1H21a2 2 0 110 4h-.09a1.65 1.65 0 00-1.51 1z",
    chart: "M3 3v18h18M7 14l4-4 3 3 5-6",
    cpu: "M4 4h16v16H4zM9 9h6v6H9zM9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 14h3M1 9h3M1 14h3",
    search: "M11 19a8 8 0 100-16 8 8 0 000 16zM21 21l-4.35-4.35",
    bell: "M18 8a6 6 0 10-12 0c0 7-3 9-3 9h18s-3-2-3-9 M13.73 21a2 2 0 01-3.46 0",
    plus: "M12 5v14M5 12h14",
    chevronRight: "M9 18l6-6-6-6",
    chevronDown: "M6 9l6 6 6-6",
    chevronLeft: "M15 18l-6-6 6-6",
    menu: "M3 12h18M3 6h18M3 18h18",
    check: "M20 6L9 17l-5-5",
    x: "M18 6L6 18M6 6l12 12",
    download: "M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3",
    filter: "M22 3H2l8 9.5V19l4 2v-8.5L22 3z",
    sparkle: "M12 3l1.5 5.5L19 10l-5.5 1.5L12 17l-1.5-5.5L5 10l5.5-1.5L12 3z M19 17l.5 1.5L21 19l-1.5.5L19 21l-.5-1.5L17 19l1.5-.5z",
    clipboard: "M9 3h6a2 2 0 012 2v0a2 2 0 01-2 2H9a2 2 0 01-2-2v0a2 2 0 012-2zM9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2",
    arrowUp: "M12 19V5M5 12l7-7 7 7",
    arrowDown: "M12 5v14M19 12l-7 7-7-7",
    user: "M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2M12 11a4 4 0 100-8 4 4 0 000 8z",
    morehoriz: "M5 12h.01M12 12h.01M19 12h.01",
    alert: "M12 9v4M12 17h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z",
  };
  const d = map[name];
  if (!d) return null;
  return (
    <svg className={"icn " + className} viewBox="0 0 24 24" fill="none"
         stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <path d={d} />
    </svg>
  );
};

const SP_LANG = window.SP_LANG || "fr";
const t = (k) => (I18N[window.SP_LANG || SP_LANG] || I18N.fr)[k] || k;

function Sidebar({ active, collapsed }) {
  const tt = (k) => I18N[window.SP_LANG || "fr"][k];
  const items = [
    { sec: tt("pilotage"), entries: [
      { id: "dashboard", label: tt("dashboard"), icon: "home" },
      { id: "journals", label: tt("journals"), icon: "clock" },
      { id: "reports", label: tt("reports"), icon: "chart" },
    ]},
    { sec: tt("rh"), entries: [
      { id: "employees", label: tt("employees"), icon: "users" },
      { id: "planning", label: tt("planning"), icon: "calendar" },
      { id: "timesheet", label: tt("timesheet"), icon: "clipboard", badge: 7 },
      { id: "absences", label: tt("absences"), icon: "plane", badge: 3 },
    ]},
    { sec: tt("infra"), entries: [
      { id: "devices", label: tt("devices"), icon: "cpu" },
    ]},
    { sec: tt("admin"), entries: [
      { id: "settings", label: tt("settings"), icon: "settings" },
    ]},
  ];
  return (
    <aside className="sb">
      <div className="sb-brand">
        <div className="sb-logo">SP</div>
        {!collapsed && (
          <div>
            <div className="sb-name">SecurePoint</div>
            <div className="sb-tenant">HQ — Casablanca</div>
          </div>
        )}
      </div>
      {items.map((g, i) => (
        <div key={i}>
          {!collapsed && <div className="sb-section">{g.sec}</div>}
          {g.entries.map((it) => (
            <div key={it.id} className={"sb-item " + (active === it.id ? "active" : "")}>
              <Icon name={it.icon} />
              <span>{it.label}</span>
              {it.badge && !collapsed && <span className="badge">{it.badge}</span>}
            </div>
          ))}
        </div>
      ))}
      <div className="sb-foot">
        <div className="av">JD</div>
        {!collapsed && (
          <div className="col" style={{ gap: 0 }}>
            <div className="who">Jamila Dahbi</div>
            <div className="role">Manager — Sécurité</div>
          </div>
        )}
      </div>
    </aside>
  );
}

function Topbar({ crumbs, lang, onLang, onCollapse }) {
  return (
    <div className="topbar">
      <button className="tb-collapse" onClick={onCollapse} aria-label="Collapse">
        <Icon name="menu" />
      </button>
      <div className="tb-crumbs">
        {crumbs.map((c, i) => (
          <React.Fragment key={i}>
            {i > 0 && <Icon name="chevronRight" className="" />}
            <span className={i === crumbs.length - 1 ? "" : "muted"}>
              {i === crumbs.length - 1 ? <strong>{c}</strong> : c}
            </span>
          </React.Fragment>
        ))}
      </div>
      <div className="tb-search">
        <Icon name="search" />
        <span>{I18N[lang].search}</span>
      </div>
      <div className="tb-spacer" />
      <span className="tb-pill">
        <span className="dot" />
        {I18N[lang].apiOnline}
      </span>
      <div className="tb-lang">
        <button className={lang === "fr" ? "on" : ""} onClick={() => onLang("fr")}>FR</button>
        <button className={lang === "en" ? "on" : ""} onClick={() => onLang("en")}>EN</button>
      </div>
      <button className="tb-icon-btn" aria-label="Notifications">
        <Icon name="bell" />
        <span className="ind" />
      </button>
      <div className="tb-avatar">JD</div>
    </div>
  );
}

Object.assign(window, { Sidebar, Topbar, Icon, I18N });
