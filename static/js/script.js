// Patient Case-Taking Software - minimal client-side JS
// (Kept intentionally small - most logic lives server-side in Flask.)

document.addEventListener("DOMContentLoaded", function () {
    // Auto-hide flash messages after a few seconds
    const flashes = document.querySelectorAll(".flash");
    flashes.forEach(function (flash) {
        setTimeout(function () {
            flash.style.transition = "opacity 0.5s ease";
            flash.style.opacity = "0";
            setTimeout(function () {
                flash.remove();
            }, 500);
        }, 4000);
    });

    // Basic client-side check that a file was chosen before "Upload" is clicked.
    // (Server-side validation still happens in app.py - this is just a UX nicety.)
    const uploadForm = document.querySelector(".upload-form");
    if (uploadForm) {
        uploadForm.addEventListener("submit", function (e) {
            const fileInput = uploadForm.querySelector('input[type="file"]');
            if (fileInput && fileInput.files.length === 0) {
                e.preventDefault();
                alert("Please choose a file to upload.");
            }
        });
    }
});
