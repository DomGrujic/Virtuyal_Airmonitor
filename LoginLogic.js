/**
 * \file LoginLogic.js
 * \brief Login and authentication UI logic for Virtuyal.
 *
 * \details Handles login, registration, and two-step password reset flows in a single form.
 * Uses the Flask API endpoints for user validation and password reset.
 *
 * Notes for documentation tools:
 * - Comments use JSDoc/Javadoc style so Doxygen can index them when FILE_PATTERNS includes *.js.
 * - The module wraps logic in an IIFE and attaches event listeners on DOMContentLoaded.
 *
 * @module auth-ui
 */
"use strict";
(function () {
    /**
     * Initialize authentication UI logic after the DOM is ready.
     *
     * Wires up the login/register toggle, forgot/cancel reset links, and the
     * submit handler that calls the backend API.
     *
     * DOM expectations (ids):
     * - auth-form, form-title, toggle-text, toggle-link, confirm-group, username-group
     * - forgot-wrap, forgot-link, confirm-password, username, password-group, password-label
     * - reset-code-group, cancel-reset-wrap, cancel-reset-link, password
     */
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initAuthLogic);
    } else {
        initAuthLogic();
    }

    function initAuthLogic() {
        const form = document.getElementById("auth-form");
        if (!form) return;

        const formTitle = document.getElementById("form-title");
        const toggleText = document.getElementById("toggle-text");
        const toggleLink = document.getElementById("toggle-link");
        const confirmGroup = document.getElementById("confirm-group");
        const usernameGroup = document.getElementById("username-group");
        const forgotWrap = document.getElementById("forgot-wrap");
        const forgotLink = document.getElementById("forgot-link");
        const confirmPasswordInput = document.getElementById("confirm-password");
        const usernameInput = document.getElementById("username");
        const passwordGroup = document.getElementById("password-group");
        const passwordLabel = document.getElementById("password-label");
        const resetCodeGroup = document.getElementById("reset-code-group");
        const cancelResetWrap = document.getElementById("cancel-reset-wrap");
        const cancelResetLink = document.getElementById("cancel-reset-link");
        const passwordInput = document.getElementById("password");
        

        let isLogin = true;
        let isResetPhase1 = false; // only email
        let isResetPhase2 = false; // code + new password

        /**
         * Update the form visibility and requirements based on the current mode.
         *
         * Modes:
         * - Login
         * - Registration
         * - Reset Phase 1 (request reset code)
         * - Reset Phase 2 (enter code + new password)
         */
        function updateMode() {
            if (isResetPhase1) {
                formTitle.textContent = "Passwort zurücksetzen";
                toggleText.classList.add("hidden");
                usernameGroup.classList.add("hidden");
                confirmGroup.classList.add("hidden");
                resetCodeGroup.classList.add("hidden");
                passwordGroup.classList.add("hidden");
                forgotWrap.classList.add("hidden");
                cancelResetWrap.classList.remove("hidden");
                form.querySelector("button").textContent = "Code anfordern";
                passwordInput.required = false;
                confirmPasswordInput.required = false;
                usernameInput.required = false;
            } else if (isResetPhase2) {
                formTitle.textContent = "Neues Passwort setzen";
                toggleText.classList.add("hidden");
                usernameGroup.classList.add("hidden");
                confirmGroup.classList.remove("hidden");
                resetCodeGroup.classList.remove("hidden");
                passwordGroup.classList.remove("hidden");
                passwordLabel.textContent = "Neues Passwort";
                forgotWrap.classList.add("hidden");
                cancelResetWrap.classList.remove("hidden");
                form.querySelector("button").textContent = "Zurücksetzen";
                passwordInput.required = true;
                confirmPasswordInput.required = true;
                usernameInput.required = false;
            } else if (isLogin) {
                formTitle.textContent = "Login";
                confirmGroup.classList.add("hidden");
                usernameGroup.classList.add("hidden");
                form.querySelector("button").textContent = "Anmelden";
                toggleText.innerHTML = 'Noch kein Konto? <a href="#" id="toggle-link">Jetzt registrieren</a>';
                confirmPasswordInput.required = false;
                usernameInput.required = false;
                forgotWrap.classList.remove("hidden");
                resetCodeGroup.classList.add("hidden");
                passwordGroup.classList.remove("hidden");
                passwordLabel.textContent = "Passwort";
                toggleText.classList.remove("hidden");
                cancelResetWrap.classList.add("hidden");
            } else {
                formTitle.textContent = "Registrierung";
                confirmGroup.classList.remove("hidden");
                usernameGroup.classList.remove("hidden");
                form.querySelector("button").textContent = "Registrieren";
                toggleText.innerHTML = 'Schon ein Konto? <a href="#" id="toggle-link">Jetzt anmelden</a>';
                confirmPasswordInput.required = true;
                usernameInput.required = true;
                forgotWrap.classList.add("hidden");
                resetCodeGroup.classList.add("hidden");
                passwordGroup.classList.remove("hidden");
                passwordLabel.textContent = "Passwort";
                toggleText.classList.remove("hidden");
                cancelResetWrap.classList.add("hidden");
            }
            const newToggleLink = document.getElementById("toggle-link");
            if (newToggleLink) newToggleLink.addEventListener("click", handleToggleClick, { once: true });
        }

        /**
         * Toggle between login and registration modes.
         * @param {MouseEvent} e Click event from the mode toggle link.
         */
        function handleToggleClick(e) {
            e.preventDefault();
            isLogin = !isLogin;
            updateMode();
        }

        toggleLink.addEventListener("click", handleToggleClick, { once: true });
        updateMode();

        /**
         * Handle submit for login, registration, and password reset flows.
         *
         * Backend endpoints used:
         * - GET /user/forgotpassword/:email
         * - POST /user/resetPassword
         * - POST /user/validateUser
         * - POST /user/createUser
         *
         * Local storage keys set on successful login:
         * - isLoggedIn ("true"), userEmail, userRole (defaults to "Gast" if not provided)
         *
         * @param {SubmitEvent} e Form submit event
         * @returns {Promise<void>}
         */
        form.addEventListener("submit", async (e) => {
            e.preventDefault();

            const email = document.getElementById("email").value.trim();
            const password = document.getElementById("password").value.trim();
            const username = usernameInput.value.trim();
            const resetCodeInput = document.getElementById("reset-code");
            const resetCode = resetCodeInput ? resetCodeInput.value.trim() : "";
        
            const baseUrl = (window.location && window.location.origin ? window.location.origin : '') + '/api';

            if (isResetPhase1) {
                if (!email) {
                    alert("Bitte E-Mail eingeben");
                    return;
                }
                try {
                    const resp = await fetch(`${baseUrl}/user/forgotpassword/${encodeURIComponent(email)}`, {
                        method: "GET",
                        headers: { "Content-Type": "application/json" }
                    });
                    const data = await resp.json().catch(()=>({}));
                    if (resp.ok) {
                        alert(data.message || "Code gesendet (falls E-Mail existiert). Prüfe dein Postfach.");
                        isResetPhase1 = false;
                        isResetPhase2 = true;
                        passwordInput.value = "";
                        confirmPasswordInput.value = "";
                        updateMode();
                    } else {
                        alert(data.error || data.message || "Fehler beim Anfordern des Codes");
                    }
                } catch (err) {
                    console.error(err);
                    alert("Netzwerkfehler beim Anfordern des Codes");
                }
                return;
            }

            if (isResetPhase2) {
                if (!email || !resetCode || !password) {
                    alert("Bitte E-Mail, Code und neues Passwort eingeben");
                    return;
                }
                if (password !== confirmPasswordInput.value.trim()) {
                    alert("Passwörter stimmen nicht überein");
                    return;
                }
                try {
                    const resp = await fetch(`${baseUrl}/user/resetPassword`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ email, code: resetCode, newPassword: password })
                    });
                    const data = await resp.json().catch(()=>({}));
                    if (resp.ok) {
                        alert(data.message || "Passwort erfolgreich geändert. Bitte einloggen.");
                        isResetPhase2 = false;
                        isLogin = true;
                        passwordInput.value = "";
                        confirmPasswordInput.value = "";
                        resetCodeInput.value = "";
                        updateMode();
                    } else {
                        alert(data.error || data.message || "Fehler beim Zurücksetzen");
                    }
                } catch (err) {
                    console.error(err);
                    alert("Netzwerkfehler beim Zurücksetzen");
                }
                return;
            }

            if (!email || !password || (!isLogin && (!username))) {
                alert("Bitte alle Felder ausfüllen!");
                return;
            }

            if (isLogin) {
                // LOGIN REQUEST
                try {
                    const response = await fetch(`${baseUrl}/user/validateUser`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ 
                            email: email,
                            password: password
                        })
                    });

                    const data = await response.json();
                    if (response.ok && data.success) {
                        localStorage.setItem("isLoggedIn", "true");
                        localStorage.setItem("userEmail", email);
                        // Always clear any previous role to avoid stale privileges
                        localStorage.removeItem("userRole");
                        // optional: Username/Rolle falls vom Backend geliefert
                        if (data.user) {
                            if (data.user.username) localStorage.setItem("username", data.user.username);
                            if (data.user.role) localStorage.setItem("userRole", data.user.role);
                        }
                        // Fallback: Wenn Backend keine Rolle liefert → immer Gast (Server bestimmt Admin explizit)
                        if (!localStorage.getItem("userRole")) {
                            localStorage.setItem('userRole', 'Gast');
                        }
                        window.location.href = "index.html";
                    } else {
                        alert(data.message || "Login fehlgeschlagen!");
                    }
                } catch (err) {
                    console.error("Login-Fehler:", err);
                    alert("Fehler beim Login. Bitte Server prüfen.");
                }

            } else {

                // REGISTRIERUNG REQUEST
                const confirmPassword = confirmPasswordInput.value.trim();
                if (password !== confirmPassword) {
                    alert("Passwörter stimmen nicht überein!");
                    return;
                }
 
                try {
                    const response = await fetch(`${baseUrl}/user/createUser`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            email: email, 
                            username: username,
                            password: password,
                        
                        })
                    });

                    const data = await response.json();
                    if (response.ok && data.message) {
                        alert("Registrierung erfolgreich! Bitte einloggen.");
                        isLogin = true;
                        confirmPasswordInput.value = "";
                        usernameInput.value = "";
                        updateMode();
                    } else {
                        alert(data.error || data.message || "Registrierung fehlgeschlagen!");
                    }
                } catch (err) {
                    console.error("Registrierungs-Fehler:", err);
                    alert("Fehler bei der Registrierung. Bitte Server prüfen.");
                }

            }
        });

        // Passwort vergessen Trigger
        /**
         * Enter reset phase 1 (request code) when clicking the "forgot password" link.
         */
        if (forgotLink) {
            forgotLink.addEventListener("click", (e) => {
                e.preventDefault();
                isLogin = false;
                isResetPhase1 = true;
                isResetPhase2 = false;
                passwordInput.value = "";
                confirmPasswordInput.value = "";
                updateMode();
            });
        }

        /**
         * Cancel any reset phase and return to login mode.
         */
        if (cancelResetLink) {
            cancelResetLink.addEventListener("click", (e) => {
                e.preventDefault();
                isResetPhase1 = false;
                isResetPhase2 = false;
                isLogin = true;
                passwordInput.value = "";
                confirmPasswordInput.value = "";
                const rc = document.getElementById("reset-code");
                if (rc) rc.value = "";
                updateMode();
            });
        }
    }
})();
