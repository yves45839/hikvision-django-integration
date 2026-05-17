/* global React, Icon */
const { useState: useStateD } = React;

const DEVICES = [
  { id: 'DS-K1T343-001', name: 'Caméra Hall A · Entrée', site: 'Casablanca', ip: '192.168.10.42', model: 'DS-K1T343MFWX', fw: '6.2.4', last: '12 s', status: 'ok', events: 87 },
  { id: 'DS-K1T343-002', name: 'Caméra Hall A · Sortie', site: 'Casablanca', ip: '192.168.10.43', model: 'DS-K1T343MFWX', fw: '6.2.4', last: '18 s', status: 'ok', events: 84 },
  { id: 'DS-K1T343-003', name: 'Caméra Hall B · Entrée', site: 'Casablanca', ip: '192.168.10.51', model: 'DS-K1T343MFWX', fw: '6.2.1', last: '4 min', status: 'warn', events: 41 },
  { id: 'DS-K1T343-004', name: 'Lecteur Production', site: 'Casablanca', ip: '192.168.10.60', model: 'DS-K1A340MX', fw: '6.2.4', last: '9 s', status: 'ok', events: 213 },
  { id: 'DS-K1T343-005', name: 'Lecteur Parking', site: 'Casablanca', ip: '192.168.10.71', model: 'DS-K1A340MX', fw: '6.1.8', last: '2h12', status: 'bad', events: 0 },
  { id: 'DS-K1T343-006', name: 'Lecteur Siège · Accueil', site: 'Rabat', ip: '192.168.20.10', model: 'DS-K1T343MFWX', fw: '6.2.4', last: '31 s', status: 'ok', events: 56 },
];

const DeviceDrawer = ({ device, onClose }) => (
  <>
    <div className={`drawer__veil${device ? ' is-open' : ''}`} onClick={onClose}></div>
    <aside className={`drawer${device ? ' is-open' : ''}`} aria-hidden={!device}>
      {device && <>
        <div className="drawer__hd">
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{ width: 40, height: 40, borderRadius: 10, background: 'var(--brand-soft)', color: 'var(--brand)', display: 'grid', placeItems: 'center' }}>
              <Icon id="camera" size={20}/>
            </div>
            <div>
              <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 16, color: 'var(--fg1)' }}>{device.name}</div>
              <div className="mono" style={{ fontSize: 12, color: 'var(--fg3)' }}>{device.id}</div>
            </div>
          </div>
          <button className="btn btn--ghost btn--icon" onClick={onClose}><Icon id="x" size={16}/></button>
        </div>
        <div className="drawer__bd">
          <div style={{ display: 'flex', gap: 8, marginBottom: 18 }}>
            <span className={`badge ${device.status === 'ok' ? 'b-ok' : device.status === 'warn' ? 'b-warn' : 'b-bad'}`}><span className="dot"></span>{device.status === 'ok' ? `Actif · ${device.last}` : device.status === 'warn' ? `Lent · ${device.last}` : `Hors ligne · ${device.last}`}</span>
            <span className="badge b-brand">Tenant ACME-CASA</span>
          </div>
          <div className="t-eyebrow" style={{ marginBottom: 8 }}>Identité</div>
          <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr', rowGap: 10, columnGap: 16, fontSize: 13.5, marginBottom: 22 }}>
            <span style={{ color: 'var(--fg3)' }}>Modèle</span><span className="mono" style={{ color: 'var(--fg1)' }}>{device.model}</span>
            <span style={{ color: 'var(--fg3)' }}>Firmware</span><span className="mono" style={{ color: 'var(--fg1)' }}>{device.fw}</span>
            <span style={{ color: 'var(--fg3)' }}>Adresse IP</span><span className="mono" style={{ color: 'var(--fg1)' }}>{device.ip} · TLS</span>
            <span style={{ color: 'var(--fg3)' }}>Site</span><span style={{ color: 'var(--fg1)' }}>{device.site}</span>
          </div>
          <div className="t-eyebrow" style={{ marginBottom: 8 }}>Activité</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 22 }}>
            <div style={{ padding: 14, background: 'var(--bg-muted)', borderRadius: 10 }}>
              <div className="tnum" style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 22, color: 'var(--fg1)' }}>{device.events}</div>
              <div style={{ fontSize: 11.5, color: 'var(--fg3)' }}>pointages aujourd'hui</div>
            </div>
            <div style={{ padding: 14, background: 'var(--bg-muted)', borderRadius: 10 }}>
              <div className="tnum" style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 22, color: 'var(--fg1)' }}>0</div>
              <div style={{ fontSize: 11.5, color: 'var(--fg3)' }}>échecs de lecture</div>
            </div>
          </div>
          <div className="t-eyebrow" style={{ marginBottom: 8 }}>Journal récent</div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg2)', background: 'var(--bg-muted)', borderRadius: 10, padding: 14, lineHeight: 1.7 }}>
            <div>09:47:13 · ping OK · rtt 38ms</div>
            <div>09:46:02 · badge Nadia Amrani · OK</div>
            <div>09:45:48 · badge Karim Tazi · OK</div>
            <div>09:44:21 · biométrie Y. Benali · ECHEC retry</div>
            <div>09:44:25 · biométrie Y. Benali · OK</div>
          </div>
        </div>
        <div className="drawer__ft">
          <button className="btn btn--ghost">Désactiver</button>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn--secondary">Redémarrer</button>
            <button className="btn btn--primary"><Icon id="settings" size={16}/> Configurer</button>
          </div>
        </div>
      </>}
    </aside>
  </>
);

