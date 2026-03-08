window.addEventListener("load", function () {
    const intro = document.getElementById("intro-screen");
    const mainContent = document.getElementById("main-content");
    const toggleBtn = document.getElementById("theme-toggle");

    const savedTheme = localStorage.getItem("famshare_theme");
    if (savedTheme === "dark") {
        document.body.classList.add("dark-mode");
        if (toggleBtn) toggleBtn.textContent = "☀️ Light Mode";
    } else {
        document.body.classList.remove("dark-mode");
        if (toggleBtn) toggleBtn.textContent = "🌙 Dark Mode";
    }

    if (toggleBtn) {
        toggleBtn.addEventListener("click", function () {
            document.body.classList.toggle("dark-mode");
            if (document.body.classList.contains("dark-mode")) {
                localStorage.setItem("famshare_theme", "dark");
                toggleBtn.textContent = "☀️ Light Mode";
            } else {
                localStorage.setItem("famshare_theme", "light");
                toggleBtn.textContent = "🌙 Dark Mode";
            }
        });
    }

    const introShown = localStorage.getItem("famshare_intro_seen");

    if (introShown === "true") {
        if (intro) intro.style.display = "none";
        if (mainContent) {
            mainContent.classList.remove("hidden-content");
            mainContent.classList.add("show-content");
        }
        return;
    }

    localStorage.setItem("famshare_intro_seen", "true");

    setTimeout(() => {
        if (intro) intro.classList.add("intro-slide-up");
    }, 1400);

    setTimeout(() => {
        if (intro) intro.style.display = "none";
        if (mainContent) {
            mainContent.classList.remove("hidden-content");
            mainContent.classList.add("show-content");
        }
    }, 2600);
});