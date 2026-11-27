import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {states, legend, stateBars, statusGroup, statusFill, statusSwatch, statusStroke} from '../../src/knowflow/web/static/charts.js';

const ROOT = new URL('../../src/knowflow/web/static/', import.meta.url);
const read = (name) => readFileSync(new URL(name, ROOT), 'utf8');

test('four levels share names and colors across confirmed and likely states',()=>{
  for(const key of ['mastered','confirmed_mastered','likely_mastered']) {
    assert.equal(states[key].label,'掌握');
    assert.equal(states[key].color,'#d78b51');
  }
  for(const key of ['weak','confirmed_weak','likely_weak']) {
    assert.equal(states[key].label,'薄弱');
    assert.equal(states[key].short,'弱');
    assert.equal(states[key].color,'#238778');
  }
  assert.equal(states.sparse_good.color,'#edb985');
  assert.equal(states.sparse_poor.color,'#81b9a5');
  assert.doesNotMatch(legend(),/表现不稳定|知识点表现不一|待观察/);
  assert.match(legend(true),/知识点表现不一/);
});

test('class bars retain all four separate counts with correct population widths',()=>{
  const html=stateBars([{knowledge_id:'K-01',student_count:10,mastered_count:1,sparse_good_count:2,sparse_poor_count:3,weak_count:4}],()=> '方程');
  for(const [label,count] of [['掌握',1],['较好',2],['较差',3],['薄弱',4]])assert.ok(html.includes(`${label} ${count} 人`));
  for(const width of [10,20,30,40])assert.ok(html.includes(`width:${width}%`));
});

test('status fills are class-driven, not inline pastel colours',()=>{
  assert.equal(statusFill('confirmed_mastered'),'chart-fill-mastered');
  assert.equal(statusFill('mixed_performance'),'chart-fill-mixed');
  assert.equal(statusSwatch('unobserved'),'chart-swatch-unobserved');
  assert.equal(statusStroke('not_applicable'),'chart-stroke-not-applicable');
  assert.equal(statusGroup('likely_weak'),'weak');

  const html=stateBars([{knowledge_id:'K-02',student_count:10,mastered_count:0,sparse_good_count:0,
    sparse_poor_count:0,weak_count:0,mixed_count:0,insufficient_count:1,unobserved_count:2,not_applicable_count:3}],()=> '方程');
  for(const token of ['insufficient-evidence','unobserved','not-applicable'])assert.ok(html.includes(`chart-swatch-${token}`));
  // 旧实现把浅灰写死在 style 里；现在色块只带 class，颜色随主题变量。
  assert.doesNotMatch(html,/background:#(c9d4dc|9fb2c0|e9edf0)/);
  assert.match(legend(),/chart-swatch-unobserved/);
  assert.doesNotMatch(legend(),/style="background:/);

  const theme=read('theme.css');
  const light={'insufficient-evidence':'#c9d4dc','unobserved':'#9fb2c0','not-applicable':'#e9edf0'};
  for(const token of Object.keys(light)){
    assert.match(theme,new RegExp(`--status-fill-${token}: ${light[token]}`));
    assert.match(theme,new RegExp(`\\.chart-swatch-${token} \\{ background:`));
  }
  // 深色用低亮度中性色，避免 >200 的浅块。
  assert.match(theme,/\[data-theme="dark"\] \{\s*--status-fill-mastered/);
  assert.match(theme,/--status-fill-insufficient-evidence: #5f6e77/);
  assert.match(theme,/--status-fill-unobserved: #53626b/);
  assert.match(theme,/--status-fill-not-applicable: #45525a/);
  // 知识地图在 shadow root 里复用同一组变量。
  const mapCss=read('knowledge-map.css');
  for(const token of ['insufficient-evidence','unobserved','not-applicable']){
    assert.match(mapCss,new RegExp(`\\.chart-fill-${token}\\{fill:var\\(--status-fill-${token}`));
  }
  const map=read('knowledge-map.js');
  assert.match(map,/statusFill\(status\|\|'insufficient_evidence'\)/);
  assert.match(map,/dot\.className=statusSwatch\(key\)/);
});

