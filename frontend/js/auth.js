document.addEventListener("DOMContentLoaded", () => {
  // If already logged in, skip straight to the dashboard.
  if (API.token()) {
    location.href = "home.html";
    return;
  }

  const loginView = document.getElementById("login-view");
  const registerView = document.getElementById("register-view");

  document.getElementById("show-register").addEventListener("click", (e) => {
    e.preventDefault();
    loginView.style.display = "none";
    registerView.style.display = "block";
  });
  document.getElementById("show-login").addEventListener("click", (e) => {
    e.preventDefault();
    registerView.style.display = "none";
    loginView.style.display = "block";
  });

  document.getElementById("login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const errEl = document.getElementById("login-error");
    errEl.classList.remove("show");
    const btn = document.getElementById("login-btn");
    btn.disabled = true; btn.textContent = "Signing in…";

    try {
      const email = document.getElementById("login-email").value.trim();
      const password = document.getElementById("login-password").value;
      const data = await API.login(email, password);
      API.setSession(data.access_token, data.user);
      location.href = "home.html";
    } catch (err) {
      errEl.textContent = err.message;
      errEl.classList.add("show");
    } finally {
      btn.disabled = false; btn.textContent = "Sign in";
    }
  });

  document.getElementById("register-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const errEl = document.getElementById("register-error");
    errEl.classList.remove("show");
    const btn = document.getElementById("register-btn");
    btn.disabled = true; btn.textContent = "Creating account…";

    try {
      const payload = {
        full_name: document.getElementById("reg-name").value.trim(),
        company: document.getElementById("reg-company").value.trim(),
        email: document.getElementById("reg-email").value.trim(),
        password: document.getElementById("reg-password").value,
      };
      const data = await API.register(payload);
      API.setSession(data.access_token, data.user);
      location.href = "home.html";
    } catch (err) {
      errEl.textContent = err.message;
      errEl.classList.add("show");
    } finally {
      btn.disabled = false; btn.textContent = "Create account";
    }
  });
});
