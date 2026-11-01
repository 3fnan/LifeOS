/* LifeGrid client enhancements. Everything here is progressive:
   without JavaScript, every form still posts and the page reloads. */
(function () {
    "use strict";

    /* ---------- Theme toggle ---------- */
    function currentTheme() {
        var set = document.documentElement.dataset.theme;
        if (set) return set;
        return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    }

    document.querySelectorAll("[data-theme-toggle]").forEach(function (button) {
        button.addEventListener("click", function () {
            var next = currentTheme() === "dark" ? "light" : "dark";
            document.documentElement.dataset.theme = next;
            try { localStorage.setItem("lifegrid-theme", next); } catch (e) {}
        });
    });

    /* ---------- Toasts ---------- */
    function dismiss(toast) {
        if (!toast || toast.classList.contains("is-leaving")) return;
        toast.classList.add("is-leaving");
        setTimeout(function () { toast.remove(); }, 200);
    }

    document.querySelectorAll(".toast").forEach(function (toast, index) {
        toast.querySelector(".toast-close").addEventListener("click", function () { dismiss(toast); });
        setTimeout(function () { dismiss(toast); }, 4500 + index * 500);
    });

    /* ---------- Progress recalculation ---------- */
    // A [data-progress-scope] counts the [data-task-row] elements inside it
    // and updates its own bar / value / count (not those of nested scopes).
    function ownElements(scope, selector) {
        return Array.prototype.filter.call(scope.querySelectorAll(selector), function (el) {
            return el.closest("[data-progress-scope]") === scope;
        });
    }

    function refreshProgress() {
        document.querySelectorAll("[data-progress-scope]").forEach(function (scope) {
            var total = scope.querySelectorAll("[data-task-row]").length;
            var done = scope.querySelectorAll('[data-task-row][data-status="done"]').length;
            var percent = total ? Math.round((done / total) * 100) : 0;

            ownElements(scope, "[data-progress-bar]").forEach(function (el) { el.style.width = percent + "%"; });
            ownElements(scope, "[data-progress-value]").forEach(function (el) { el.textContent = percent; });
            ownElements(scope, "[data-progress-count]").forEach(function (el) { el.textContent = done + " of " + total; });
        });
    }

    /* ---------- Async task toggle ---------- */
    document.querySelectorAll("form[data-async-toggle]").forEach(function (form) {
        form.addEventListener("submit", function (event) {
            event.preventDefault();
            var button = form.querySelector("button");
            var token = form.querySelector("[name=csrfmiddlewaretoken]").value;
            button.disabled = true;

            fetch(form.action, {
                method: "POST",
                headers: { "X-CSRFToken": token, "X-Requested-With": "XMLHttpRequest" },
                credentials: "same-origin"
            })
                .then(function (response) {
                    if (!response.ok) throw new Error("Request failed: " + response.status);
                    return response.json();
                })
                .then(function (data) {
                    if (!data.success) throw new Error("Task update failed");
                    var row = form.closest("[data-task-row]");
                    var taskId = row ? row.dataset.taskId : null;
                    if (!taskId) return;
                    // The same task can appear several times (e.g. two blocks in a week).
                    document.querySelectorAll('[data-task-row][data-task-id="' + taskId + '"]').forEach(function (el) {
                        el.dataset.status = data.status;
                        var tick = el.querySelector(".tick");
                        if (tick) tick.setAttribute("aria-pressed", data.status === "done" ? "true" : "false");
                    });
                    refreshProgress();
                })
                .catch(function () {
                    // Don't re-post (that could toggle twice); reload to show the true state.
                    window.location.reload();
                })
                .finally(function () {
                    button.disabled = false;
                });
        });
    });
})();
