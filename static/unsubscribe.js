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
                    showMessage('Verification code sent', 'success');
                } else {
                    res.json().then(d => showMessage(d.error || 'Failed', 'error'));
                }
            });
    };
    document.getElementById('submit').onclick = () => {
        const email = document.getElementById('email').value;
        const code = document.getElementById('code').value;
        fetch('/unsubscribe', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({email, code})})
            .then(r => {
                if(r.ok) {
                    showMessage('Unsubscribed', 'success');
                    setTimeout(() => { window.location='/'; }, 800);
                } else {
                    r.json().then(d => showMessage(d.error || 'Failed', 'error'));
                }
            });
    };
});