const DevicesScreen = () => {
  const [open, setOpen] = useStateD(null);
  const [selected, setSelected] = useStateD('DS-K1T343-003');
  const cols = '32px 2.4fr 1fr 1.4fr 1fr 110px 28px';
  return (
    <div>
      <div className="ph">
        <div>
          <h1 className="ph__title">Appareils Hikvision</h1>
          <p className="ph__sub">6 appareils sur 2 sites — 5 en ligne, 1 hors ligne. Synchronisé via gateway HikCentral.</p>
        </div>
        <div className="ph__actions">
          <button className="btn btn--secondary"><Icon id="filter" size={16}/> Filtres</button>
          <button className="btn btn--primary"><Icon id="plus" size={16}/> Ajouter un appareil</button>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <span className="badge b-brand" style={{ height: 28, padding: '0 12px', fontSize: 12.5 }}>Tous · 6</span>
        <span className="badge b-neutral" style={{ height: 28, padding: '0 12px', fontSize: 12.5 }}>En ligne · 5</span>
        <span className="badge b-neutral" style={{ height: 28, padding: '0 12px', fontSize: 12.5 }}>Hors ligne · 1</span>
        <span className="badge b-neutral" style={{ height: 28, padding: '0 12px', fontSize: 12.5 }}>Casablanca · 5</span>
        <span className="badge b-neutral" style={{ height: 28, padding: '0 12px', fontSize: 12.5 }}>Rabat · 1</span>
      </div>

      <div className="card" style={{ padding: 0 }}>
        <div className="tbl">
          <div className="tbl__hd" style={{ gridTemplateColumns: cols }}>
            <div></div><div>Appareil</div><div>Site</div><div>Adresse IP · Firmware</div><div>Activité</div><div>État</div><div></div>
          </div>
          {DEVICES.map(d => (
            <div
              key={d.id}
              className={`tbl__row${selected === d.id ? ' is-selected' : ''}`}
              style={{ gridTemplateColumns: cols }}
              onClick={() => { setSelected(d.id); setOpen(d); }}
            >
              <div style={{ width: 32, height: 32, borderRadius: 8, background: 'var(--brand-soft)', color: 'var(--brand)', display: 'grid', placeItems: 'center' }}>
                <Icon id={d.model.includes('K1T') ? 'camera' : 'fingerprint'} size={16}/>
              </div>
              <div>
                <div style={{ color: 'var(--fg1)', fontWeight: 600, fontSize: 13.5 }}>{d.name}</div>
                <div className="mono" style={{ color: 'var(--fg3)', fontSize: 11.5 }}>{d.id} · {d.model}</div>
              </div>
              <div style={{ fontSize: 13 }}>{d.site}</div>
              <div className="mono" style={{ fontSize: 12, color: 'var(--fg2)' }}>{d.ip} · fw {d.fw}</div>
              <div style={{ fontSize: 13 }}>
                <div className="tnum" style={{ color: 'var(--fg1)', fontWeight: 600 }}>{d.events} pointages</div>
                <div style={{ color: 'var(--fg3)', fontSize: 11.5 }}>il y a {d.last}</div>
              </div>
              <div>
                <span className={`badge ${d.status === 'ok' ? 'b-ok' : d.status === 'warn' ? 'b-warn' : 'b-bad'}`}><span className="dot"></span>{d.status === 'ok' ? 'En ligne' : d.status === 'warn' ? 'Lent' : 'Hors ligne'}</span>
              </div>
              <div style={{ color: 'var(--fg3)', display: 'grid', placeItems: 'center' }}><Icon id="more" size={16}/></div>
            </div>
          ))}
        </div>
      </div>

      <DeviceDrawer device={open} onClose={() => setOpen(null)}/>
    </div>
  );
};

window.DevicesScreen = DevicesScreen;
