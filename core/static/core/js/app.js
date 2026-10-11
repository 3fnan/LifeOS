const buttons = document.querySelectorAll(".complete-task-btn");

console.log("Found buttons:", buttons.length);

function updateGoalProgress() {
    const tasks = document.querySelectorAll(".task-item");
    const completedTasks = document.querySelectorAll(
        ".task-checkbox.completed"
    );

    const totalTasks = tasks.length;
    const completedCount = completedTasks.length;


    let progress = 0;

    if (totalTasks > 0) {
        progress = Math.round((completedCount / totalTasks) * 100);
    }

    const progressValue = document.querySelector(".goal-progress-value");
    const progressFill = document.querySelector(".goal-progress-fill");
    const progressCount = document.querySelector(".goal-progress-count");

    progressValue.textContent = `${progress}%`;
    progressFill.style.width = `${progress}%`;
    progressCount.textContent = `${completedCount} of ${totalTasks} tasks completed`;

    console.log(
        `Progress: ${completedCount}/${totalTasks} = ${progress}%`
    );
}


function updateMilestoneProgress(milestone) {
    const tasks = milestone.querySelectorAll(".task-item");

    const completedTasks = milestone.querySelectorAll(
        ".task-checkbox.completed"
    );

    const totalTasks = tasks.length;
    const completedCount = completedTasks.length;

    let progress = 0;

    if (totalTasks > 0) {
        progress = Math.round(
            (completedCount / totalTasks) * 100
        );
    }

    const progressValue = milestone.querySelector(
        ".milestone-progress-value"
    );

    const progressFill = milestone.querySelector(
        ".milestone-progress-fill"
    );

    const progressCount = milestone.querySelector(
        ".milestone-progress-count"
    );

    progressValue.textContent = `${progress}%`;

    progressFill.style.width = `${progress}%`;

    progressCount.textContent =
        `${completedCount} / ${totalTasks} tasks completed`;

    console.log(
        `Milestone progress: ${completedCount}/${totalTasks} = ${progress}%`
    );
}

buttons.forEach(function (button) {
    button.addEventListener("click", function (event) {
        event.preventDefault();

        const form = button.closest("form");

        const csrfToken = form.querySelector(
            "[name=csrfmiddlewaretoken]"
        ).value;

        button.disabled = true;

        fetch(form.action, {
            method: "POST",
            headers: {
                "X-CSRFToken": csrfToken,
                "X-Requested-With": "XMLHttpRequest"
            }
        })
            .then(function (response) {
                if (!response.ok) {
                    throw new Error("Request failed: " + response.status);
                }
                return response.json();
            })
            .then(function (data) {
                console.log("Django response:", data);

                if (!data.success) {
                    throw new Error(data.error || "Task update failed");
                }

                const taskItem = button.closest(".task-item");
                const milestone = button.closest(".milestone-card");
                const checkbox = taskItem.querySelector(".task-checkbox");
                const taskTitle = taskItem.querySelector(".task-title");

                if (data.status === "completed") {
                    button.textContent = "Undo";
                    checkbox.textContent = "✓";
                    checkbox.classList.add("completed");
                    taskTitle.classList.add("task-completed");
                } else {
                    button.textContent = "Complete";
                    checkbox.textContent = "○";
                    checkbox.classList.remove("completed");
                    taskTitle.classList.remove("task-completed");
                }

                updateGoalProgress();
                updateMilestoneProgress(milestone);
            })
            .catch(function (error) {
                console.error("Task update failed:", error);
                alert("Something went wrong. Please try again.");
            })
            .finally(function () {
                button.disabled = false;
            });
    });
});
