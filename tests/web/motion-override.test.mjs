// Motion policy: animation is ON for everyone by default; it stops only when the
// reader turns it off on that machine. These tests pin both halves, because the
// failure mode (a demo looking static) is silent.
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';

const ROOT = new URL('../../src/knowflow/web/static/', import.meta.url);
const boot = readFileSync(new URL('theme-boot.js', ROOT), 'utf8');
const read = (name) => readFileSync(new URL(name, ROOT), 'utf8');

/** Run theme-boot.js against a stub page that reports `reduce` for the OS setting. */
function runBoot({ search = '', reduce = true, stored = null, storageFails = false } = {}) {
  const classes = new Set();
  const store = new Map(stored === null ? [] : [['knowflow.motion', stored]]);
  const html = {
    setAttribute() {},
    classList: {
      add: (name) => classes.add(name),
      contains: (name) => classes.has(name),
    },
  };
  const window = {
    matchMedia: (query) => ({ matches: reduce && query.includes('reduce') }),
    console: { info() {} },
  };
  const localStorage = storageFails
    ? {
        getItem() { throw new Error('blocked'); },
        setItem() { throw new Error('blocked'); },
        removeItem() { throw new Error('blocked'); },
      }
    : {
        getItem: (key) => (store.has(key) ? store.get(key) : null),
        setItem: (key, value) => store.set(key, String(value)),
        removeItem: (key) => store.delete(key),
      };
  const context = {
    window,
    document: { documentElement: html },
    location: { search },
    URLSearchParams,
    localStorage,
    console: { info() {} },
  };
  vm.createContext(context);
  vm.runInContext(boot, context);
  return { classes, store, window };
}

test('animation plays by default even when the OS asks for reduced motion', () => {
  const { classes, window } = runBoot({ reduce: true });
  assert.equal(classes.has('kf-force-motion'), true);
  assert.equal(window.kfMotionAllowed(), true);
});

test('?motion=0 turns animation off for this machine and remembers it', () => {
  const { classes, store, window } = runBoot({ search: '?motion=0', reduce: true });
  assert.equal(classes.has('kf-force-motion'), false);
  assert.equal(store.get('knowflow.motion'), 'off');
  assert.equal(window.kfMotionAllowed(), false);
});

test('the off choice survives navigation without the query string', () => {
  const { classes, window } = runBoot({ search: '', reduce: true, stored: 'off' });
  assert.equal(classes.has('kf-force-motion'), false);
  assert.equal(window.kfMotionAllowed(), false);
});

test('?motion=1 restores the default after an opt-out', () => {
  const { classes, store, window } = runBoot({ search: '?motion=1', reduce: true, stored: 'off' });
  assert.equal(classes.has('kf-force-motion'), true);
  assert.equal(store.has('knowflow.motion'), false);
  assert.equal(window.kfMotionAllowed(), true);
});

test('blocked storage still defaults to playing animation', () => {
  const { classes, window } = runBoot({ reduce: true, storageFails: true });
  assert.equal(classes.has('kf-force-motion'), true);
  assert.equal(window.kfMotionAllowed(), true);
});

test('opted-out storage still wins when storage is blocked', () => {
  const { window } = runBoot({ search: '?motion=0', reduce: true, storageFails: true });
  assert.equal(window.kfMotionAllowed(), false);
});

test('the stylesheets skip their reduced-motion guard when animation is on', () => {
  const styles = read('styles.css');
  assert.match(styles, /html:not\(\.kf-force-motion\) \*/);
  const theme = read('theme.css');
  assert.match(theme, /html:not\(\.kf-force-motion\)::view-transition-old\(root\)/);
  // The map stylesheet lives in a shadow root, where `html` cannot be selected.
  const map = read('knowledge-map.css');
  assert.match(map, /:host\(:not\(\.force-motion\)\)/);
});

test('motion.css is not gated by a media query the app cannot override', () => {
  const motion = read('motion.css');
  assert.doesNotMatch(motion, /@media \(prefers-reduced-motion: no-preference\)/);
  // The sign-in page does not load styles.css, so it carries its own guard.
  assert.match(read('login.css'), /html:not\(\.kf-force-motion\) \*/);
});

test('drag linkage is not gated on the ambient-motion switch', () => {
  // 拖拽联动是直接操作反馈，必须无条件生效（否则系统关动画时拖模块没有联动）。
  const map = read('knowledge-map.js');
  const wake = map.slice(map.indexOf('function wake()'), map.indexOf('function wake()') + 600);
  assert.doesNotMatch(wake, /!dynamic/);
});
