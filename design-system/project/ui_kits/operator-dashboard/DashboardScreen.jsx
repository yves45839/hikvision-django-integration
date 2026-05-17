/* global React, Icon, KpiCard */
const { useMemo } = React;

const Sparkline = ({ data, color = 'var(--brand)', height = 60 }) => {
  const w = 100, h = 100;
  const max = Math.max(...data), min = Math.min(...data);
  const range = max - min || 1;
  const stepX = w / (data.length - 1);
  const pts = data.map((v, i) => `${i * stepX},${h - ((v - min) / range) * h}`).join(' ');
  const areaPts = `0,${h} ${pts} ${w},${h}`;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{ width: '100%', height }}>
      <defs>
        <linearGradient id="sparkfill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.18"/>
          <stop offset="100%" stopColor={color} stopOpacity="0"/>
        </linearGradient>
      </defs>
      <polygon points={areaPts} fill="url(#sparkfill)"/>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke"/>
    </svg>
  );
};

const PresenceChart = () => {
  const data = [12, 28, 64, 92, 118, 132, 142, 145, 144, 147, 142, 140];
  const labels = ['07:00','','08:00','','09:00','','10:00','','11:00','','12:00','13:00'];
  return (
    <div className="card">
      <div className="card__hd">
        <div>
          <h3 className="card__title">Pointages — aujourd'hui</h3>
          <p className="card__sub">Cumul des arrivées par tranche de 30 minutes · objectif 8h00</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <span className="badge b-ok"><span className="dot"></span>Live · 09:47</span>
          <button className="btn btn--ghost btn--sm"><Icon id="download" size={14}/> CSV</button>
        </div>
      </div>
      <div className="card__bd" style={{ paddingTop: 0 }}>
        <div style={{ display: 'flex', gap: 28, marginBottom: 12, alignItems: 'baseline' }}>
          <div>
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 28, color: 'var(--fg1)', letterSpacing: '-0.02em' }} className="tnum">142</div>
            <div style={{ fontSize: 12, color: 'var(--fg3)' }}>arrivées · 87% de couverture</div>
          </div>
          <div>
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 18, color: 'var(--success-700)' }}>▲ 4</div>
            <div style={{ fontSize: 12, color: 'var(--fg3)' }}>vs hier 09:47</div>
          </div>
          <div>
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 18, color: 'var(--warning-700)' }}>9 retards</div>
            <div style={{ fontSize: 12, color: 'var(--fg3)' }}>moyenne 14 min</div>
          </div>
        </div>
        <Sparkline data={data} height={120}/>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg4)', marginTop: 6 }}>
          {labels.map((l, i) => <span key={i}>{l}</span>)}
        </div>
      </div>
    </div>
  );
};

const AnomalyRow = ({ av, name, role, kind, when, severity }) => (
  <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 0', borderBottom: '1px solid var(--border-subtle)' }}>
    <div className={`av ${av || ''}`}>{name.split(' ').map(s => s[0]).slice(0,2).join('')}</div>
    <div style={{ flex: 1, minWidth: 0 }}>
      <div style={{ color: 'var(--fg1)', fontWeight: 500, fontSize: 13.5 }}>{name}</div>
      <div style={{ color: 'var(--fg3)', fontSize: 12 }}>{role} · {kind}</div>
    </div>
    <span className="mono" style={{ fontSize: 12, color: 'var(--fg3)' }}>{when}</span>
    <span className={`badge ${severity === 'bad' ? 'b-bad' : severity === 'warn' ? 'b-warn' : 'b-info'}`}><span className="dot"></span>{severity === 'bad' ? 'Absent' : severity === 'warn' ? 'Retard' : 'À vérifier'}</span>
    <button className="btn btn--secondary btn--sm">Examiner</button>
  </div>
);

