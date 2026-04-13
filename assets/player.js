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

    var timer    = null;
    var raf      = null;
    var pending  = false; // play() promise in flight

    function updateProgress() {
        if (fill && audio.duration) {
            fill.style.width = Math.min((audio.currentTime / Math.min(audio.duration, PREVIEW_SECONDS)) * 100, 100) + '%';
        }
        if (!audio.paused) raf = requestAnimationFrame(updateProgress);
    }

    function stop() {
        if (!audio.paused) audio.pause();
        audio.currentTime = 0;
        btn.textContent = '\u25B6 \u8BD5\u542C 30\u79D2';
        if (fill) fill.style.width = '0%';
        if (timer) { clearTimeout(timer); timer = null; }
        if (raf)   { cancelAnimationFrame(raf); raf = null; }
    }

    audio.addEventListener('error', function () {
        btn.textContent = '[ \u65E0\u6CD5\u64AD\u653E ]';
        btn.disabled = true;
    });

    btn.addEventListener('click', function () {
        if (pending) return;

        if (audio.paused) {
            pending = true;
            var p = audio.play();
            if (p !== undefined) {
                p.then(function () {
                    pending = false;
                    btn.textContent = '\u23F8 \u6682\u505C';
                    updateProgress();
                    timer = setTimeout(stop, PREVIEW_SECONDS * 1000);
                }).catch(function (err) {
                    pending = false;
                    if (err.name !== 'AbortError') {
                        btn.textContent = '[ \u65E0\u6CD5\u64AD\u653E ]';
                        btn.disabled = true;
                    }
                });
            } else {
                // Legacy browser — no promise returned
                pending = false;
                btn.textContent = '\u23F8 \u6682\u505C';
                updateProgress();
                timer = setTimeout(stop, PREVIEW_SECONDS * 1000);
            }
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

    var active = null; // { audio, btn, fill, timer, raf, pending }

    function stopActive() {
        if (!active) return;
        if (!active.audio.paused) active.audio.pause();
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

        var state = { audio: audio, btn: btn, fill: fill, timer: null, raf: null, pending: false };

        function updateProgress() {
            if (fill && audio.duration) {
                fill.style.width = Math.min((audio.currentTime / Math.min(audio.duration, PREVIEW_SECONDS)) * 100, 100) + '%';
            }
            if (!audio.paused) state.raf = requestAnimationFrame(updateProgress);
        }

        function stopThis() {
            if (!audio.paused) audio.pause();
            audio.currentTime = 0;
            btn.textContent = '\u25B6 \u8BD5\u542C';
            if (fill) fill.style.width = '0%';
            if (state.timer) { clearTimeout(state.timer); state.timer = null; }
            if (state.raf)   { cancelAnimationFrame(state.raf); state.raf = null; }
            active = null;
        }

        audio.addEventListener('error', function () {
            btn.textContent = '[ \u65E0\u6CD5\u64AD\u653E ]';
            btn.disabled = true;
        });

        btn.addEventListener('click', function () {
            if (state.pending) return;

            if (active && active !== state) stopActive();

            if (audio.paused) {
                state.pending = true;
                var p = audio.play();
                if (p !== undefined) {
                    p.then(function () {
                        state.pending = false;
                        btn.textContent = '\u23F8 \u6682\u505C';
                        updateProgress();
                        state.timer = setTimeout(stopThis, PREVIEW_SECONDS * 1000);
                        active = state;
                    }).catch(function (err) {
                        state.pending = false;
                        if (err.name !== 'AbortError') {
                            btn.textContent = '[ \u65E0\u6CD5\u64AD\u653E ]';
                            btn.disabled = true;
                        }
                    });
                } else {
                    state.pending = false;
                    btn.textContent = '\u23F8 \u6682\u505C';
                    updateProgress();
                    state.timer = setTimeout(stopThis, PREVIEW_SECONDS * 1000);
                    active = state;
                }
            } else {
                stopThis();
            }
        });

        audio.addEventListener('ended', function () {
            if (active === state) stopThis();
        });
    });
}
