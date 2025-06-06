document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('sendCode').onclick = () => {
        const email = document.getElementById('email').value;
        fetch('/send_code', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({email})});
    };
    document.getElementById('submit').onclick = () => {
        const email = document.getElementById('email').value;
        const code = document.getElementById('code').value;
        fetch('/unsubscribe', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({email, code})})
            .then(r => {if(r.ok) window.location='/';});
    };
});