const DeviceStrip = () => {
  const devices = [
    { name: 'Hall A · Entrée', ip: '192.168.10.42', status: 'ok', last: '12 s' },
    { name: 'Hall A · Sortie', ip: '192.168.10.43', status: 'ok', last: '18 s' },
    { name: 'Hall B · Entrée', ip: '192.168.10.51', status: 'warn', last: '4 min' },
    { name: 'Production', ip: '192.168.10.60', status: 'ok', last: '9 s' },
    { name: 'Parking', ip: '192.168.10.71', status: 'bad', last: '2h12' },
  ];
  return (
    <div className="card">
      <div className="card__hd">
        <div>
          <h3 className="card__title">Lecteurs & caméras</h3>
          <p className="card__sub">5 appareils synchronisés via gateway HikCentral</p>
        </div>
        <button className="btn btn--ghost btn--sm">Tout voir →</button>
      </div>
      <div className="card__bd" style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 10 }}>
        {devices.map(d => (
          <div key={d.ip} style={{ border: '1px solid var(--border-subtle)', borderRadius: 12, padding: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ width: 28, height: 28, borderRadius: 7, background: 'var(--brand-soft)', color: 'var(--brand)', display: 'grid', placeItems: 'center' }}>
                <Icon id="camera" size={14}/>
              </div>
              <span className={`badge ${d.status === 'ok' ? 'b-ok' : d.status === 'warn' ? 'b-warn' : 'b-bad'}`} style={{ height: 18, padding: '0 8px', fontSize: 10.5 }}><span className="dot"></span>{d.status === 'ok' ? 'OK' : d.status === 'warn' ? 'Lent' : 'Off'}</span>
            </div>
            <div>
              <div style={{ fontSize: 13, color: 'var(--fg1)', fontWeight: 600 }}>{d.name}</div>
              <div className="mono" style={{ fontSize: 11, color: 'var(--fg3)', marginTop: 2 }}>{d.ip}</div>
            </div>
            <div style={{ fontSize: 11.5, color: 'var(--fg3)' }}>il y a {d.last}</div>
          </div>
        ))}
      </div>
    </div>
  );
};

const DashboardScreen = () => (
  <div>
    <div className="ph">
      <div>
        <h1 className="ph__title">Bonjour Fatima · jeudi 16 janvier</h1>
        <p className="ph__sub">142 personnes pointées · 87% de couverture · 14 anomalies à traiter avant 11 h.</p>
      </div>
      <div className="ph__actions">
        <button className="btn btn--secondary"><Icon id="refresh" size={16}/> Actualiser</button>
        <button className="btn btn--primary"><Icon id="download" size={16}/> Exporter la journée</button>
      </div>
    </div>

    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 20 }}>
      <KpiCard label="Présents aujourd'hui" icon="users" value="142" denom="163" delta="4 vs hier" sub="Couverture 87%" tone="brand"/>
      <KpiCard label="Anomalies à traiter" icon="alert" value="14" delta="6 vs hier" deltaDir="down" sub="Avant 11h" tone="accent"/>
      <KpiCard label="Appareils actifs" icon="cpu" value="31" denom="32" delta="stable" sub="1 hors ligne · Parking" tone="ok"/>
      <KpiCard label="Retard moyen" icon="clock" value="9" unit="min" delta="2 min" deltaDir="down" sub="Sur 23 retards" tone="warn"/>
    </div>

    <div style={{ display: 'grid', gridTemplateColumns: '1.7fr 1fr', gap: 16, marginBottom: 16 }}>
      <PresenceChart/>
      <div className="card">
        <div className="card__hd">
          <div>
            <h3 className="card__title">Anomalies à traiter</h3>
            <p className="card__sub">Validation manuelle requise</p>
          </div>
          <span className="badge b-accent">14</span>
        </div>
        <div className="card__bd" style={{ paddingTop: 4 }}>
          <AnomalyRow name="Sara El Idrissi" role="RH · Siège" kind="Absente sans préavis" when="—" severity="bad" av="av-pink"/>
          <AnomalyRow name="Youssef Benali" role="Sécurité · Hall B" kind="Retard non justifié" when="08:14" severity="warn" av="av-blue"/>
          <AnomalyRow name="Karim Tazi" role="Production" kind="Double pointage" when="08:02 / 08:04" severity="info" av="av-green"/>
        </div>
        <div className="card__ft">
          <span>14 anomalies détectées</span>
          <button className="btn btn--ghost btn--sm">Voir tout →</button>
        </div>
      </div>
    </div>

    <DeviceStrip/>
  </div>
);

window.DashboardScreen = DashboardScreen;
