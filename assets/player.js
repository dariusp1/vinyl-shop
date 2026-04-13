/**
 * Minimal tap-to-play audio player for WeChat X5/XWebView browser.
 * No autoplay — playback is always user-gesture-triggered.
 *
 * Expects in the DOM:
 *   <button id="play-btn">...</button>
 *   <audio  id="audio" preload="none">...</audio>
 *   <div    id="progress-bar"><div id="progress-fill"></div></div>
 */
function initPlayer() {
    var btn = document.getElementById('play-btn');
    var audio = document.getElementById('audio');
    var fill = document.getElementById('progress-fill');
    if (!btn || !audio) return;

    var PREVIEW_SECONDS = 30;
    var timer = null;
    var raf = null;

    function updateProgress() {
        if (fill && audio.duration) {
            var pct = (audio.currentTime / Math.min(audio.duration, PREVIEW_SECONDS)) * 100;
            fill.style.width = Math.min(pct, 100) + '%';
        }
        if (!audio.paused) {
            raf = requestAnimationFrame(updateProgress);
        }
    }

    function stop() {
        audio.pause();
        audio.currentTime = 0;
        btn.textContent = '\u25B6 \u8BD5\u542C 30\u79D2';
        if (fill) fill.style.width = '0%';
        if (timer) { clearTimeout(timer); timer = null; }
        if (raf) { cancelAnimationFrame(raf); raf = null; }
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
