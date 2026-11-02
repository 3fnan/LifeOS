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

    /* ---------- Busy state for slow forms ---------- */
    // The clicked button shows a spinner and its data-busy-label, the status
    // line says what's happening and counts seconds, and the form locks so it
    // can't be sent twice.
    document.querySelectorAll("form[data-busy-form]").forEach(function (form) {
        form.addEventListener("submit", function (event) {
            if (form.dataset.busy) { event.preventDefault(); return; }
            form.dataset.busy = "1";
            var button = event.submitter;
            var status = form.querySelector("[data-busy-status]");
            if (button && button.dataset.busyLabel) {
                button.classList.add("is-busy");
                button.textContent = button.dataset.busyLabel;
            }
            if (status && button && button.dataset.busyStatusText) {
                var seconds = 0, text = button.dataset.busyStatusText;
                status.hidden = false;
                status.textContent = text;
                setInterval(function () {
                    seconds += 1;
                    status.textContent = text + " (" + seconds + "s)";
                }, 1000);
            }
            // Disable after the browser has captured the submitter's name/value.
            setTimeout(function () {
                form.querySelectorAll("button, input, select, textarea").forEach(function (el) {
                    if (el.type !== "hidden") el.setAttribute("aria-disabled", "true");
                });
                form.classList.add("is-busy");
            }, 0);
        });
    });

    /* ---------- AI draft editor ---------- */
    // Turns the "# phase / ## step / - task (N min)" outline into editable
    // cards, and writes the outline back into the textarea before submit.
    var outlineField = document.querySelector("[data-outline-field]");
    if (outlineField) {
        var textarea = outlineField.querySelector("textarea");
        var MINUTES = /\s*\((\d+)\s*(?:m|min|mins|minutes)\)\s*$/i;
        var ICON_X = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>';
        var ICON_PLUS = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>';

        var parseOutline = function (text) {
            var phases = [];
            text.split(/\r?\n/).forEach(function (raw) {
                var line = raw.trim();
                if (line.indexOf("## ") === 0) {
                    if (!phases.length) phases.push({ title: "", steps: [] });
                    phases[phases.length - 1].steps.push({ title: line.slice(3).trim(), tasks: [] });
                } else if (line.indexOf("# ") === 0) {
                    phases.push({ title: line.slice(2).trim(), steps: [] });
                } else if (line.indexOf("- ") === 0) {
                    if (!phases.length) phases.push({ title: "", steps: [] });
                    var phase = phases[phases.length - 1];
                    if (!phase.steps.length) phase.steps.push({ title: "", tasks: [] });
                    var title = line.slice(2).trim(), minutes = 30, match = title.match(MINUTES);
                    if (match) { minutes = parseInt(match[1], 10); title = title.slice(0, match.index).trim(); }
                    phase.steps[phase.steps.length - 1].tasks.push({ title: title, minutes: minutes });
                }
            });
            return phases;
        };

        var el = function (tag, className, html) {
            var node = document.createElement(tag);
            if (className) node.className = className;
            if (html) node.innerHTML = html;
            return node;
        };

        var input = function (className, value, label, placeholder) {
            var node = el("input", className);
            node.type = "text";
            node.value = value;
            node.maxLength = 200;
            node.placeholder = placeholder;
            node.setAttribute("aria-label", label);
            return node;
        };

        var removeButton = function (label, target) {
            var button = el("button", "icon-btn icon-btn-danger ed-remove", ICON_X);
            button.type = "button";
            button.setAttribute("aria-label", label);
            button.title = label;
            button.addEventListener("click", function () { target.remove(); update(); });
            return button;
        };

        var addButton = function (label, onClick) {
            var button = el("button", "ed-add", ICON_PLUS + "<span>" + label + "</span>");
            button.type = "button";
            button.addEventListener("click", onClick);
            return button;
        };

        var taskRow = function (task) {
            var row = el("li", "ed-task");
            var minutes = el("input", "ed-min");
            minutes.type = "number";
            minutes.min = "5";
            minutes.step = "5";
            minutes.value = task.minutes;
            minutes.setAttribute("aria-label", "Minutes");
            var unit = el("span", "ed-unit");
            unit.textContent = "min";
            row.append(input("ed-task-title", task.title, "Task", "What will you do?"), minutes, unit, removeButton("Remove task", row));
            return row;
        };

        var stepBlock = function (step) {
            var block = el("div", "ed-step");
            var head = el("div", "ed-step-head");
            head.append(input("ed-step-title", step.title, "Step", "Step name"), removeButton("Remove step", block));
            var tasks = el("ul", "ed-tasks");
            step.tasks.forEach(function (task) { tasks.append(taskRow(task)); });
            block.append(head, tasks, addButton("Add task", function () {
                var row = taskRow({ title: "", minutes: 30 });
                tasks.append(row);
                row.querySelector("input").focus();
                update();
            }));
            return block;
        };

        var phaseCard = function (phase) {
            var card = el("section", "ed-phase");
            var head = el("div", "ed-phase-head");
            head.append(el("span", "ed-phase-num"), input("ed-phase-title", phase.title, "Phase", "Phase name"), removeButton("Remove phase", card));
            var steps = el("div", "ed-steps");
            phase.steps.forEach(function (step) { steps.append(stepBlock(step)); });
            card.append(head, steps, addButton("Add step", function () {
                var block = stepBlock({ title: "", tasks: [{ title: "", minutes: 30 }] });
                steps.append(block);
                block.querySelector("input").focus();
                update();
            }));
            return card;
        };

        var editor = el("div", "ed");
        var summary = el("p", "ed-summary");
        var phasesBox = el("div", "ed-phases");
        parseOutline(textarea.value).forEach(function (phase) { phasesBox.append(phaseCard(phase)); });
        editor.append(summary, phasesBox, addButton("Add phase", function () {
            var card = phaseCard({ title: "", steps: [{ title: "", tasks: [{ title: "", minutes: 30 }] }] });
            phasesBox.append(card);
            card.querySelector("input").focus();
            update();
        }));

        // Rebuild the outline from the cards. Empty task rows are dropped;
        // empty phase/step titles are kept so the server can point them out.
        var serialize = function () {
            var lines = [], counts = { phases: 0, steps: 0, tasks: 0, minutes: 0 };
            phasesBox.querySelectorAll(".ed-phase").forEach(function (card) {
                counts.phases += 1;
                lines.push("# " + card.querySelector(".ed-phase-title").value.trim());
                card.querySelectorAll(".ed-step").forEach(function (block) {
                    counts.steps += 1;
                    lines.push("## " + block.querySelector(".ed-step-title").value.trim());
                    block.querySelectorAll(".ed-task").forEach(function (row) {
                        var title = row.querySelector(".ed-task-title").value.trim();
                        if (!title) return;
                        var minutes = Math.max(1, parseInt(row.querySelector(".ed-min").value, 10) || 30);
                        counts.tasks += 1;
                        counts.minutes += minutes;
                        lines.push("- " + title + " (" + minutes + " min)");
                    });
                });
                lines.push("");
            });
            textarea.value = lines.join("\n");
            return counts;
        };

        var plural = function (n, word) { return n + " " + word + (n === 1 ? "" : "s"); };
        var update = function () {
            var c = serialize();
            var hours = Math.floor(c.minutes / 60), mins = c.minutes % 60;
            var total = (hours ? hours + "h" : "") + (hours && mins ? " " : "") + (mins || !hours ? mins + "m" : "");
            summary.textContent = [plural(c.phases, "phase"), plural(c.steps, "step"), plural(c.tasks, "task"), total + " in total"].join(" · ");
        };

        editor.addEventListener("input", update);
        outlineField.closest("form").addEventListener("submit", serialize);
        outlineField.hidden = true;
        outlineField.after(editor);
        update();
    }
})();
