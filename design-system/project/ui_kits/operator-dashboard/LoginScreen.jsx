/* global React, Icon */

const LoginScreen = () => (
  <div style={{ minHeight: '100vh', display: 'grid', gridTemplateColumns: '1fr 1.1fr', background: 'var(--bg-app)' }}>
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 48 }}>
      <div style={{ width: '100%', maxWidth: 380 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 36 }}>
          <div style={{ width: 38, height: 38, borderRadius: 10, background: 'linear-gradient(135deg, var(--lr-blue-500), var(--lr-blue-700))', position: 'relative', boxShadow: 'var(--shadow-sm)' }}>
            <span style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', color: 'white', fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 20 }}>L</span>
            <span style={{ position: 'absolute', right: 6, top: 6, width: 7, height: 7, borderRadius: 999, background: 'var(--accent)' }}></span>
          </div>
          <div>
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, color: 'var(--fg1)', fontSize: 18, letterSpacing: '-0.01em' }}>LR Time</div>
            <div style={{ fontSize: 11, color: 'var(--fg3)', letterSpacing: '0.12em', textTransform: 'uppercase' }}>PRÉSENCE · ACCÈS · HIK</div>
          </div>
        </div>

        <h1 style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 28, color: 'var(--fg1)', letterSpacing: '-0.02em', margin: '0 0 8px' }}>Bonjour 👋</h1>
        <p style={{ color: 'var(--fg3)', fontSize: 14, margin: '0 0 28px', lineHeight: 1.5 }}>Connectez-vous pour reprendre la supervision de votre site et traiter les anomalies du matin.</p>

        <form onSubmit={(e) => e.preventDefault()} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div>
            <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--fg2)', display: 'block', marginBottom: 6 }}>Adresse e-mail</label>
            <input type="email" defaultValue="fatima.bennani@acme.ma" style={{ width: '100%', height: 42, borderRadius: 8, border: '1px solid var(--border-default)', background: 'var(--bg-surface)', padding: '0 14px', fontSize: 14, color: 'var(--fg1)' }}/>
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 6 }}>
              <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--fg2)' }}>Mot de passe</label>
              <a href="#" style={{ fontSize: 12, color: 'var(--brand)', textDecoration: 'none', fontWeight: 600 }}>Oublié ?</a>
            </div>
            <input type="password" defaultValue="••••••••••••" style={{ width: '100%', height: 42, borderRadius: 8, border: '1px solid var(--border-default)', background: 'var(--bg-surface)', padding: '0 14px', fontSize: 14, color: 'var(--fg1)' }}/>
          </div>
          <label style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--fg2)', userSelect: 'none', marginTop: 4 }}>
            <input type="checkbox" defaultChecked style={{ width: 16, height: 16 }}/>
            Garder ma session active sur ce poste
          </label>
          <button className="btn btn--primary" style={{ height: 44, marginTop: 8, justifyContent: 'center' }}>Se connecter</button>
          <button type="button" className="btn btn--secondary" style={{ height: 42, justifyContent: 'center' }}>
            <Icon id="zap" size={16}/> Continuer en mode démo
          </button>
        </form>

        <div style={{ marginTop: 32, padding: '14px 16px', background: 'var(--brand-softer)', border: '1px solid var(--lr-blue-100)', borderRadius: 10, display: 'flex', alignItems: 'flex-start', gap: 10 }}>
          <Icon id="wifi" size={16} style={{ color: 'var(--brand)', marginTop: 2 }}/>
          <div style={{ fontSize: 12.5, color: 'var(--fg2)', lineHeight: 1.5 }}>
            <strong style={{ color: 'var(--fg1)' }}>Gateway connectée</strong> · tenant <span className="mono" style={{ background: 'white', padding: '1px 6px', borderRadius: 4, fontSize: 11.5 }}>ACME-CASA</span> · prêt à recevoir les pointages.
          </div>
        </div>
      </div>
    </div>

    <div style={{ background: 'linear-gradient(135deg, var(--lr-blue-500) 0%, var(--lr-blue-900) 100%)', position: 'relative', overflow: 'hidden', padding: 64, display: 'flex', flexDirection: 'column', justifyContent: 'space-between', color: 'white' }}>
      <div style={{ position: 'absolute', right: -120, top: -120, width: 400, height: 400, background: 'radial-gradient(closest-side, rgba(255,255,255,.2), transparent 70%)' }}></div>
      <div style={{ position: 'absolute', left: -80, bottom: -80, width: 320, height: 320, background: 'radial-gradient(closest-side, rgba(249,115,22,.18), transparent 70%)' }}></div>

      <div style={{ position: 'relative', zIndex: 2 }}>
        <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.12em', textTransform: 'uppercase', opacity: .7, marginBottom: 14 }}>Édition Janvier 2026</div>
        <h2 style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 36, lineHeight: 1.15, letterSpacing: '-0.02em', margin: 0, maxWidth: '14ch' }}>
          Diagnostiquez votre matinée en moins de 90&nbsp;secondes.
        </h2>
        <p style={{ fontSize: 14.5, lineHeight: 1.6, color: 'rgba(255,255,255,.78)', marginTop: 16, maxWidth: '36ch' }}>
          Présence, retards, anomalies, état des lecteurs Hikvision — tout en une vue, prête pour l'export paie.
        </p>
      </div>

      <div style={{ position: 'relative', zIndex: 2, display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 18 }}>
        {[
          { k: '142', l: 'Présents ce matin' },
          { k: '87%', l: 'Couverture' },
          { k: '14', l: 'Anomalies à traiter' },
        ].map(s => (
          <div key={s.l} style={{ background: 'rgba(255,255,255,.08)', backdropFilter: 'blur(4px)', borderRadius: 12, padding: 16, border: '1px solid rgba(255,255,255,.1)' }}>
            <div className="tnum" style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 26, letterSpacing: '-0.02em' }}>{s.k}</div>
            <div style={{ fontSize: 12, color: 'rgba(255,255,255,.7)', marginTop: 2 }}>{s.l}</div>
          </div>
        ))}
      </div>
    </div>
  </div>
);

window.LoginScreen = LoginScreen;
