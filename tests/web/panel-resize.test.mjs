// 侧栏面板宽度：pointer 拖动、键盘 ±16、双击回默认、宽度写本机。
// 两个面板（讲解 / 学生差异）共用 panel-resize.mjs，这里用最小 DOM 桩直接跑逻辑，
// 因为失败模式（记住宽度失效、拖动越界、整页选中）在静态检查里看不出来。
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { attachPanelResizer } from '../../src/knowflow/web/static/panel-resize.mjs';

const ROOT = new URL('../../src/knowflow/web/static/', import.meta.url);
const read = (name) => readFileSync(new URL(name, ROOT), 'utf8');

/** 够用就好的元素桩：属性、classList、事件与指针捕获。 */
function makeElement(tag) {
  const listeners = new Map();
  const classes = new Set();
  const attrs = new Map();
  const element = {
    tagName: tag,
    className: '',
    tabIndex: -1,
    title: '',
    isConnected: true,
    style: {
      properties: {},
      setProperty(name, value) {
        this.properties[name] = value;
      },
      removeProperty(name) {
        delete this.properties[name];
      },
    },
    classList: {
      add: (name) => classes.add(name),
      remove: (name) => classes.delete(name),
      contains: (name) => classes.has(name),
    },
    setAttribute: (name, value) => attrs.set(name, String(value)),
    getAttribute: (name) => (attrs.has(name) ? attrs.get(name) : null),
    addEventListener(type, handler) {
      if (!listeners.has(type)) listeners.set(type, []);
      listeners.get(type).push(handler);
    },
    removeEventListener(type, handler) {
      const bucket = listeners.get(type) || [];
      const index = bucket.indexOf(handler);
      if (index >= 0) bucket.splice(index, 1);
    },
    setPointerCapture() {},
    releasePointerCapture() {},
    remove() {
      element.isConnected = false;
    },
    dispatch(type, detail = {}) {
      const event = {
        pointerId: 1,
        pointerType: 'mouse',
        button: 0,
        clientX: 0,
        clientY: 0,
        key: '',
        preventDefault() {},
        ...detail,
      };
      for (const handler of [...(listeners.get(type) || [])]) handler(event);
      return event;
    },
    listenerCount(type) {
      return (listeners.get(type) || []).length;
    },
  };
  return element;
}

/** 装一套文档桩，返回每次 attach 用到的面板与写入记录。 */
function installDom(storage = new Map()) {
  const html = makeElement('html');
  globalThis.document = {
    createElement: (tag) => makeElement(tag),
    documentElement: html,
  };
  globalThis.localStorage = {
    getItem: (key) => (storage.has(key) ? storage.get(key) : null),
    setItem: (key, value) => storage.set(key, String(value)),
    removeItem: (key) => storage.delete(key),
  };
  const resizeListeners = [];
  globalThis.window = {
    innerWidth: 1440,
    addEventListener(type, handler) {
      if (type === 'resize') resizeListeners.push(handler);
    },
    removeEventListener(type, handler) {
      const index = resizeListeners.indexOf(handler);
      if (index >= 0) resizeListeners.splice(index, 1);
    },
  };
  return { html, storage, resizeListeners };
}

/** 一块宽度写回变量的面板。 */
function makePanel(defaultWidth) {
  const panel = {
    rendered: defaultWidth,
    getBoundingClientRect() {
      return { width: this.rendered };
    },
    style: { properties: {} },
  };
  const writes = [];
  panel.setWidth = (width) => {
    writes.push(width);
    panel.rendered = width == null ? defaultWidth : width;
  };
  return { panel, writes };
}

function mount({ defaultWidth = 420, storage = new Map(), min = 360, max = 760 } = {}) {
  const dom = installDom(storage);
  const { panel, writes } = makePanel(defaultWidth);
  const resizer = attachPanelResizer(panel, {
    storageKey: 'kf.panel.test.width',
    label: '调整测试面板宽度',
    min,
    max,
    getWidth: () => panel.rendered,
    setWidth: panel.setWidth,
    maxFor: () => max,
  });
  return { dom, panel, writes, resizer };
}

const KEY = 'kf.panel.test.width';

test('把手声明为竖直 separator，并给出范围与当前宽度', () => {
  const { resizer, dom } = mount();
  assert.equal(resizer.handle.className, 'panel-resizer');
  assert.equal(resizer.handle.getAttribute('role'), 'separator');
  assert.equal(resizer.handle.getAttribute('aria-orientation'), 'vertical');
  assert.equal(resizer.handle.getAttribute('aria-valuemin'), '360');
  assert.equal(resizer.handle.getAttribute('aria-valuemax'), '760');
  assert.equal(resizer.handle.getAttribute('aria-valuenow'), '420');
  assert.equal(resizer.handle.tabIndex, 0);
  assert.equal(dom.html.classList.contains('kf-panel-resizing'), false);
});

