// 可拖拽侧栏面板：左边缘 8px 把手 + Pointer Events + 本机记忆宽度。
//
// 课程知识地图的「讲解」面板与「全部班级 · 学生差异」抽屉共用这一份逻辑，
// 差别只在宽度写回哪里，所以通过 getWidth / setWidth 两个钩子注入，
// 不在调用处各写一遍 pointerdown/move/up。
//
// 约定：
//   · 拖动条 role="separator" aria-orientation="vertical"，左右方向键 ±16px，双击恢复默认；
//   · 松手把宽度写进 localStorage（键由调用方给），刷新后恢复；
//   · 恢复默认 = 清掉本机记忆并移除内联宽度，回到样式表里的原默认值。
const STEP = 16;

function readSaved(storageKey) {
  try {
    const value = Number(localStorage.getItem(storageKey));
    return Number.isFinite(value) && value > 0 ? value : null;
  } catch {
    return null;
  }
}

function writeSaved(storageKey, width) {
  try {
    if (width == null) localStorage.removeItem(storageKey);
    else localStorage.setItem(storageKey, String(Math.round(width)));
  } catch {
    // 隐私模式下写不进去：本次拖动仍然生效，只是不记忆。
  }
}

/**
 * @param {HTMLElement} panel 宽度受控的面板
 * @param {object} options
 * @param {string} options.storageKey localStorage 键
 * @param {string} [options.label] 拖动条的无障碍名称
 * @param {number} [options.min] 最小宽度
 * @param {number} [options.max] 最大宽度
 * @param {() => number} [options.getWidth] 读当前渲染宽度
 * @param {(width: number|null) => void} [options.setWidth] 写宽度，null 表示恢复默认
 * @param {() => number} [options.maxFor] 计算当前允许的最大宽度（受容器/视口限制）
 * @param {(width: number|null, detail: {immediate: boolean}) => void} [options.onResize]
 *   宽度变化回调。拖动过程中 immediate=false（由调用方自行节流），
 *   松手 / 键盘 / 双击 / 窗口缩放 / 恢复本机宽度时 immediate=true。
 * @returns {{dispose: () => void, reset: () => void, handle: HTMLElement}}
 */
export function attachPanelResizer(panel, options) {
  const {
    storageKey,
    label = '调整面板宽度',
    min = 360,
    max = 760,
    getWidth = () => panel.getBoundingClientRect().width,
    setWidth = width => {
      if (width == null) panel.style.removeProperty('--kf-panel-width');
      else panel.style.setProperty('--kf-panel-width', `${width}px`);
    },
    maxFor = () => max,
    onResize = null,
  } = options;

  const clamp = value => Math.max(min, Math.min(maxFor(), value));

  const handle = document.createElement('div');
  handle.className = 'panel-resizer';
  handle.tabIndex = 0;
  handle.setAttribute('role', 'separator');
  handle.setAttribute('aria-orientation', 'vertical');
  handle.setAttribute('aria-label', label);
  handle.setAttribute('aria-valuemin', String(min));
  handle.setAttribute('aria-valuemax', String(max));
  handle.title = '拖动调整宽度 · 双击恢复默认';

  let drag = null;

  const syncAria = () => {
    const width = Math.round(getWidth());
    handle.setAttribute('aria-valuenow', String(width));
  };

  const apply = (width, immediate = false) => {
    const next = width == null ? null : clamp(width);
    setWidth(next);
    syncAria();
    onResize?.(next, { immediate });
    return next;
  };

  const commit = width => {
    apply(width, true);
    writeSaved(storageKey, width == null ? null : clamp(width));
  };

  const reset = () => {
    writeSaved(storageKey, null);
    apply(null, true);
  };

  const onPointerDown = event => {
    if (event.pointerType === 'mouse' && event.button !== 0) return;
    event.preventDefault();
    drag = { id: event.pointerId, x: event.clientX, width: getWidth() };
    handle.classList.add('is-dragging');
    document.documentElement.classList.add('kf-panel-resizing');
    try {
      handle.setPointerCapture(event.pointerId);
    } catch {
      // 指针已经被系统收回时忽略，后续 move 仍按坐标算。
    }
  };

  const onPointerMove = event => {
    if (!drag || drag.id !== event.pointerId) return;
    // 面板在右侧：指针往左（clientX 变小）面板变宽。
    apply(drag.width + (drag.x - event.clientX));
  };

  const finish = event => {
    if (!drag || drag.id !== event.pointerId) return;
    drag = null;
    handle.classList.remove('is-dragging');
    document.documentElement.classList.remove('kf-panel-resizing');
    try {
      handle.releasePointerCapture(event.pointerId);
    } catch {
      // 已经释放过了。
    }
    writeSaved(storageKey, clamp(getWidth()));
    // 松手时宽度已经由最后一次 move 写好了，这里再补一次“立即适配”信号。
    onResize?.(clamp(getWidth()), { immediate: true });
  };

  const onKeyDown = event => {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
    event.preventDefault();
    // 左方向键把左边缘往左推 = 变宽，右方向键相反。
    const current = getWidth();
    commit(current + (event.key === 'ArrowLeft' ? STEP : -STEP));
  };

  const onDoubleClick = event => {
    event.preventDefault();
    reset();
  };

  handle.addEventListener('pointerdown', onPointerDown);
  handle.addEventListener('pointermove', onPointerMove);
  handle.addEventListener('pointerup', finish);
  handle.addEventListener('pointercancel', finish);
  handle.addEventListener('lostpointercapture', finish);
  handle.addEventListener('keydown', onKeyDown);
  handle.addEventListener('dblclick', onDoubleClick);

  const saved = readSaved(storageKey);
  if (saved != null) apply(saved, true);
  else syncAria();

  // 面板在挂载时可能还没显示（宽度 0），打开那一刻才第一次有真实宽度；
  // 用 ResizeObserver 把 aria-valuenow 与真实宽度对齐，也顺带覆盖窗口缩放。
  let observer = null;
  if (typeof ResizeObserver === 'function') {
    observer = new ResizeObserver(() => {
      if (getWidth() > 0) syncAria();
    });
    observer.observe(panel);
  }

  // 视口一变，之前记住的宽度可能超过新的可用空间，重新夹一次。
  const reapply = () => {
    const stored = readSaved(storageKey);
    if (stored != null) apply(stored, true);
    else syncAria();
  };
  window.addEventListener('resize', reapply);

  return {
    handle,
    reset,
    reapply,
    dispose() {
      observer?.disconnect();
      window.removeEventListener('resize', reapply);
      handle.removeEventListener('pointerdown', onPointerDown);
      handle.removeEventListener('pointermove', onPointerMove);
      handle.removeEventListener('pointerup', finish);
      handle.removeEventListener('pointercancel', finish);
      handle.removeEventListener('lostpointercapture', finish);
      handle.removeEventListener('keydown', onKeyDown);
      handle.removeEventListener('dblclick', onDoubleClick);
      document.documentElement.classList.remove('kf-panel-resizing');
      handle.remove();
    },
  };
}

/**
 * 面板内宽度的上限：始终给主内容区留出可读空间，避免出现横向滚动条。
 * 两个面板都用同一个公式，只是「主内容至少留多少」不同。
 */
export function fitWithin(container, keep, hardMax) {
  const available = container ? container.clientWidth - keep : hardMax;
  return Math.max(360, Math.min(hardMax, available));
}
