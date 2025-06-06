async function downloadData() {
    if (downloadTimer > 0) {
        showMessage(`Please wait ${downloadTimer}s before downloading again`, 'warning');
        return;
    }

    try {
        showMessage('Downloading data...', 'info');
        
        const [fuelPrices, data] = await Promise.all([
            fetch('fuel_prices.json').then(response => response.json()),
            fetch('data.json').then(response => response.json())
        ]);

        // Convert JSON to blobs and trigger download
        const fuelPricesBlob = new Blob([JSON.stringify(fuelPrices, null, 2)], { type: 'application/json' });
        const dataBlob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });

        // Trigger download
        const fuelPricesUrl = URL.createObjectURL(fuelPricesBlob);
        const dataUrl = URL.createObjectURL(dataBlob);

        const fuelPricesLink = document.createElement('a');
        const dataLink = document.createElement('a');

        fuelPricesLink.href = fuelPricesUrl;
        dataLink.href = dataUrl;

        fuelPricesLink.download = 'fuel_prices.json';
        dataLink.download = 'data.json';

        fuelPricesLink.click();
        dataLink.click();

        // Clean up urls
        URL.revokeObjectURL(fuelPricesUrl);
        URL.revokeObjectURL(dataUrl);

        showMessage('Download successful!', 'success');

        // cooldown 3s
        downloadTimer = 3;
        const countdown = setInterval(() => {
            downloadTimer--;
            if (downloadTimer <= 0) {
                clearInterval(countdown);
            }
        }, 1000);
    } catch (error) {
        console.error('Failed to download data:', error);
        showMessage('Download failed. Please try again later', 'error');
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
        console.error('Failed to fetch chart data', err);
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

// notification helper
function showMessage(message, type = 'info') {
    // remove existing message
    const existingMessage = document.querySelector('.message-container');
    if (existingMessage) {
        existingMessage.remove();
    }
    
    // create container
    const messageContainer = document.createElement('div');
    messageContainer.className = `message-container message-${type}`;
    
    // icon by type
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
    
    // style
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
    
    // color by type
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


// subscription links handled on separate pages