test('指针向左拖 200px，面板宽度加 200 并在松手后写进本机', () => {
  const { resizer, panel, dom, writes } = mount();
  resizer.handle.dispatch('pointerdown', { clientX: 700 });
  assert.equal(dom.html.classList.contains('kf-panel-resizing'), true);
  resizer.handle.dispatch('pointermove', { clientX: 600 });
  resizer.handle.dispatch('pointermove', { clientX: 500 });
  assert.equal(panel.rendered, 620);
  resizer.handle.dispatch('pointerup', { clientX: 500 });
  assert.equal(dom.html.classList.contains('kf-panel-resizing'), false);
  assert.equal(dom.storage.get(KEY), '620');
  assert.equal(writes.at(-1), 620);
});

test('拖动被夹在 360–760 之间', () => {
  const { resizer, panel } = mount({ defaultWidth: 740 });
  resizer.handle.dispatch('pointerdown', { clientX: 700 });
  resizer.handle.dispatch('pointermove', { clientX: 100 });
  assert.equal(panel.rendered, 760);
  resizer.handle.dispatch('pointerup', { clientX: 100 });
  resizer.handle.dispatch('pointerdown', { clientX: 100 });
  resizer.handle.dispatch('pointermove', { clientX: 900 });
  assert.equal(panel.rendered, 360);
});

test('刷新后按本机记住的宽度恢复', () => {
  const storage = new Map([[KEY, '655']]);
  const { panel, resizer } = mount({ storage });
  assert.equal(panel.rendered, 655);
  assert.equal(resizer.handle.getAttribute('aria-valuenow'), '655');
});

test('记住的宽度超出新的可用空间时重新夹一次', () => {
  const storage = new Map([[KEY, '900']]);
  const { panel } = mount({ storage });
  assert.equal(panel.rendered, 760);
});

test('左右方向键各走 16px，并向左变宽', () => {
  const { resizer, panel, dom } = mount();
  resizer.handle.dispatch('keydown', { key: 'ArrowLeft' });
  assert.equal(panel.rendered, 436);
  assert.equal(dom.storage.get(KEY), '436');
  resizer.handle.dispatch('keydown', { key: 'ArrowRight' });
  resizer.handle.dispatch('keydown', { key: 'ArrowRight' });
  assert.equal(panel.rendered, 404);
  resizer.handle.dispatch('keydown', { key: 'Enter' });
  assert.equal(panel.rendered, 404);
});

test('双击清掉本机记忆并回到样式表默认宽度', () => {
  const storage = new Map([[KEY, '640']]);
  const { resizer, panel, dom, writes } = mount({ storage });
  assert.equal(panel.rendered, 640);
  resizer.handle.dispatch('dblclick');
  assert.equal(panel.rendered, 420);
  assert.equal(writes.at(-1), null);
  assert.equal(dom.storage.has(KEY), false);
});

test('两个面板复用同一个模块，只是键与范围由调用方给', () => {
  const map = read('knowledge-map.js');
  const app = read('app.js');
  assert.match(map, /from '\.\/panel-resize\.mjs'/);
  assert.match(app, /from '\.\/panel-resize\.mjs'/);
  assert.match(map, /kf\.panel\.map-explain\.width/);
  assert.match(app, /kf\.panel\.map-diff\.width/);
  // 范围 360–760 由调用方传入，模块里不放死值。
  assert.match(map, /min:360,[\s\S]{0,40}max:760/);
  assert.match(app, /min: 360,[\s\S]{0,40}max: 760/);
  // 讲解面板的宽度写回网格变量，画布靠既有 ResizeObserver 重新适配。
  assert.match(map, /--kf-panel-width/);
  assert.match(read('knowledge-map.css'), /min\(var\(--kf-panel-width/);
  assert.match(read('knowledge-map.css'), /#detail\{position:relative/);
  assert.match(read('styles.css'), /#drawer \{[\s\S]{0,80}--kf-panel-width/);
  // 样式在 shadow root 里也要能取到薄荷色。
  assert.match(read('panel-resize.css'), /var\(--panel-accent/);
  assert.match(read('theme.css'), /--panel-accent: #3fa98d/);
});
