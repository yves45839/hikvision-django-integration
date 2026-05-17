/* global React, Icon */

const KpiCard = ({ label, icon, value, unit, denom, delta, deltaDir = 'up', sub, tone = 'brand' }) => {
  const toneClass = { brand: '', accent: 'kpi--accent', ok: 'kpi--ok', warn: 'kpi--warn' }[tone];
  return (
    <div className={`kpi ${toneClass}`}>
      <div className="kpi__hd">
        <span className="kpi__label">{label}</span>
        <div className="kpi__icon"><Icon id={icon} size={18} /></div>
      </div>
      <div className="kpi__value tnum">
        {value}
        {(unit || denom) && <small>{unit ? ` ${unit}` : ''}{denom ? ` / ${denom}` : ''}</small>}
      </div>
      <div className="kpi__row">
        {delta != null && (
          <span className={`kpi__delta${deltaDir === 'down' ? ' is-down' : ''}`}>
            {deltaDir === 'down' ? '▼' : '▲'} {delta}
          </span>
        )}
        {sub && <span className="kpi__sub">{sub}</span>}
      </div>
    </div>
  );
};

window.KpiCard = KpiCard;
