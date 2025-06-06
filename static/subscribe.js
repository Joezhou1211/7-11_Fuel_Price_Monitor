document.addEventListener('DOMContentLoaded', () => {
    const alertCheck = document.getElementById('alert');
    const methodSel = document.getElementById('method');
    const alertOptions = document.getElementById('alertOptions');
    const thresholdInput = document.getElementById('threshold');
    const maInput = document.getElementById('maWindow');
    const sendBtn = document.getElementById('sendCode');
    let countdown = 0;

    alertCheck.addEventListener('change', () => {
        alertOptions.style.display = alertCheck.checked ? 'block' : 'none';
    });

    methodSel.addEventListener('change', () => {
        thresholdInput.style.display = methodSel.value === 'fixed' ? 'inline' : 'none';
        maInput.style.display = methodSel.value === 'moving_average' ? 'inline' : 'none';
    });

    document.getElementById('next').onclick = () => {
        document.getElementById('step1').style.display = 'none';
        document.getElementById('step2').style.display = 'block';
    };

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
        fetch('/send_code', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({email, action:'subscribe'})})
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
        const weekly = document.getElementById('weekly').checked;
        const alerts = alertCheck.checked ? [{
            fuel_type: document.getElementById('fuelType').value,
            method: methodSel.value,
            threshold: parseFloat(thresholdInput.value) || undefined,
            ma_window: parseInt(maInput.value) || undefined
        }] : [];
        fetch('/subscribe', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({email, code, weekly, alerts})})
            .then(r => {
                if(r.ok) {
                    showMessage('Subscription successful', 'success');
                    setTimeout(() => { window.location='/'; }, 800);
                } else {
                    r.json().then(d => showMessage(d.error || 'Failed', 'error'));
                }
            });
    };
});
