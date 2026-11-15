// Dependency-free SVG charts; each chart also has readable labels and counts.
export const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;'
} [c]));
export const pct = value => value == null || !Number.isFinite(value) ? '—' : `${value > 0 && value < .01 ? (value * 100).toFixed(1) : Math.round(value * 100)}%`;
export const states = {
  mastered: {
    label: '掌握倾向',
    color: '#238778',
    short: '掌'
  },
  weak: {
    label: '偏弱倾向',
    color: '#d78b51',
    short: '固'
  },
  mixed: {
    label: '表现不稳定',
    color: '#a28bc7',
    short: '波'
  },
  insufficient_evidence: {
    label: '待观察',
    color: '#c9d4dc',
    short: '观'
  },
  not_applicable: {
    label: '本节点不适用',
    color: '#e9edf0',
    short: '—'
  },
  confirmed_mastered: {
    label: '已确认掌握',
    color: '#238778',
    short: '掌'
  },
  likely_mastered: {
    label: '较可能掌握',
    color: '#238778',
    short: '掌'
  },
  confirmed_weak: {
    label: '已确认薄弱',
    color: '#d78b51',
    short: '固'
  },
  likely_weak: {
    label: '较可能偏弱',
    color: '#d78b51',
    short: '固'
  },
  mixed_performance: {
    label: '表现不稳定',
    color: '#a28bc7',
    short: '波'
  }
};
export const categories = ['mastered', 'weak', 'mixed', 'insufficient_evidence', 'not_applicable'];
export const statusGroup = status => ({
  confirmed_mastered: 'mastered',
  likely_mastered: 'mastered',
  confirmed_weak: 'weak',
  likely_weak: 'weak',
  mixed_performance: 'mixed'
} [status] || status);
export const icon = (name, size = 20) => {
  const paths = {
    overview: '<rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/>',
    map: '<circle cx="12" cy="5" r="3"/><circle cx="5" cy="19" r="3"/><circle cx="19" cy="19" r="3"/><path d="m10 8-4 8m8-8 4 8M8 19h8"/>',
    students: '<circle cx="9" cy="8" r="3"/><path d="M3 21v-3a6 6 0 0 1 12 0v3m1-16a3 3 0 0 1 0 6m2 4a5 5 0 0 1 3 5"/>',
    check: '<path d="m5 12 4 4L19 6"/>',
    shield: '<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6Z"/><path d="m8 12 3 3 5-6"/>',
    arrow: '<path d="M4 12h16m-6-6 6 6-6 6"/>',
    book: '<path d="M12 5v16M3 4c4-1 6-1 9 1 3-2 5-2 9-1v15c-4-1-6-1-9 2-3-3-5-3-9-2Z"/>',
    target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
    trend: '<path d="M3 3v18h18M6 16l5-5 4 2 6-7m-5 0h5v5"/>',
    spark: '<path d="m12 3 2.7 6.3L21 12l-6.3 2.7L12 21l-2.7-6.3L3 12l6.3-2.7Z"/>',
    settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.6-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3H9a1.7 1.7 0 0 0 1-1.6V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9V9a1.7 1.7 0 0 0 1.6 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.6 1Z"/>',
    close: '<path d="m6 6 12 12M6 18 18 6"/>',
    search: '<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/>',
    download: '<path d="M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l4 2"/>',
    link: '<path d="m9 15 6-6m-7 3-3 3a4 4 0 0 0 6 6l3-3m2-6 3-3a4 4 0 0 0-6-6l-3 3"/>',
  };
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.overview}</svg>`;
};
export function badge(status) {
  const s = states[status] || {
    label: status,
    color: '#c9d4dc'
  };
  return `<span class="badge status-${esc(status)}"><i style="background:${s.color}"></i>${esc(s.label)}</span>`;
}
export function legend() {
  return `<div class="legend">${categories.map(k=>states[k]).map(s=>`<span><i style="background:${s.color}"></i>${s.label}</span>`).join('')}</div>`;
}
export function donut(items, center, caption) {
  const sum = items.reduce((a, x) => a + x.value, 0),
    radius = 64,
    circumference = 2 * Math.PI * radius;
  let offset = 0;
  const arcs = items.filter(x => x.value > 0).map(x => {
    const length = sum ? x.value / sum * circumference : 0;
    const part = `<circle cx="90" cy="90" r="${radius}" fill="none" stroke="${x.color}" stroke-width="18" stroke-dasharray="${Math.max(0,length-2)} ${circumference}" stroke-dashoffset="${-offset}" transform="rotate(-90 90 90)"><title>${esc(x.label)}：${x.value}（${pct(x.value/sum)}）</title></circle>`;
    offset += length;
    return part;
  }).join('');
  return `<div class="donut-wrap"><svg class="donut" viewBox="0 0 180 180" role="img" aria-label="${esc(items.map(x=>`${x.label} ${x.value}`).join('，'))}"><circle cx="90" cy="90" r="${radius}" fill="none" stroke="#eef2f1" stroke-width="18"/>${arcs}<text class="donut-value" x="90" y="88" text-anchor="middle">${esc(center)}</text><text class="donut-caption" x="90" y="110" text-anchor="middle">${esc(caption)}</text></svg><div class="donut-legend">${items.map(x=>`<div><span><i style="background:${x.color}"></i>${esc(x.label)}</span><strong>${x.value}<small> ${sum?pct(x.value/sum):'—'}</small></strong></div>`).join('')}</div></div>`;
}
export function stateBars(rows, nameFor) {
  const fields = {
    mastered: 'mastered_count',
    weak: 'weak_count',
    mixed: 'mixed_count',
    insufficient_evidence: 'insufficient_count',
    not_applicable: 'not_applicable_count'
  };
  return `<div class="state-bars">${rows.map(r=>`<button class="state-bar-row" data-knowledge="${esc(r.knowledge_id)}"><span class="bar-label"><b>${esc(r.knowledge_id)}</b>${esc(nameFor(r.knowledge_id))}</span><span class="bar-track" aria-label="${esc(Object.entries(fields).map(([k,f])=>states[k].label+' '+r[f]+'人').join('；'))}">${Object.entries(fields).map(([s,f])=>r[f]?`<span class="segment-${s}" style="width:${r[f]/Math.max(1,r.student_count)*100}%;background:${states[s].color}" title="${states[s].label} ${r[f]} 人">${r[f]>=3?r[f]:''}</span>`:'').join('')}</span><span class="bar-end">${r.student_count} 人</span></button>`).join('')}</div>`;
}
export function lineChart(series) {
  const width = 540,
    height = 210,
    left = 40,
    right = 30,
    top = 20,
    bottom = 44;
  const max = Math.max(1, ...series.flatMap(s => s.points.map(p => p.value)));
  const yMax = Math.ceil(max / 100) * 100 || 1,
    n = Math.max(2, ...series.map(s => s.points.length));
  const x = i => left + i * (width - left - right) / (n - 1),
    y = v => height - bottom - v / yMax * (height - top - bottom);
  const grid = [0, 0.5, 1].map(v => `<line x1="${left}" x2="${width-right}" y1="${y(v*yMax)}" y2="${y(v*yMax)}" stroke="#e5ebe9" stroke-dasharray="4 5"/><text x="${left-8}" y="${y(v*yMax)+4}" text-anchor="end" class="axis-label">${Math.round(v*yMax)}</text>`).join('');
  return `<svg class="line-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(series.map(s=>s.label+': '+s.points.map(p=>p.label+' '+p.value+'条').join(', ')).join('; '))}">${grid}${series.map(s=>`<polyline points="${s.points.map((p,i)=>`${x(i)},${y(p.value)}`).join(' ')}" fill="none" stroke="${s.color}" stroke-width="2.5"/>${s.points.map((p,i)=>`<circle cx="${x(i)}" cy="${y(p.value)}" r="5" stroke="white" stroke-width="2" fill="${s.color}"><title>${esc(s.label+' '+p.label)}：${p.value} 条</title></circle><text x="${x(i)}" y="${y(p.value)-11}" text-anchor="middle" fill="${s.color}" class="point-label">${p.value}</text>`).join('')}`).join('')}${(series[0]?.points || []).map((p,i)=>`<text x="${x(i)}" y="${height-20}" text-anchor="middle" class="axis-label">${esc(p.label)}</text><text x="${x(i)}" y="${height-3}" text-anchor="middle" class="axis-label">${esc(p.date||'')}</text>`).join('')}</svg><div class="legend">${series.map(s=>`<span><i style="background:${s.color}"></i>${esc(s.label)}</span>`).join('')}</div>`;
}
export function masteryBars(items, nameFor) {
  return `<div class="mastery-bars">${items.map(k=>`<button class="mastery-row" data-knowledge="${esc(k.knowledge_id)}"><span>${esc(k.knowledge_id)}<b>${esc(nameFor(k.knowledge_id))}</b></span><span class="estimate-track">${k.credible_interval?`<i class="interval" style="left:${k.credible_interval[0]*100}%;width:${(k.credible_interval[1]-k.credible_interval[0])*100}%"></i>`:''}${k.mastery!=null?`<i class="estimate-dot" style="left:${k.mastery*100}%;background:${states[k.status]?.color||'#238778'}"></i>`:''}</span><strong>${pct(k.mastery)}</strong><small>${k.evidence_count} 条</small></button>`).join('')}</div><p class="chart-note">圆点为满分成功概率的模型估计，淡色区间表示不确定性；“—”表示无法估计。估计值不等于考试成绩或能力百分比。</p>`;
}
