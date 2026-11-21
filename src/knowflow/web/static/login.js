// Login form: one JSON POST to the local server, then a redirect by role.

const form = document.getElementById('login-form');
const usernameInput = document.getElementById('username');
const passwordInput = document.getElementById('password');
const errorBox = document.getElementById('login-error');
const submit = document.getElementById('login-submit');

function showError(message) {
  errorBox.textContent = message;
}

async function alreadySignedIn() {
  try {
    const response = await fetch('/api/session', {cache: 'no-store'});
    if (!response.ok) return;
    const session = await response.json();
    if (session.authenticated) {
      location.replace(session.role === 'teacher' ? '/teacher' : '/student');
    }
  } catch {
    // Offline backend: stay on the form and let the submit report the problem.
  }
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  showError('');
  const username = usernameInput.value.trim();
  const password = passwordInput.value;
  if (!username || !password) {
    showError('请填写用户名和密码。');
    return;
  }
  submit.disabled = true;
  submit.textContent = '正在登录…';
  try {
    const response = await fetch('/api/login', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-KnowFlow-Login': '1'},
      body: JSON.stringify({username, password})
    });
    let payload = {};
    try {
      payload = await response.json();
    } catch {
      payload = {};
    }
    if (!response.ok) {
      showError(payload.error || '登录失败，请重试。');
      passwordInput.value = '';
      passwordInput.focus();
      return;
    }
    location.replace(payload.redirect || '/');
  } catch {
    showError('无法连接本机后端，请确认启动窗口仍在运行（不要关闭它）。');
  } finally {
    submit.disabled = false;
    submit.textContent = '登录';
  }
});

usernameInput.focus();
alreadySignedIn();
