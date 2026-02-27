// ===================================================================
// Archi Input – Client-side JavaScript
// ===================================================================

/**
 * Save notes for a work item via AJAX
 */
function saveNotes(btn) {
    const id = btn.dataset.id;
    const card = btn.closest('.work-card, .library-item, .recent-item');
    const textarea = card.querySelector(`textarea[data-id="${id}"]`);
    const notes = textarea.value;

    btn.disabled = true;
    btn.textContent = '保存中…';

    fetch('/update_notes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: parseInt(id), notes: notes })
    })
        .then(res => res.json())
        .then(data => {
            if (data.status === 'ok') {
                btn.textContent = '✓ 保存済';
                btn.classList.add('saved');
                setTimeout(() => {
                    btn.textContent = '保存';
                    btn.classList.remove('saved');
                    btn.disabled = false;
                }, 2000);
            } else {
                btn.textContent = 'エラー';
                btn.disabled = false;
            }
        })
        .catch(() => {
            btn.textContent = 'エラー';
            setTimeout(() => {
                btn.textContent = '保存';
                btn.disabled = false;
            }, 2000);
        });
}


// Analysis step messages
const ANALYSIS_STEPS = [
    '🔍 ページをスクレイピング中…',
    '🖼️ OGP画像を取得中…',
    '🧠 Gemini 3.1 Pro で分析中…',
    '📐 建築情報を抽出中…',
    '💾 データを保存中…',
];

function startStepAnimation(el) {
    let step = 0;
    el.innerHTML = `<span class="spinner"></span> ${ANALYSIS_STEPS[0]}`;
    const interval = setInterval(() => {
        step = (step + 1) % ANALYSIS_STEPS.length;
        el.innerHTML = `<span class="spinner"></span> ${ANALYSIS_STEPS[step]}`;
    }, 4000);
    return interval;
}

/**
 * Analyze a work with Gemini AI
 */
function analyzeWork(workId, btn) {
    btn.disabled = true;
    const originalText = btn.textContent;
    const stepInterval = startStepAnimation(btn);

    fetch(`/analyze/${workId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
    })
        .then(res => res.json())
        .then(data => {
            clearInterval(stepInterval);
            if (data.status === 'ok') {
                btn.innerHTML = '✅ 分析完了！';
                btn.classList.add('saved');
                setTimeout(() => location.reload(), 1000);
            } else {
                btn.textContent = 'エラー: ' + (data.message || '不明');
                btn.disabled = false;
                setTimeout(() => { btn.innerHTML = originalText; }, 3000);
            }
        })
        .catch(err => {
            clearInterval(stepInterval);
            btn.textContent = '通信エラー';
            setTimeout(() => { btn.innerHTML = originalText; btn.disabled = false; }, 3000);
        });
}


/**
 * Generate AI report
 */
function generateReport() {
    const btn = document.getElementById('generate-report-btn');
    const output = document.getElementById('report-output');

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> レポート生成中…（30秒ほどお待ちください）';
    output.style.display = 'none';

    // Get custom prompt if available
    const promptEl = document.getElementById('report-prompt');
    const customPrompt = promptEl ? promptEl.value.trim() : '';

    fetch('/generate_report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: customPrompt }),
    })
        .then(res => res.json())
        .then(data => {
            if (data.status === 'ok') {
                output.innerHTML = markdownToHtml(data.report);
                output.style.display = 'block';
                btn.innerHTML = '📊 レポートを再生成する';
                btn.disabled = false;
            } else {
                output.innerHTML = `<p class="report-error">エラー: ${data.message}</p>`;
                output.style.display = 'block';
                btn.innerHTML = '📊 レポートを生成する';
                btn.disabled = false;
            }
        })
        .catch(() => {
            output.innerHTML = '<p class="report-error">通信エラーが発生しました</p>';
            output.style.display = 'block';
            btn.innerHTML = '📊 レポートを生成する';
            btn.disabled = false;
        });
}


/**
 * Simple markdown to HTML converter
 */
function markdownToHtml(md) {
    let html = md
        // Headers
        .replace(/^### (.+)$/gm, '<h3>$1</h3>')
        .replace(/^## (.+)$/gm, '<h2>$1</h2>')
        .replace(/^# (.+)$/gm, '<h1>$1</h1>')
        // Bold
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        // Italic
        .replace(/\*(.+?)\*/g, '<em>$1</em>')
        // Lists
        .replace(/^- (.+)$/gm, '<li>$1</li>')
        .replace(/^(\d+)\. (.+)$/gm, '<li>$2</li>')
        // Line breaks
        .replace(/\n\n/g, '</p><p>')
        .replace(/\n/g, '<br>');

    // Wrap consecutive <li> elements in <ul>
    html = html.replace(/((?:<li>.*?<\/li><br>?)+)/g, '<ul>$1</ul>');

    return '<div class="report-content"><p>' + html + '</p></div>';
}


/**
 * Preview uploaded image
 */
function previewImage(input) {
    const preview = document.getElementById('image-preview');
    const img = document.getElementById('preview-img');
    const label = document.getElementById('file-label');

    if (input.files && input.files[0]) {
        const reader = new FileReader();
        reader.onload = function (e) {
            img.src = e.target.result;
            preview.style.display = 'flex';
            label.style.display = 'none';
        };
        reader.readAsDataURL(input.files[0]);
    }
}

function clearImage() {
    const input = document.getElementById('image');
    const preview = document.getElementById('image-preview');
    const label = document.getElementById('file-label');
    input.value = '';
    preview.style.display = 'none';
    label.style.display = 'flex';
}


/**
 * Run visual analysis on a work's image
 */
function visualAnalyze(workId, btn) {
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> 視覚分析中…';

    const output = document.getElementById(`visual-result-${workId}`);

    fetch(`/visual_analyze/${workId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
    })
        .then(res => res.json())
        .then(data => {
            if (data.status === 'ok') {
                output.innerHTML = '<h4 class="visual-title">🖼️ 視覚分析</h4>' + markdownToHtml(data.result);
                output.style.display = 'block';
                btn.innerHTML = '✓ 視覚分析完了';
                btn.classList.add('saved');
            } else {
                btn.textContent = 'エラー: ' + (data.message || '不明');
            }
            setTimeout(() => {
                btn.innerHTML = originalText;
                btn.classList.remove('saved');
                btn.disabled = false;
            }, 3000);
        })
        .catch(() => {
            btn.textContent = '通信エラー';
            setTimeout(() => {
                btn.innerHTML = originalText;
                btn.disabled = false;
            }, 3000);
        });
}


