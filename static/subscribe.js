document.addEventListener('DOMContentLoaded', () => {
    const alertCheck = document.getElementById('alert');
    const methodSel = document.getElementById('method');
    const alertOptions = document.getElementById('alertOptions');
    const thresholdInput = document.getElementById('threshold');

    alertCheck.addEventListener('change', () => {
        alertOptions.style.display = alertCheck.checked ? 'block' : 'none';
    });

    methodSel.addEventListener('change', () => {
        thresholdInput.style.display = methodSel.value === 'fixed' ? 'inline' : 'none';
    });

    document.getElementById('next').onclick = () => {
        document.getElementById('step1').style.display = 'none';
        document.getElementById('step2').style.display = 'block';
    };

    document.getElementById('sendCode').onclick = () => {
        const email = document.getElementById('email').value;
        fetch('/send_code', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({email})});
    };

    document.getElementById('submit').onclick = () => {
        const email = document.getElementById('email').value;
        const code = document.getElementById('code').value;
        const weekly = document.getElementById('weekly').checked;
        const alerts = alertCheck.checked ? [{fuel_type: document.getElementById('fuelType').value, method: methodSel.value, threshold: parseFloat(thresholdInput.value) || undefined}] : [];
        fetch('/subscribe', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({email, code, weekly, alerts})})
            .then(r => {if(r.ok) window.location='/';});
    };
});
