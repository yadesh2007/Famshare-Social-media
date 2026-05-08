window.addEventListener("load", function () {
    const intro = document.getElementById("intro-screen");
    const mainContent = document.getElementById("main-content");
    const toggleBtn = document.getElementById("theme-toggle");
    const sidebarToggle = document.getElementById("sidebar-toggle");
    const sidebarOverlay = document.getElementById("sidebar-overlay");

    function setTheme(theme) {
        const isDark = theme === "dark";
        document.body.classList.toggle("dark-mode", isDark);
        if (toggleBtn) {
            toggleBtn.textContent = isDark ? "Light Mode" : "Dark Mode";
        }
    }

    setTheme(localStorage.getItem("famshare_theme") || "light");

    if (toggleBtn) {
        toggleBtn.addEventListener("click", function () {
            const nextTheme = document.body.classList.contains("dark-mode") ? "light" : "dark";
            localStorage.setItem("famshare_theme", nextTheme);
            setTheme(nextTheme);
        });
    }

    function setSidebarOpen(isOpen) {
        document.body.classList.toggle("sidebar-closed", !isOpen);
        if (sidebarToggle) {
            sidebarToggle.textContent = isOpen ? "\u2039" : "\u203a";
            sidebarToggle.setAttribute("aria-expanded", String(isOpen));
            sidebarToggle.setAttribute("aria-label", isOpen ? "Close menu" : "Open menu");
        }
        localStorage.setItem("famshare_sidebar_open", String(isOpen));
    }

    if (sidebarToggle) {
        const savedSidebarState = localStorage.getItem("famshare_sidebar_open");
        const startsOpen = savedSidebarState === null
            ? !window.matchMedia("(max-width: 900px)").matches
            : savedSidebarState !== "false";
        setSidebarOpen(startsOpen);

        sidebarToggle.addEventListener("click", function () {
            setSidebarOpen(document.body.classList.contains("sidebar-closed"));
        });
    }

    if (sidebarOverlay) {
        sidebarOverlay.addEventListener("click", function () {
            setSidebarOpen(false);
        });
    }

    const profilePhotoInput = document.getElementById("profile-photo-input");
    const profilePhotoPreview = document.getElementById("profile-photo-preview");
    const removeProfilePhotoBtn = document.getElementById("remove-profile-photo");
    const removeProfilePhotoInput = document.getElementById("remove-profile-photo-input");

    if (profilePhotoInput && profilePhotoPreview && removeProfilePhotoInput) {
        profilePhotoInput.addEventListener("change", function () {
            const file = profilePhotoInput.files && profilePhotoInput.files[0];
            removeProfilePhotoInput.value = "0";

            if (file) {
                profilePhotoPreview.src = URL.createObjectURL(file);
            }
        });
    }

    if (removeProfilePhotoBtn && profilePhotoPreview && removeProfilePhotoInput && profilePhotoInput) {
        removeProfilePhotoBtn.addEventListener("click", function () {
            profilePhotoInput.value = "";
            removeProfilePhotoInput.value = "1";
            profilePhotoPreview.src = profilePhotoPreview.dataset.defaultSrc;
        });
    }

    const sosModal = document.getElementById("sos-modal");
    const sosForm = document.getElementById("sos-form");
    const emergencyToast = document.getElementById("emergency-toast");
    const openSosButtons = document.querySelectorAll("#open-sos-modal, [data-open-sos]");
    const closeSosBtn = document.getElementById("close-sos-modal");
    const useCurrentLocationBtn = document.getElementById("use-current-location");
    const sosLocationStatus = document.getElementById("sos-location-status");
    const currentUserId = Number(document.body.dataset.currentUserId || 0);
    const appSocket = window.io ? io({
        transports: ["websocket", "polling"],
        reconnection: true
    }) : null;

    function setSosLocationStatus(message) {
        if (sosLocationStatus) {
            sosLocationStatus.textContent = message;
        }
    }

    function getLocationErrorMessage(error) {
        if (!window.isSecureContext) {
            return "Location needs HTTPS or localhost. Open the app on 127.0.0.1/localhost instead of a network IP, or enable HTTPS.";
        }
        if (!error) {
            return "Could not access current location. Please check browser location settings.";
        }
        if (error.code === error.PERMISSION_DENIED) {
            return "Location permission is blocked. Allow location for this site in the browser, then try again.";
        }
        if (error.code === error.POSITION_UNAVAILABLE) {
            return "Your device could not provide a location right now. Turn on GPS/location services and try again.";
        }
        if (error.code === error.TIMEOUT) {
            return "Location request timed out. Try again near a window or with GPS/location services enabled.";
        }
        return "Could not access current location. Please type the location manually.";
    }

    async function updateSosLocation(showStatus) {
        if (!navigator.geolocation || !sosForm) {
            if (showStatus) {
                setSosLocationStatus("Location access is not available in this browser.");
            }
            return false;
        }

        if (!window.isSecureContext) {
            if (showStatus) {
                setSosLocationStatus(getLocationErrorMessage());
            }
            return false;
        }

        if (showStatus) {
            setSosLocationStatus("Fetching current location...");
        }

        return new Promise(function (resolve) {
            navigator.geolocation.getCurrentPosition(function (position) {
                const latitude = position.coords.latitude;
                const longitude = position.coords.longitude;
                sosForm.elements.latitude.value = latitude;
                sosForm.elements.longitude.value = longitude;
                if (showStatus) {
                    setSosLocationStatus("Current location captured. Address will be added when SOS is sent.");
                }
                if (appSocket) {
                    appSocket.emit("update_user_location", {
                        latitude: latitude,
                        longitude: longitude
                    });
                }
                resolve(true);
            }, function (error) {
                if (showStatus) {
                    setSosLocationStatus(getLocationErrorMessage(error));
                }
                resolve(false);
            }, {
                enableHighAccuracy: true,
                timeout: 15000,
                maximumAge: 0
            });
        });
    }

    function openSosModal() {
        if (sosModal) {
            sosModal.classList.add("show-sos-modal");
            sosModal.setAttribute("aria-hidden", "false");
        }
        updateSosLocation(true);
    }

    function closeSosModal() {
        if (sosModal) {
            sosModal.classList.remove("show-sos-modal");
            sosModal.setAttribute("aria-hidden", "true");
        }
    }

    function playEmergencySound() {
        try {
            const audioContext = new (window.AudioContext || window.webkitAudioContext)();
            const oscillator = audioContext.createOscillator();
            const gain = audioContext.createGain();
            oscillator.type = "sine";
            oscillator.frequency.value = 880;
            gain.gain.value = 0.08;
            oscillator.connect(gain);
            gain.connect(audioContext.destination);
            oscillator.start();
            setTimeout(function () {
                oscillator.stop();
                audioContext.close();
            }, 450);
        } catch (error) {
            return;
        }
    }

    function showEmergencyToast(alert) {
        if (!emergencyToast) {
            return;
        }
        if (currentUserId && Number(alert.user_id) === currentUserId) {
            return;
        }
        emergencyToast.innerHTML = `
            <strong>${alert.emergency_type} · ${alert.severity}</strong>
            <p>${alert.username} needs help${alert.location_text ? " near " + alert.location_text : ""}.</p>
            <a href="/emergency">Open Emergency Feed</a>
        `;
        emergencyToast.classList.add("show-emergency-toast");
        playEmergencySound();
        setTimeout(function () {
            emergencyToast.classList.remove("show-emergency-toast");
        }, 9000);
    }

    function showSosSentToast(data) {
        if (!emergencyToast) {
            return;
        }
        const nearbyUsers = data.nearby_users || [];
        const nearbyText = nearbyUsers.length
            ? `Nearby online users: ${nearbyUsers.map(function (user) { return user.username; }).join(", ")}.`
            : "No nearby online users were found yet. The alert is still visible in the emergency feed.";
        emergencyToast.innerHTML = `
            <strong>SOS sent</strong>
            <p>${nearbyText}</p>
            <a href="/emergency">Open Emergency Feed</a>
        `;
        emergencyToast.classList.add("show-emergency-toast");
        setTimeout(function () {
            emergencyToast.classList.remove("show-emergency-toast");
        }, 9000);
    }

    openSosButtons.forEach(function (button) {
        button.addEventListener("click", openSosModal);
    });

    if (closeSosBtn) {
        closeSosBtn.addEventListener("click", closeSosModal);
    }

    if (sosModal) {
        sosModal.addEventListener("click", function (event) {
            if (event.target === sosModal) {
                closeSosModal();
            }
        });
    }

    if (useCurrentLocationBtn) {
        useCurrentLocationBtn.addEventListener("click", function () {
            updateSosLocation(true);
        });
    }

    if (sosForm) {
        sosForm.addEventListener("submit", async function (event) {
            event.preventDefault();
            const button = sosForm.querySelector("button[type='submit']");
            button.disabled = true;
            try {
                await updateSosLocation(true);
                const formData = new FormData(sosForm);
                const payload = Object.fromEntries(formData.entries());
                const response = await fetch("/emergency/create", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify(payload)
                });
                const data = await response.json();
                if (!response.ok || !data.ok) {
                    throw new Error(data.error || "Could not send SOS.");
                }
                closeSosModal();
                showSosSentToast(data);
            } catch (error) {
                alert(error.message);
            } finally {
                button.disabled = false;
            }
        });
    }

    document.querySelectorAll(".emergency-help-btn").forEach(function (button) {
        button.addEventListener("click", async function () {
            const alertId = button.dataset.alertId;
            await fetch(`/emergency/${alertId}/respond`, {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({message: "I can help."})
            });
            button.textContent = "Responding";
            button.disabled = true;
        });
    });

    document.querySelectorAll(".emergency-safe-btn").forEach(function (button) {
        button.addEventListener("click", async function () {
            const alertId = button.dataset.alertId;
            await fetch(`/emergency/${alertId}/safe`, {method: "POST"});
            const card = button.closest(".emergency-alert-card");
            if (card) {
                card.remove();
            }
        });
    });

    if (appSocket) {
        appSocket.on("emergency_alert", showEmergencyToast);
        appSocket.on("emergency_created", showSosSentToast);
        document.querySelectorAll("[data-alert-id]").forEach(function (node) {
            appSocket.emit("join_emergency", {alert_id: node.dataset.alertId});
        });
        appSocket.on("emergency_safe", function (data) {
            const card = document.querySelector(`.emergency-alert-card[data-alert-id="${data.alert_id}"]`);
            if (card) {
                card.remove();
            }
        });
        appSocket.on("emergency_chat_message", function (data) {
            const box = document.getElementById("emergency-chat-box");
            if (!box || Number(box.dataset.alertId) !== Number(data.alert_id)) {
                return;
            }
            const row = document.createElement("div");
            row.className = "emergency-chat-message";
            row.innerHTML = `<strong>${data.username}</strong><p>${data.message_text}</p>`;
            box.appendChild(row);
            box.scrollTop = box.scrollHeight;
        });
    }

    if (!intro || !mainContent) {
        return;
    }

    if (localStorage.getItem("famshare_intro_seen") === "true") {
        intro.style.display = "none";
        mainContent.classList.remove("hidden-content");
        mainContent.classList.add("show-content");
        return;
    }

    localStorage.setItem("famshare_intro_seen", "true");

    setTimeout(() => {
        intro.classList.add("intro-slide-up");
    }, 1100);

    setTimeout(() => {
        intro.style.display = "none";
        mainContent.classList.remove("hidden-content");
        mainContent.classList.add("show-content");
    }, 2100);
});
