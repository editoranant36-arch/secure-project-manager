document.addEventListener('DOMContentLoaded', () => {

    // 1. Password Visibility Toggle
    document.querySelectorAll('.toggle-password-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const targetId = btn.getAttribute('data-target');
            const input = document.getElementById(targetId);
            if (!input) return;
            const icon = btn.querySelector('i');
            if (input.type === 'password') {
                input.type = 'text';
                if (icon) icon.className = 'fas fa-eye-slash';
            } else {
                input.type = 'password';
                if (icon) icon.className = 'fas fa-eye';
            }
        });
    });

    // 2. Real-time Password Strength Meter
    const passwordInput = document.getElementById('passwordInput');
    const strengthBarFill = document.getElementById('strengthBarFill');
    const strengthText = document.getElementById('strengthText');

    if (passwordInput && strengthBarFill && strengthText) {
        passwordInput.addEventListener('input', () => {
            const val = passwordInput.value;
            let score = 0;
            if (val.length >= 8) score += 20;
            if (val.length >= 12) score += 10;
            if (/[A-Z]/.test(val)) score += 20;
            if (/[a-z]/.test(val)) score += 20;
            if (/[0-9]/.test(val)) score += 15;
            if (/[!@#$%^&*(),.?":{}|<>]/.test(val)) score += 15;

            strengthBarFill.style.width = `${score}%`;

            if (score <= 30) {
                strengthBarFill.style.backgroundColor = 'var(--accent-rose)';
                strengthText.textContent = 'Weak';
                strengthText.style.color = 'var(--accent-rose)';
            } else if (score <= 70) {
                strengthBarFill.style.backgroundColor = 'var(--accent-amber)';
                strengthText.textContent = 'Moderate';
                strengthText.style.color = 'var(--accent-amber)';
            } else {
                strengthBarFill.style.backgroundColor = 'var(--accent-emerald)';
                strengthText.textContent = 'Strong';
                strengthText.style.color = 'var(--accent-emerald)';
            }
        });
    }

    // 3. Auto-advancing 6-Digit OTP Box Logic
    const otpBoxes = document.querySelectorAll('.otp-digit');
    const fullOtpInput = document.getElementById('fullOtpInput');

    if (otpBoxes.length === 6) {
        const updateFullCode = () => {
            let combined = '';
            otpBoxes.forEach(b => combined += b.value.trim());
            if (fullOtpInput) fullOtpInput.value = combined;
        };

        otpBoxes.forEach((box, index) => {
            box.addEventListener('input', (e) => {
                const val = box.value.replace(/[^0-9]/g, '');
                box.value = val ? val[0] : '';
                updateFullCode();
                if (box.value && index < 5) {
                    otpBoxes[index + 1].focus();
                }
            });

            box.addEventListener('keydown', (e) => {
                if (e.key === 'Backspace' && !box.value && index > 0) {
                    otpBoxes[index - 1].focus();
                }
            });

            box.addEventListener('paste', (e) => {
                e.preventDefault();
                const pasteData = (e.clipboardData || window.clipboardData).getData('text');
                const clean = pasteData.replace(/[^0-9]/g, '').slice(0, 6);
                for (let i = 0; i < clean.length; i++) {
                    otpBoxes[i].value = clean[i];
                }
                updateFullCode();
                if (clean.length > 0) {
                    const focusIndex = Math.min(clean.length, 5);
                    otpBoxes[focusIndex].focus();
                }
            });
        });
    }

    // 4. Copy to Clipboard
    document.querySelectorAll('.copy-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const targetSelector = btn.getAttribute('data-clipboard-target');
            const targetEl = document.querySelector(targetSelector);
            if (!targetEl) return;

            const textToCopy = targetEl.value || targetEl.innerText;
            navigator.clipboard.writeText(textToCopy.trim()).then(() => {
                const originalHtml = btn.innerHTML;
                btn.innerHTML = '<i class="fas fa-check text-success"></i> Copied!';
                setTimeout(() => {
                    btn.innerHTML = originalHtml;
                }, 2000);
            }).catch(err => {
                console.error("Clipboard copy failed: ", err);
            });
        });
    });

    // 5. Drag-and-Drop File Upload Zone
    const dropzone = document.getElementById('dropzone');
    const fileInput = document.getElementById('projectFilesInput');
    const selectedFilesList = document.getElementById('selectedFilesList');

    if (dropzone && fileInput) {
        ['dragenter', 'dragover'].forEach(evt => {
            dropzone.addEventListener(evt, (e) => {
                e.preventDefault();
                dropzone.classList.add('dragover');
            });
        });

        ['dragleave', 'drop'].forEach(evt => {
            dropzone.addEventListener(evt, (e) => {
                e.preventDefault();
                dropzone.classList.remove('dragover');
            });
        });

        dropzone.addEventListener('drop', (e) => {
            if (e.dataTransfer.files.length) {
                fileInput.files = e.dataTransfer.files;
                renderFileList(fileInput.files);
            }
        });

        dropzone.addEventListener('click', () => {
            fileInput.click();
        });

        fileInput.addEventListener('change', () => {
            renderFileList(fileInput.files);
        });

        function renderFileList(files) {
            if (!selectedFilesList) return;
            selectedFilesList.innerHTML = '';
            if (files.length === 0) return;

            const ul = document.createElement('div');
            ul.className = 'd-flex flex-column gap-2 mt-3';

            Array.from(files).forEach((f, idx) => {
                const sizeKb = (f.size / 1024).toFixed(1);
                const item = document.createElement('div');
                item.className = 'p-2 rounded bg-dark border border-secondary d-flex justify-content-between align-items-center';
                item.innerHTML = `
                    <div class="d-flex align-items-center gap-2">
                        <i class="fas fa-file text-info"></i>
                        <span class="small font-monospace">${f.name}</span>
                    </div>
                    <span class="badge bg-secondary">${sizeKb} KB</span>
                `;
                ul.appendChild(item);
            });

            selectedFilesList.appendChild(ul);
        }
    }

    // 6. Project Search & Filter on Projects Page
    const projectSearchInput = document.getElementById('projectSearch');
    const projectCards = document.querySelectorAll('.project-item');

    if (projectSearchInput && projectCards.length) {
        projectSearchInput.addEventListener('input', () => {
            const query = projectSearchInput.value.toLowerCase().trim();
            projectCards.forEach(card => {
                const name = (card.getAttribute('data-name') || '').toLowerCase();
                const desc = (card.getAttribute('data-desc') || '').toLowerCase();
                const category = (card.getAttribute('data-category') || '').toLowerCase();

                if (name.includes(query) || desc.includes(query) || category.includes(query)) {
                    card.style.display = '';
                } else {
                    card.style.display = 'none';
                }
            });
        });
    }

});
