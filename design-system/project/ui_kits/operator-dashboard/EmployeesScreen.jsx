/* global React, Icon */

const EMPLOYEES = [
  { mat: 'EMP-00214', name: 'Nadia Amrani', role: 'Production · Hall A', site: 'Casablanca', bio: 'enrolled', last: '08:02', av: '' },
  { mat: 'EMP-00187', name: 'Youssef Benali', role: 'Sécurité · Hall B', site: 'Casablanca', bio: 'enrolled', last: '08:14', av: 'av-blue' },
  { mat: 'EMP-00309', name: 'Sara El Idrissi', role: 'RH · Siège', site: 'Rabat', bio: 'enrolled', last: '—', av: 'av-pink' },
  { mat: 'EMP-00342', name: 'Mehdi Kabbaj', role: 'Production · Hall A', site: 'Casablanca', bio: 'enrolled', last: '07:58', av: 'av-green' },
  { mat: 'EMP-00401', name: 'Karim Tazi', role: 'Production · Hall A', site: 'Casablanca', bio: 'enrolled', last: '08:02', av: 'av-violet' },
  { mat: 'EMP-00455', name: 'Imane Ouazzani', role: 'RH · Siège', site: 'Rabat', bio: 'pending', last: '—', av: 'av-pink' },
  { mat: 'EMP-00478', name: 'Hamza Lahlou', role: 'Maintenance', site: 'Casablanca', bio: 'enrolled', last: '07:51', av: '' },
];

const EmployeesScreen = () => {
  const cols = '36px 2.2fr 1.6fr 1fr 1fr 1fr 110px';
  return (
    <div>
      <div className="ph">
        <div>
          <h1 className="ph__title">Employés</h1>
          <p className="ph__sub">163 actifs sur 2 sites · 1 enrôlement biométrique en attente.</p>
        </div>
        <div className="ph__actions">
          <button className="btn btn--secondary"><Icon id="download" size={16}/> Exporter</button>
          <button className="btn btn--secondary"><Icon id="file" size={16}/> Importer CSV</button>
          <button className="btn btn--primary"><Icon id="plus" size={16}/> Ajouter un employé</button>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 16, alignItems: 'center' }}>
        <div style={{ position: 'relative', flex: 1, maxWidth: 360 }}>
          <Icon id="search" size={14} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--fg3)' }}/>
          <input type="text" placeholder="Rechercher par nom ou matricule…" style={{ width: '100%', height: 36, borderRadius: 8, border: '1px solid var(--border-default)', background: 'var(--bg-surface)', padding: '0 12px 0 34px', fontSize: 13, color: 'var(--fg1)', fontFamily: 'var(--font-sans)' }}/>
        </div>
        <span className="badge b-brand" style={{ height: 28, padding: '0 12px', fontSize: 12.5 }}>Tous · 163</span>
        <span className="badge b-neutral" style={{ height: 28, padding: '0 12px', fontSize: 12.5 }}>Production · 84</span>
        <span className="badge b-neutral" style={{ height: 28, padding: '0 12px', fontSize: 12.5 }}>RH · 12</span>
        <span className="badge b-accent" style={{ height: 28, padding: '0 12px', fontSize: 12.5 }}>Enrôlement en attente · 1</span>
      </div>

      <div className="card" style={{ padding: 0 }}>
        <div className="tbl">
          <div className="tbl__hd" style={{ gridTemplateColumns: cols }}>
            <div></div><div>Employé</div><div>Matricule · Rôle</div><div>Site</div><div>Biométrie</div><div>Dernier pointage</div><div></div>
          </div>
          {EMPLOYEES.map(e => (
            <div key={e.mat} className="tbl__row" style={{ gridTemplateColumns: cols }}>
              <div className={`av ${e.av || ''}`}>{e.name.split(' ').map(s => s[0]).slice(0,2).join('')}</div>
              <div>
                <div style={{ color: 'var(--fg1)', fontWeight: 600, fontSize: 13.5 }}>{e.name}</div>
                <div style={{ color: 'var(--fg3)', fontSize: 12 }}>{e.role}</div>
              </div>
              <div>
                <div className="mono" style={{ fontSize: 12.5, color: 'var(--fg2)' }}>{e.mat}</div>
              </div>
              <div style={{ fontSize: 13 }}>{e.site}</div>
              <div>
                {e.bio === 'enrolled'
                  ? <span className="badge b-ok"><span className="dot"></span>Enrôlée</span>
                  : <span className="badge b-warn"><span className="dot"></span>En attente</span>}
              </div>
              <div className="mono" style={{ fontSize: 12.5, color: 'var(--fg2)' }}>{e.last}</div>
              <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                <button className="btn btn--ghost btn--sm">Voir</button>
                <button className="btn btn--ghost btn--icon btn--sm"><Icon id="more" size={14}/></button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

window.EmployeesScreen = EmployeesScreen;
