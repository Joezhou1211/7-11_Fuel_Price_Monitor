let emailRegex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;

function getRecipientMails() {
    return fetch('recipient_mails.json')
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok ' + response.statusText);
            }
            return response.json();
        })
        .catch(error => {
            console.error('Error fetching recipient mails:', error);
            return [];
        });
}

function updateRecipientMails(mails) {
    return fetch('recipient_mails.json', {
        method: 'PUT',
        body: JSON.stringify(mails),
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('Network response was not ok ' + response.statusText);
        }
    })
    .catch(error => console.error('Error updating recipient mails:', error));
}

document.getElementById('subscribeButton').addEventListener('click', function() {
    let inputValue = document.getElementById('inputField').value;
    console.log('Subscribe button clicked');

    // 检查输入的值是否符合电子邮件地址的格式
    if (emailRegex.test(inputValue)) {
        getRecipientMails().then(mails => {
            // 如果输入的电子邮件地址不在文件中，将它添加到文件中
            if (!mails.includes(inputValue)) {
                mails.push(inputValue);
                updateRecipientMails(mails).then(() => {
                    alert('Subscription successful!');
                });
            } else {
                alert('You are already subscribed!');
            }
        });
    } else {
        alert('Please enter a valid email address!');
    }
});

document.getElementById('unsubscribeButton').addEventListener('click', function() {
    let inputValue = document.getElementById('inputField').value;
    console.log('Unsubscribe button clicked');

    // 检查输入的值是否符合电子邮件地址的格式
    if (emailRegex.test(inputValue)) {
        getRecipientMails().then(mails => {
            // 如果输入的电子邮件地址在文件中，将它从文件中删除
            let index = mails.indexOf(inputValue);
            if (index !== -1) {
                mails.splice(index, 1);
                updateRecipientMails(mails).then(() => {
                    alert('Unsubscription successful!');
                });
            } else {
                alert('You are not subscribed!');
            }
        });
    } else {
        alert('Please enter a valid email address!');
    }
});
