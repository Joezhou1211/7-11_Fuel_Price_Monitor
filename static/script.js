async function downloadData() {
    if (downloadTimer > 0) {
        showMessage(`请等待 ${downloadTimer} 秒后再次下载`, 'warning');
        return;
    }

    try {
        showMessage('正在下载数据...', 'info');
        
        const [fuelPrices, data] = await Promise.all([
            fetch('fuel_prices.json').then(response => response.json()),
            fetch('data.json').then(response => response.json())
        ]);

        // 将数据转换为 Blob 并下载
        const fuelPricesBlob = new Blob([JSON.stringify(fuelPrices, null, 2)], { type: 'application/json' });
        const dataBlob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });

        // 创建下载链接并触发下载
        const fuelPricesUrl = URL.createObjectURL(fuelPricesBlob);
        const dataUrl = URL.createObjectURL(dataBlob);

        const fuelPricesLink = document.createElement('a');
        const dataLink = document.createElement('a');

        fuelPricesLink.href = fuelPricesUrl;
        dataLink.href = dataUrl;

        fuelPricesLink.download = 'fuel_prices.json';
        dataLink.download = 'data.json';

        // 触发下载
        fuelPricesLink.click();
        dataLink.click();

        // 清理 URL 对象
        URL.revokeObjectURL(fuelPricesUrl);
        URL.revokeObjectURL(dataUrl);

        showMessage('数据下载成功！', 'success');

        // 开始倒计时3秒
        downloadTimer = 3;
        const countdown = setInterval(() => {
            downloadTimer--;
            if (downloadTimer <= 0) {
                clearInterval(countdown);
            }
        }, 1000);
    } catch (error) {
        console.error('下载数据失败:', error);
        showMessage('下载数据失败，请稍后重试', 'error');
    }
}

// 初始化下载计时器
let downloadTimer = 0;

// ---------------- Chart Rendering -----------------
let chart;
const COLORS = ['#2196F3', '#FF5722', '#4CAF50', '#9C27B0', '#FFC107'];

async function fetchChartData() {
    try {
        const records = await fetch('fuel_prices.json').then(r => r.json());
        renderChart(records);
    } catch (err) {
        console.error('获取图表数据失败', err);
    }
}

function renderChart(records) {
    const grouped = {};
    records.forEach(rec => {
        const t = rec.type || 'UNKNOWN';
        if (!grouped[t]) grouped[t] = [];
        grouped[t].push({ x: new Date(rec.timestamp), y: rec.price });
    });

    const datasets = Object.keys(grouped).map((type, idx) => ({
        label: type,
        data: grouped[type].sort((a,b)=>a.x-b.x),
        borderColor: COLORS[idx % COLORS.length],
        tension: 0.3,
        fill: false
    }));

    if (!chart) {
        chart = new Chart(document.getElementById('priceChart'), {
            type: 'line',
            data: { datasets },
            options: {
                responsive: true,
                interaction: { mode: 'index', intersect: false },
                scales: {
                    x: { type: 'time', time: { unit: 'day' } },
                    y: { beginAtZero: false }
                }
            }
        });
    } else {
        chart.data.datasets = datasets;
        chart.update();
    }
}

// 消息提示函数
function showMessage(message, type = 'info') {
    // 移除之前的消息
    const existingMessage = document.querySelector('.message-container');
    if (existingMessage) {
        existingMessage.remove();
    }
    
    // 创建新的消息容器
    const messageContainer = document.createElement('div');
    messageContainer.className = `message-container message-${type}`;
    
    // 根据类型设置图标
    let icon = '';
    switch(type) {
        case 'success':
            icon = '✓';
            break;
        case 'error':
            icon = '✗';
            break;
        case 'warning':
            icon = '⚠';
            break;
        default:
            icon = 'ℹ';
    }
    
    messageContainer.innerHTML = `
        <span class="message-icon">${icon}</span>
        <span class="message-text">${message}</span>
    `;
    
    // 添加样式
    messageContainer.style.position = 'fixed';
    messageContainer.style.top = '20px';
    messageContainer.style.left = '50%';
    messageContainer.style.transform = 'translateX(-50%)';
    messageContainer.style.padding = '12px 20px';
    messageContainer.style.borderRadius = '5px';
    messageContainer.style.boxShadow = '0 3px 10px rgba(0, 0, 0, 0.2)';
    messageContainer.style.zIndex = '1000';
    messageContainer.style.display = 'flex';
    messageContainer.style.alignItems = 'center';
    messageContainer.style.gap = '10px';
    messageContainer.style.fontFamily = 'Arial, sans-serif';
    messageContainer.style.fontSize = '14px';
    
    // 根据类型设置颜色
    switch(type) {
        case 'success':
            messageContainer.style.backgroundColor = '#4CAF50';
            messageContainer.style.color = 'white';
            break;
        case 'error':
            messageContainer.style.backgroundColor = '#F44336';
            messageContainer.style.color = 'white';
            break;
        case 'warning':
            messageContainer.style.backgroundColor = '#FF9800';
            messageContainer.style.color = 'white';
            break;
        default:
            messageContainer.style.backgroundColor = '#2196F3';
            messageContainer.style.color = 'white';
    }
    
    // 添加到文档
    document.body.appendChild(messageContainer);
    
    // 3秒后自动删除
    setTimeout(() => {
        messageContainer.style.opacity = '0';
        messageContainer.style.transition = 'opacity 0.5s ease';
        
        setTimeout(() => {
            messageContainer.remove();
        }, 500);
    }, 3000);
}

// 添加事件监听器
document.addEventListener('DOMContentLoaded', () => {
    const downloadButton = document.getElementById('downloadButton');
    if (downloadButton) {
        downloadButton.addEventListener('click', downloadData);
    }

    // 初始化图表
    fetchChartData();
    setInterval(fetchChartData, 60000);
});


//订阅和取消订阅
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
                    showMessage('订阅成功！您将定期收到油价更新邮件', 'success');
                    document.getElementById('inputField').value = '';
                });
            } else {
                showMessage('您已经订阅过了！', 'info');
            }
        });
    } else {
        showMessage('请输入有效的邮箱地址！', 'error');
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
                    showMessage('取消订阅成功！您将不再收到油价更新邮件', 'success');
                    document.getElementById('inputField').value = '';
                });
            } else {
                showMessage('您尚未订阅，无需取消！', 'warning');
            }
        });
    } else {
        showMessage('请输入有效的邮箱地址！', 'error');
    }
});