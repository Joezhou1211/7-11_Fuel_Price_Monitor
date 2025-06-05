import requests
import json
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from datetime import datetime, timedelta
from apscheduler.schedulers.blocking import BlockingScheduler
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter
from matplotlib.dates import AutoDateLocator
from flask import Flask, render_template, request, send_from_directory
import threading
import pandas as pd

# 配置日志记录
logging.basicConfig(
    filename='app.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# 定义保存文件路径
data_file = 'fuel_prices.json'
full_data = 'data.json'


def get_recipient_mails():
    global recipient_mails
    with open("recipient_mails.json", 'r') as file:
        recipient_mails = json.load(file)


# 邮件发送相关信息
mail = ''
mail_password = ''
recipient_mails = []
get_recipient_mails()

alert_sent = {'timestamp': '2024-06-17 04:00:59', 'price': 0}

# 初始化调度器
scheduler = BlockingScheduler()


def fetch_and_update_fuel_prices():
    logging.info("开始获取和更新油价数据...")
    url = 'https://projectzerothree.info/api.php?format=json'
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        logging.info("成功获取API数据")
    except requests.RequestException as e:
        logging.error(f"API请求失败: {e}")
        return

    qld_u91_prices = []

    for region in data['regions']:
        if region['region'] == 'QLD':
            for price_info in region['prices']:
                if price_info['type'] == 'U91':
                    qld_u91_prices.append(price_info)

    if not qld_u91_prices:
        logging.info("没有找到QLD地区的U91汽油价格信息。")
        return

    qld_u91_prices_sorted = sorted(qld_u91_prices, key=lambda x: x['price'])
    lowest_price_info = qld_u91_prices_sorted[0]
    lowest_price_info['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 读取并更新 data.json
    try:
        with open(full_data, 'r') as file:
            record_data = json.load(file)
        logging.info("成功读取data.json文件")
    except FileNotFoundError:
        logging.info("没有找到data.json文件，将创建新文件")
        return

    record_data.append(lowest_price_info)
    with open(full_data, 'w') as file:
        json.dump(record_data, file, indent=4)
        logging.info(f"*** 成功更新data.json: {lowest_price_info} ***")

    # 读取并更新 fuel_prices.json
    try:
        with open(data_file, 'r') as file:
            price_records = json.load(file)
        logging.info("成功读取fuel_prices.json文件")
    except FileNotFoundError:
        logging.info("没有找到fuel_prices.json")
        return

    # 更新当天最低价格记录
    today_str = datetime.now().strftime('%Y-%m-%d')
    today_records = [record for record in price_records if record['timestamp'].startswith(today_str)]

    # 检查并延续 last_sent 时间
    if price_records and 'last_sent' in price_records[-1]:
        last_sent_time = datetime.strptime(price_records[-1]['last_sent'], '%Y-%m-%d %H:%M:%S')
        if (datetime.now() - last_sent_time).days < 7:
            lowest_price_info['last_sent'] = price_records[-1]['last_sent']

    if today_records:
        current_lowest_today = min(today_records, key=lambda x: x['price'])
        if lowest_price_info['price'] < current_lowest_today['price']:
            price_records = [record for record in price_records if not record['timestamp'].startswith(today_str)]
            price_records.append(lowest_price_info)
            logging.info("更新当天最低价格记录\n\n")
        else:
            logging.info("当前价格高于或等于今天的最低价格，不更新记录\n\n")
            return
    else:
        price_records.append(lowest_price_info)

    with open(data_file, 'w') as file:
        json.dump(price_records, file, indent=4)
        logging.info("*** 成功更新fuel_prices.json ***")

    # 检查是否有足够的数据进行价格变动计算
    check_price_change(price_records, lowest_price_info)

    # 检查是否需要发送可视化图表邮件
    check_and_send_visualization(price_records, record_data)


def check_price_change(price_records, current_record):
    logging.info("开始检查价格变动...")
    if not price_records or (
            datetime.now() - datetime.strptime(price_records[0]['timestamp'], '%Y-%m-%d %H:%M:%S')).days < 10:
        logging.info("数据不足，未达到10天记录。")
        return

    now = datetime.now()
    ninety_days_ago = now - timedelta(days=90)

    # 过去90天的价格
    recent_90_days_prices = [
        record['price'] for record in price_records
        if datetime.strptime(record['timestamp'], '%Y-%m-%d %H:%M:%S') > ninety_days_ago
    ]

    if recent_90_days_prices:
        highest_price_90_days = max(recent_90_days_prices)
        current_price = current_record['price']

        logging.info(f"当前价格: {current_price}")

        # 条件1: 价格相对于90天内的最高价下跌了10%
        condition1 = (highest_price_90_days - current_price) / highest_price_90_days >= 0.10
        logging.info(f"条件1（90天内最高价下跌10%）: {condition1}, 90天最高价格: {highest_price_90_days}")

        # 条件2: 当前价格低于移动平均线的5%
        window_size = min(240, len(recent_90_days_prices))
        moving_average = calculate_moving_average(recent_90_days_prices, window_size)

        # 计算警报线
        alert_line = [round(ma * 0.95, 2) for ma in moving_average]  # 95% 的警报线

        # 检查条件2
        condition2 = current_price < alert_line[-1]
        logging.info(f"并且 条件2（低于30天均线的5%）: {condition2}, 30天移动平均的95%警报线: {alert_line[-1]}")

        # 条件3: 当前价格低于140
        condition3 = current_price < 140
        logging.info(f"或 条件3（低于140）: {condition3}")

        # 判断是否满足发送警报的条件
        if (condition1 and condition2) or condition3:
            # 检查是否已发送警报
            if not alert_sent['timestamp'] or datetime.strptime(alert_sent['timestamp'],
                                                                '%Y-%m-%d %H:%M:%S').date() != datetime.now().date():
                if not alert_sent['price'] or (alert_sent['price'] - current_price) / alert_sent['price'] >= 0.01:
                    alert_sent['price'] = current_price
                    price_change_percentage = -round(
                        ((highest_price_90_days - current_price) / highest_price_90_days) * 100, 2)
                    logging.info(f"当前价格相比过去90天最高点的变化百分比: {price_change_percentage}%")
                    alert_sent['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')  # 更新警报发送时间
                    send_email(current_record, highest_price_90_days, price_change_percentage, alert_line[-1])
                else:
                    logging.info("价格变动不足1%，不发送警报邮件。")
            else:
                logging.info("今天已经发送过警报邮件，不再发送。")
        else:
            logging.info("条件未满足，不发送警报。")
    else:
        logging.info("最近90天内没有足够的价格数据。")


def send_email(current_record, highest_price_90_days, price_change_percentage, moving_average_30_days):
    get_recipient_mails()
    gmail_user = mail
    gmail_password = mail_password
    for recipient_mail in recipient_mails:
        # 创建HTML格式的邮件
        msg = MIMEMultipart('related')
        msg['Subject'] = '⚠️ 油价降低提醒 - 现在是加油的好时机!'
        msg['From'] = gmail_user
        msg['To'] = recipient_mail

        # 创建HTML邮件正文
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M')
        
        html_content = f"""
        <!DOCTYPE html>
        <html lang="zh">
        <head>
            <meta charset="UTF-8">
            <style>
                body {{
                    font-family: 'Arial', sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 0;
                }}
                .container {{
                    background-color: #f9f9f9;
                    border-radius: 8px;
                    overflow: hidden;
                    box-shadow: 0 3px 10px rgba(0, 0, 0, 0.1);
                }}
                .header {{
                    background-color: #FF5722;
                    color: white;
                    padding: 20px;
                    text-align: center;
                }}
                .price-alert {{
                    background-color: #4CAF50;
                    color: white;
                    padding: 15px;
                    text-align: center;
                    font-size: 24px;
                    font-weight: bold;
                }}
                .content {{
                    padding: 20px;
                }}
                .station-info {{
                    background-color: white;
                    border-radius: 5px;
                    padding: 15px;
                    margin-bottom: 20px;
                    border-left: 4px solid #2196F3;
                }}
                .price-info {{
                    display: flex;
                    justify-content: space-between;
                    flex-wrap: wrap;
                    margin-bottom: 20px;
                }}
                .price-card {{
                    background-color: white;
                    border-radius: 5px;
                    padding: 15px;
                    margin-bottom: 10px;
                    width: 48%;
                    box-sizing: border-box;
                    box-shadow: 0 2px 5px rgba(0,0,0,0.05);
                }}
                .price-card h3 {{
                    margin-top: 0;
                    color: #555;
                    font-size: 14px;
                }}
                .price-value {{
                    font-size: 24px;
                    font-weight: bold;
                    color: #2196F3;
                }}
                .decrease {{
                    color: #4CAF50;
                }}
                .action-btn {{
                    display: block;
                    background-color: #2196F3;
                    color: white;
                    text-align: center;
                    padding: 12px;
                    text-decoration: none;
                    border-radius: 5px;
                    font-weight: bold;
                    margin: 20px 0;
                }}
                .footer {{
                    background-color: #eee;
                    padding: 15px;
                    text-align: center;
                    font-size: 12px;
                    color: #777;
                }}
                @media (max-width: 480px) {{
                    .price-card {{
                        width: 100%;
                    }}
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>油价降低提醒</h1>
                    <p>{current_time}</p>
                </div>
                
                <div class="price-alert">
                    现在是加油的好时机!
                </div>
                
                <div class="content">
                    <div class="station-info">
                        <h2>{current_record['name']}</h2>
                        <p>
                            地点：{current_record['suburb']}, {current_record['state']}, {current_record['postcode']}<br>
                            时间：{current_record['timestamp']}
                        </p>
                    </div>
                    
                    <div class="price-info">
                        <div class="price-card">
                            <h3>当前价格</h3>
                            <div class="price-value">{current_record['price']}¢/L</div>
                        </div>
                        
                        <div class="price-card">
                            <h3>90天最高价</h3>
                            <div class="price-value">{highest_price_90_days}¢/L</div>
                        </div>
                        
                        <div class="price-card">
                            <h3>价格降低比例</h3>
                            <div class="price-value decrease">{price_change_percentage:.2f}%</div>
                        </div>
                        
                        <div class="price-card">
                            <h3>警报触发价格</h3>
                            <div class="price-value">{moving_average_30_days:.2f}¢/L</div>
                        </div>
                    </div>
                    
                    <p>系统检测到当前油价已降至警报线以下，现在是加油的好时机！</p>
                    
                    <a href="http://nullpointers.site:6789" class="action-btn">查看详细油价走势</a>
                </div>
                
                <div class="footer">
                    <p>此邮件由系统自动发送，请勿回复。如需取消订阅，请访问<a href="http://nullpointers.site:6789">我们的网站</a>。</p>
                    <p>&copy; 2025 油价监控中心</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # 添加HTML内容
        html_part = MIMEText(html_content, 'html')
        msg.attach(html_part)

        try:
            server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
            server.ehlo()
            server.login(gmail_user, gmail_password)
            server.sendmail(gmail_user, recipient_mail, msg.as_string())
            server.close()
            logging.warning(f"邮件发送成功到: {recipient_mail}")
        except Exception as e:
            logging.warning(f'邮件发送失败到: {recipient_mail} 错误: {e}')


def check_and_send_visualization(price_records, record_data):
    logging.info("检查是否需要发送可视化图表邮件...")
    if not price_records:
        logging.info("没有找到价格记录，不发送邮件")
        return

    # 检查最近一次发送的时间戳
    last_record = price_records[-1]
    last_sent_timestamp = last_record.get('last_sent')

    now = datetime.now()
    if not last_sent_timestamp or (now - datetime.strptime(last_sent_timestamp, '%Y-%m-%d %H:%M:%S')).days >= 7:
        # 生成并发送图表邮件
        send_visualization_email(record_data)
        # 更新发送时间戳
        last_record['last_sent'] = now.strftime('%Y-%m-%d %H:%M:%S')
        with open(data_file, 'w') as file:
            json.dump(price_records, file, indent=4)


def send_visualization_email(record_data):
    get_recipient_mails()
    recent_90_days_records = [
        record for record in record_data
        if datetime.strptime(record['timestamp'], '%Y-%m-%d %H:%M:%S') > (datetime.now() - timedelta(days=90))
    ]

    if not recent_90_days_records:
        logging.info("最近90天内没有足够的数据，不生成图表")
        return

    dates = [datetime.strptime(record['timestamp'], '%Y-%m-%d %H:%M:%S') for record in recent_90_days_records]
    prices = [record['price'] for record in recent_90_days_records]

    highest_price_90_days = max(prices)
    highest_date_90_days = dates[prices.index(highest_price_90_days)]
    
    lowest_price_90_days = min(prices)
    lowest_date_90_days = dates[prices.index(lowest_price_90_days)]

    # 计算移动平均线
    window_size = min(240, len(prices))
    moving_average = calculate_moving_average(prices, window_size)

    # 计算警报线
    alert_line = [round(ma * 0.95, 2) for ma in moving_average]

    # 设置现代风格
    plt.style.use('ggplot')
    fig, ax = plt.subplots(figsize=(22, 11), dpi=100)
    
    # 自定义颜色
    main_color = '#2196F3'  # 蓝色
    alert_color = '#FF5722'  # 橙色
    high_color = '#E91E63'   # 粉色
    low_color = '#4CAF50'    # 绿色
    grid_color = '#EEEEEE'   # 浅灰色
    
    # 设置背景色
    fig.patch.set_facecolor('#FFFFFF')
    ax.set_facecolor('#FCFCFC')
    
    # 绘制价格线
    ax.plot(dates, prices, marker='o', markersize=4, linestyle='-', linewidth=2, 
            color=main_color, label='QLD - U91 价格')
    
    # 绘制警报线
    ax.plot(dates, alert_line, linestyle='--', linewidth=1.5, 
            color=alert_color, alpha=0.8, label='警报线 (30天均线的95%)')
    
    # 标注90天内最高价格
    ax.axhline(highest_price_90_days, color=high_color, linestyle=':', linewidth=1, alpha=0.7, label='90天最高价')
    ax.scatter([highest_date_90_days], [highest_price_90_days], color=high_color, s=100, zorder=5)
    ax.annotate(f'最高价: {highest_price_90_days}¢', 
                xy=(highest_date_90_days, highest_price_90_days),
                xytext=(10, 15), textcoords='offset points',
                fontsize=12, fontweight='bold',
                color=high_color,
                bbox=dict(boxstyle='round,pad=0.3', fc='white', ec=high_color, alpha=0.7))
    
    # 标注90天内最低价格
    ax.scatter([lowest_date_90_days], [lowest_price_90_days], color=low_color, s=100, zorder=5)
    ax.annotate(f'最低价: {lowest_price_90_days}¢', 
                xy=(lowest_date_90_days, lowest_price_90_days),
                xytext=(10, -25), textcoords='offset points',
                fontsize=12, fontweight='bold',
                color=low_color,
                bbox=dict(boxstyle='round,pad=0.3', fc='white', ec=low_color, alpha=0.7))
    
    # 设置轴标签和标题
    ax.set_xlabel('日期', fontsize=14, fontweight='bold')
    ax.set_ylabel('价格 (¢/L)', fontsize=14, fontweight='bold')
    ax.set_title('昆士兰州U91油价走势图 (含90天最高价和30天均线)', fontsize=18, fontweight='bold', pad=20)
    
    # 设置图例
    ax.legend(loc='upper right', frameon=True, fancybox=True, shadow=True, fontsize=12)
    
    # 设置网格
    ax.grid(True, linestyle='--', alpha=0.7, color=grid_color)
    
    # 定制边框
    for spine in ax.spines.values():
        spine.set_visible(False)
    
    # 设置日期格式
    ax.xaxis.set_major_locator(AutoDateLocator())
    ax.xaxis.set_major_formatter(DateFormatter('%m-%d'))
    plt.xticks(rotation=30, fontsize=10)
    
    # 设置Y轴刻度
    y_min = max(0, min(prices) * 0.95) 
    y_max = max(prices) * 1.05
    ax.set_ylim(y_min, y_max)
    
    # 添加当前价格标注
    current_price = prices[-1]
    current_date = dates[-1]
    ax.annotate(f'当前价格: {current_price}¢', 
                xy=(current_date, current_price),
                xytext=(30, 0), textcoords='offset points',
                fontsize=14, fontweight='bold',
                arrowprops=dict(arrowstyle='->', color=main_color, lw=2),
                bbox=dict(boxstyle='round,pad=0.4', fc='white', ec=main_color, alpha=0.9))
    
    plt.tight_layout()

    # 保存图表到文件
    chart_file = 'static/fuel_prices_chart.png'
    plt.savefig(chart_file, bbox_inches='tight', facecolor=fig.get_facecolor())
    plt.close()

    # 发送邮件
    gmail_user = mail
    gmail_password = mail_password

    # 创建邮件
    for recipient_mail in recipient_mails:
        # 创建邮件
        msg = MIMEMultipart('related')
        msg['Subject'] = '油价周报 - 昆士兰州U91最新价格'
        msg['From'] = gmail_user
        msg['To'] = recipient_mail
        
        # 创建HTML邮件正文
        html_content = f"""
        <!DOCTYPE html>
        <html lang="zh">
        <head>
            <meta charset="UTF-8">
            <style>
                body {{
                    font-family: 'Arial', sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 800px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .header {{
                    background-color: #2196F3;
                    color: white;
                    padding: 15px 20px;
                    border-radius: 5px;
                    margin-bottom: 20px;
                    text-align: center;
                }}
                .content {{
                    background-color: #f9f9f9;
                    border-radius: 5px;
                    padding: 20px;
                    margin-bottom: 20px;
                }}
                .data-table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin: 15px 0;
                }}
                .data-table th, .data-table td {{
                    padding: 12px;
                    text-align: left;
                    border-bottom: 1px solid #ddd;
                }}
                .data-table th {{
                    background-color: #f2f2f2;
                }}
                .chart-container {{
                    margin: 20px 0;
                    text-align: center;
                }}
                .footer {{
                    font-size: 12px;
                    text-align: center;
                    color: #777;
                    margin-top: 30px;
                    padding-top: 10px;
                    border-top: 1px solid #eee;
                }}
                .btn {{
                    display: inline-block;
                    background-color: #FF5722;
                    color: white;
                    padding: 10px 15px;
                    text-decoration: none;
                    border-radius: 3px;
                    margin-top: 10px;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>油价周报</h1>
                <p>为您提供最新油价走势和分析</p>
            </div>
            
            <div class="content">
                <h2>昆士兰州U91汽油价格概览</h2>
                
                <table class="data-table">
                    <tr>
                        <th>数据指标</th>
                        <th>价格 (¢/L)</th>
                    </tr>
                    <tr>
                        <td>当前价格</td>
                        <td>{prices[-1]}</td>
                    </tr>
                    <tr>
                        <td>90天最高价</td>
                        <td>{highest_price_90_days}</td>
                    </tr>
                    <tr>
                        <td>90天最低价</td>
                        <td>{lowest_price_90_days}</td>
                    </tr>
                    <tr>
                        <td>警报触发价格 (30天均线的95%)</td>
                        <td>{alert_line[-1]:.2f}</td>
                    </tr>
                    <tr>
                        <td>数据点数量</td>
                        <td>{len(prices)}</td>
                    </tr>
                </table>
                
                <div class="chart-container">
                    <img src="cid:chart" alt="油价走势图" style="max-width:100%;height:auto;">
                </div>
                
                <p>此邮件由系统自动生成并发送，每周更新一次。如果您希望实时获取油价变动信息，请访问我们的网站。</p>
                
                <a href="http://nullpointers.site:6789" class="btn">访问网站</a>
            </div>
            
            <div class="footer">
                <p>如需取消订阅，请访问<a href="http://nullpointers.site:6789">我们的网站</a>并输入您的邮箱地址点击取消订阅。</p>
                <p>&copy; 2025 油价监控中心</p>
            </div>
        </body>
        </html>
        """
        
        # 添加HTML内容
        html_part = MIMEText(html_content, 'html')
        msg.attach(html_part)

        # 添加图表图片
        with open(chart_file, 'rb') as f:
            img_data = f.read()

        image = MIMEImage(img_data)
        image.add_header('Content-ID', '<chart>')
        msg.attach(image)

        try:
            server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
            server.ehlo()
            server.login(gmail_user, gmail_password)
            server.sendmail(gmail_user, recipient_mail, msg.as_string())
            server.close()
            logging.warning(f"图表邮件发送成功到: {recipient_mail}")
        except Exception as e:
            logging.warning(f'图表邮件发送失败到: {recipient_mail} 错误: {e}')


def calculate_moving_average(prices, window_size=240):
    prices_series = pd.Series(prices)
    moving_average = prices_series.rolling(window=window_size, min_periods=1).mean()
    return moving_average.tolist()


def run_scheduler():
    # 设置任务调度
    scheduler.add_job(fetch_and_update_fuel_prices, 'interval', hours=1)

    # 启动调度器
    scheduler.start()


# 创建python服务器
app = Flask(__name__)


@app.route('/', methods=['GET'])
def home():
    return render_template('index.html')


@app.route('/recipient_mails.json', methods=['GET', 'PUT'])
def handle_recipient_mails():
    if request.method == 'GET':
        return send_from_directory('.', 'recipient_mails.json')
    elif request.method == 'PUT':
        with open('recipient_mails.json', 'w') as f:
            json.dump(request.json, f, indent=4)
        return '', 204


@app.route('/fuel_prices.json')
def fuel_prices():
    return send_from_directory(app.root_path, 'fuel_prices.json')


@app.route('/data.json')
def data():
    return send_from_directory(app.root_path, 'data.json')


if __name__ == '__main__':
    scheduler_thread = threading.Thread(target=run_scheduler)
    scheduler_thread.start()

    app.run(host='0.0.0.0', port=6789, debug=False)
