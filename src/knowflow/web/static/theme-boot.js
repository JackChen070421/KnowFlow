// Runs synchronously in <head>: restore the saved palette before first paint,
// so switching pages never flashes the default light theme.
(function () {
  var THEMES = ['light', 'dark', 'eye'];
  var stored = null;
  try {
    stored = localStorage.getItem('knowflow.theme');
  } catch (error) {
    stored = null;
  }
  var fromUrl = new URLSearchParams(location.search).get('theme');
  var theme = THEMES.indexOf(fromUrl) >= 0 ? fromUrl : stored;
  if (THEMES.indexOf(theme) < 0) theme = 'light';
  document.documentElement.setAttribute('data-theme', theme);
})();

// Motion default: ON for everyone.
//
// 原实现把「系统是否允许动画」当成总开关：Windows 关闭「动画效果」时，浏览器上报
// `prefers-reduced-motion: reduce`，于是 styles.css / motion.css / 知识地图三处各自
// 关掉动画，整页变成静态——在演示机上这等于功能缺失，而且界面上没有任何入口能打开。
//
// 现在的口径：默认播放动画，不再由系统设置决定；只在用户显式关闭时安静下来。
//   `?motion=0` 或 设置 → 显示 →「关闭」→ 记住本机不再播放（localStorage 存 off）
//   `?motion=1` 或 设置 → 「始终开启」→ 恢复播放
// 标记挂在 <html> 上，样式表首屏即可见；kfMotionAllowed() 是脚本侧唯一的判定入口，
// 调用方不再各自查询媒体查询。
(function () {
  var KEY = 'knowflow.motion';
  var ON = /^(1|on|true|yes|force)$/i;
  var OFF = /^(0|off|false|no|auto|system)$/i;
  var flag = null;
  var muted = false;
  try {
    flag = new URLSearchParams(location.search).get('motion');
  } catch (error) {
    flag = null;
  }
  try {
    if (flag !== null) {
      if (ON.test(flag)) localStorage.removeItem(KEY);
      else if (OFF.test(flag)) localStorage.setItem(KEY, 'off');
    }
    muted = localStorage.getItem(KEY) === 'off';
  } catch (error) {
    muted = false;
  }
  // Storage can be unavailable (private mode); the explicit flag still wins.
  if (flag !== null && OFF.test(flag)) muted = true;
  else if (flag !== null && ON.test(flag)) muted = false;
  if (!muted) document.documentElement.classList.add('kf-force-motion');
  window.kfMotionAllowed = function () {
    return !muted;
  };
  if (muted && window.console) {
    console.info('[KnowFlow] 本机已关闭动效（访问 ?motion=1 或设置里「始终开启」可恢复）');
  }
})();
