/* global React, Icon */

const Topbar = ({ crumbs = ['Pilotage', 'Tableau de bord'] }) => (
  <header className="tb">
    <div className="tb__crumbs">
      {crumbs.slice(0, -1).map((c, i) => (
        <React.Fragment key={i}>
          <span>{c}</span>
          <Icon id="chevron-right" size={14} />
        </React.Fragment>
      ))}
      <strong>{crumbs[crumbs.length - 1]}</strong>
    </div>
    <div className="tb__search" role="button">
      <Icon id="search" size={14} />
      <span>Rechercher employé, site, lecteur…</span>
      <span className="kbd">⌘K</span>
    </div>
    <div className="tb__right">
      <button className="tb__icon" aria-label="Notifications">
        <Icon id="bell" size={18} />
        <span className="dot"></span>
      </button>
      <button className="tb__icon" aria-label="Paramètres">
        <Icon id="settings" size={18} />
      </button>
      <div className="tb__user">
        <div className="av">FB</div>
        <div>
          <div className="nm">Fatima Bennani</div>
          <div className="role">Admin RH</div>
        </div>
        <Icon id="chevron-down" size={14} style={{ color: 'var(--fg3)', marginLeft: 4 }} />
      </div>
    </div>
  </header>
);

window.Topbar = Topbar;
