// Presentation-only statistics. Null observations never become zero scores.
export function describe(values) {
  const sorted = values.filter(Number.isFinite).sort((a, b) => a - b);
  const n = sorted.length;
  return {
    count: n,
    mean: n ? sorted.reduce((sum, value) => sum + value, 0) / n : null,
    median: n ? (sorted[Math.floor((n - 1) / 2)] + sorted[Math.floor(n / 2)]) / 2 : null,
    min: n ? sorted[0] : null,
    max: n ? sorted[n - 1] : null,
  };
}

export function distribution(values) {
  const bins = Array.from({length: 5}, (_, i) => ({
    low: i / 5, high: (i + 1) / 5, value: 0,
    label: `${i * 20}–${(i + 1) * 20}%`,
    interval: `${i * 20}% ≤ 比例 ${i === 4 ? '≤' : '<'} ${(i + 1) * 20}%`,
  }));
  let missing = 0;
  for (const value of values) {
    if (!Number.isFinite(value) || value < 0 || value > 1) missing++;
    else bins[Math.min(4, Math.floor(value * 5))].value++;
  }
  return {bins, missing, count: values.length - missing};
}

export function aggregateRecords(records) {
  const assigned = records.filter(r => r.assigned);
  const attempted = assigned.filter(r => r.attempted);
  const graded = attempted.filter(r => Number.isFinite(r.score) && r.max_score > 0);
  const possible = graded.reduce((sum, r) => sum + r.max_score, 0);
  const earned = graded.reduce((sum, r) => sum + r.score, 0);
  return {
    assigned: assigned.length, attempted: attempted.length, graded: graded.length,
    full: graded.filter(r => r.score === r.max_score).length,
    partial: graded.filter(r => r.score > 0 && r.score < r.max_score).length,
    zero: graded.filter(r => r.score === 0).length,
    pending: attempted.length - graded.length, unattempted: assigned.length - attempted.length,
    earned, possible, rate: possible ? earned / possible : null,
    completion: assigned.length ? attempted.length / assigned.length : null,
    observedStudents: new Set(graded.map(r => r.student_id)).size,
  };
}

export function topics(snapshot, nodeId, studentIds) {
  const ids = new Set(studentIds);
  // Each record belongs to exactly one material objective. Q-matrix links must
  // not duplicate a score when a question measures more than one knowledge point.
  const objectives = new Map(snapshot.knowledge_base.materials.map(m => [m.material_id, m.objective_id]));
  const records = snapshot.records.filter(r => r.node_id === nodeId && ids.has(r.student_id));
  return snapshot.knowledge_base.objectives.map(o => ({
    ...o, ...aggregateRecords(records.filter(r => objectives.get(r.material_id) === o.objective_id)),
  }));
}

// Label centers share a column. Spread close values without moving their data
// points; return positions in original order so connectors remain accurate.
export function placeLabels(desired, top, bottom, minGap = 24) {
  if (!desired.length) return [];
  const gap = Math.min(minGap, (bottom - top) / Math.max(1, desired.length - 1));
  const sorted = desired.map((y, i) => ({y: Math.max(top, Math.min(bottom, y)), i})).sort((a, b) => a.y - b.y || a.i - b.i);
  for (let i = 1; i < sorted.length; i++) sorted[i].y = Math.max(sorted[i].y, sorted[i - 1].y + gap);
  sorted[sorted.length - 1].y = Math.min(bottom, sorted[sorted.length - 1].y);
  for (let i = sorted.length - 2; i >= 0; i--) sorted[i].y = Math.min(sorted[i].y, sorted[i + 1].y - gap);
  const result = [];
  sorted.forEach(({y, i}) => { result[i] = y; });
  return result;
}