/**
 * Toggle deep analysis panel for a work
 */
function toggleDeepAnalysis(workId) {
    const panel = document.getElementById(`deep-${workId}`);
    if (panel.style.display === 'none') {
        panel.style.display = 'block';
        const input = document.getElementById(`deep-prompt-${workId}`);
        if (input) input.focus();
    } else {
        panel.style.display = 'none';
    }
}


/**
 * Deep analyze a specific work with user's prompt
 */
function deepAnalyze(workId) {
    const input = document.getElementById(`deep-prompt-${workId}`);
    const output = document.getElementById(`deep-output-${workId}`);
    const prompt = input.value.trim();

    if (!prompt) {
        input.focus();
        return;
    }

    output.innerHTML = '<div class="deep-loading"><span class="spinner"></span> 深掘り分析中…</div>';
    output.style.display = 'block';

    fetch(`/deep_analyze/${workId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: prompt }),
    })
        .then(res => res.json())
        .then(data => {
            if (data.status === 'ok') {
                output.innerHTML = markdownToHtml(data.result);
            } else {
                output.innerHTML = `<p class="report-error">エラー: ${data.message}</p>`;
            }
        })
        .catch(() => {
            output.innerHTML = '<p class="report-error">通信エラーが発生しました</p>';
        });
}



// Auto-dismiss alerts after 4 seconds (but not if analyzing)
document.addEventListener('DOMContentLoaded', () => {
    const autoAnalyze = document.getElementById('auto-analyze-status');

    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        // Don't auto-dismiss if analysis is in progress
        if (autoAnalyze && alert.contains(autoAnalyze)) return;
        setTimeout(() => {
            alert.style.transition = 'opacity 0.4s, transform 0.4s';
            alert.style.opacity = '0';
            alert.style.transform = 'translateY(-10px)';
            setTimeout(() => alert.remove(), 400);
        }, 4000);
    });

    // Poll for auto-analysis completion
    if (autoAnalyze) {
        const workId = autoAnalyze.dataset.id;
        let stepIdx = 0;
        const stepInterval = setInterval(() => {
            stepIdx = (stepIdx + 1) % ANALYSIS_STEPS.length;
            autoAnalyze.innerHTML = `<span class="spinner"></span> ${ANALYSIS_STEPS[stepIdx]}`;
        }, 4000);

        const pollInterval = setInterval(() => {
            fetch(`/status/${workId}`)
                .then(res => res.json())
                .then(data => {
                    if (data.is_analyzed) {
                        clearInterval(pollInterval);
                        clearInterval(stepInterval);
                        autoAnalyze.innerHTML = '✅ AI分析完了！';
                        autoAnalyze.classList.add('analyze-done');
                        setTimeout(() => location.reload(), 1500);
                    }
                })
                .catch(() => { });
        }, 3000);

        // Stop polling after 2 minutes
        setTimeout(() => {
            clearInterval(pollInterval);
            clearInterval(stepInterval);
            if (!autoAnalyze.classList.contains('analyze-done')) {
                autoAnalyze.innerHTML = '⏳ 分析に時間がかかっています。ページをリロードしてください。';
            }
        }, 120000);
    }
});


/**
 * Toggle bulk input panel
 */
function toggleBulk() {
    const panel = document.getElementById('bulk-panel');
    panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
}
