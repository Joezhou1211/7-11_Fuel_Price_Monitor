document.addEventListener('DOMContentLoaded', () => {
    const sendBtn = document.getElementById('sendCode');
    let countdown = 0;

    function startCountdown() {
        countdown = 60;
        sendBtn.disabled = true;
        sendBtn.textContent = `Send Code (${countdown})`;
        const timer = setInterval(() => {
            countdown--;
            sendBtn.textContent = `Send Code (${countdown})`;
            if (countdown <= 0) {
                clearInterval(timer);
                sendBtn.disabled = false;
                sendBtn.textContent = 'Send Code';
            }
        }, 1000);
    }

    sendBtn.onclick = () => {
        const email = document.getElementById('email').value;
        if (!email) return;
        fetch('/send_code', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({email, action:'unsubscribe'})})
            .then(res => {
                if (res.ok) {
                    startCountdown();
                } else {
                    res.json().then(d => alert(d.error || 'Failed'));
                }
            });
    };
    document.getElementById('submit').onclick = () => {
        const email = document.getElementById('email').value;
        const code = document.getElementById('code').value;
        fetch('/unsubscribe', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({email, code})})
            .then(r => {
                if(r.ok) {
                    window.location = '/';
                } else {
                    r.json().then(d => alert(d.error || 'Failed'));
                }
            });
    };
});
