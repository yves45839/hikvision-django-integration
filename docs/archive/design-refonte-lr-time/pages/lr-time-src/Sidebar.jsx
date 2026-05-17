/* global React */
const { useState } = React;

const Icon = ({ id, size = 16, style, className }) => (
  <svg width={size} height={size} className={className} style={style} aria-hidden="true">
    <use href={`#i-${id}`} />
  </svg>
);

const Sidebar = ({ active, onNav }) => {
  const items = [
    { group: 'Pilotage', entries: [
      { id: 'dashboard', label: 'Tableau de bord', icon: 'dashboard', href: 'dashboard.html' },
      { id: 'people',    label: 'Personnes',       icon: 'users',     count: 8 },
      { id: 'devices',   label: 'Appareils',       icon: 'cpu',       count: 3, href: 'devices.html' },
      { id: 'planning',  label: 'Planning',        icon: 'calendar',  href: 'planning.html' },
    ]},
    { group: 'Analyse', entries: [
      { id: 'reports',      label: 'Rapports',     icon: 'chart',  href: 'reports.html' },
      { id: 'surveillance', label: 'Surveillance', icon: 'shield' },
    ]},
    { group: 'Administration', entries: [
      { id: 'audit',    label: 'Journal d\'audit', icon: 'file' },
      { id: 'settings', label: 'Paramètres',       icon: 'settings' },
    ]},
  ];
  const goTo = (e) => {
    if (e.href) { window.location.href = e.href; return; }
    if (onNav) onNav(e.id);
  };
  return (
    <aside className="sb">
      <div className="sb__brand">
        <div className="sb__logo"></div>
        <div>
          <div className="nm">LR Time</div>
          <div className="sub">ACME-CASA</div>
        </div>
      </div>
      {items.map(g => (
        <div key={g.group}>
          <div className="sb__group">{g.group}</div>
          {g.entries.map(e => (
            <div
              key={e.id}
              className={`sb__item${active === e.id ? ' is-active' : ''}`}
              onClick={() => goTo(e)}
              role="link"
              style={{ cursor: 'pointer' }}
            >
              <Icon id={e.icon} />
              <span>{e.label}</span>
              {e.count != null && <span className="count">{e.count}</span>}
            </div>
          ))}
        </div>
      ))}
      <div className="sb__footer">
        <span className="pulse"></span>
        <span>Gateway connectée · 192.168.10.1</span>
      </div>
    </aside>
  );
};

window.Icon = Icon;
window.Sidebar = Sidebar;
