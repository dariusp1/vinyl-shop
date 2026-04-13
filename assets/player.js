/**
 * Audio player for WeChat X5/XWebView browser.
 * No autoplay — playback is always user-gesture-triggered.
 *
 * Single-track mode (original):
 *   initPlayer() — expects #play-btn, #audio, #progress-fill in DOM
 *
 * Multi-track mode:
 *   initMultiPlayer() — expects .track-item elements each containing
 *   a .track-btn button, an <audio>, and a .progress-fill div
 */

var PREVIEW_SECONDS = 30;

function initPlayer() {
    var btn   = document.getElementById('play-btn');
    var audio = document.getElementById('audio');
    var fill  = document.getElementById('progress-fill');
    if (!btn || !audio) return;

    var timer = null;
    var raf   = null;

    function updateProgress() {
        if (fill && audio.duration) {
            fill.style.width = Math.min((audio.currentTime / Math.min(audio.duration, PREVIEW_SECONDS)) * 100, 100) + '%';
        }
        if (!audio.paused) raf = requestAnimationFrame(updateProgress);
    }

    function stop() {
        audio.pause();
        audio.currentTime = 0;
        btn.textContent = '\u25B6 \u8BD5\u542C 30\u79D2';
        if (fill) fill.style.width = '0%';
        if (timer) { clearTimeout(timer); timer = null; }
        if (raf)   { cancelAnimationFrame(raf); raf = null; }
    }

    btn.addEventListener('click', function () {
        if (audio.paused) {
            audio.play();
            btn.textContent = '\u23F8 \u6682\u505C';
            updateProgress();
            timer = setTimeout(stop, PREVIEW_SECONDS * 1000);
        } else {
            stop();
        }
    });

    audio.addEventListener('ended', stop);
}

function initMultiPlayer() {
    var items = document.querySelectorAll('.track-item');
    if (!items.length) {
        initPlayer();
        return;
    }

    var active = null; // { audio, btn, fill, timer, raf }

    function stopActive() {
        if (!active) return;
        active.audio.pause();
        active.audio.currentTime = 0;
        active.btn.textContent = '\u25B6 \u8BD5\u542C';
        if (active.fill) active.fill.style.width = '0%';
        if (active.timer) { clearTimeout(active.timer); active.timer = null; }
        if (active.raf)   { cancelAnimationFrame(active.raf); active.raf = null; }
        active = null;
    }

    items.forEach(function (item) {
        var btn   = item.querySelector('.track-btn');
        var audio = item.querySelector('audio');
        var fill  = item.querySelector('.progress-fill');
        if (!btn || !audio) return;

        var state = { audio: audio, btn: btn, fill: fill, timer: null, raf: null };

        function updateProgress() {
            if (fill && audio.duration) {
                fill.style.width = Math.min((audio.currentTime / Math.min(audio.duration, PREVIEW_SECONDS)) * 100, 100) + '%';
            }
            if (!audio.paused) state.raf = requestAnimationFrame(updateProgress);
        }

        btn.addEventListener('click', function () {
            if (active && active !== state) stopActive();

            if (audio.paused) {
                audio.play();
                btn.textContent = '\u23F8 \u6682\u505C';
                updateProgress();
                state.timer = setTimeout(function () {
                    audio.pause();
                    audio.currentTime = 0;
                    btn.textContent = '\u25B6 \u8BD5\u542C';
                    if (fill) fill.style.width = '0%';
                    if (state.raf) { cancelAnimationFrame(state.raf); state.raf = null; }
                    active = null;
                }, PREVIEW_SECONDS * 1000);
                active = state;
            } else {
                stopActive();
            }
        });

        audio.addEventListener('ended', function () {
            if (active === state) stopActive();
        });
    });
}
