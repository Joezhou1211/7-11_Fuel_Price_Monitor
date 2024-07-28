import requests
import json
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from datetime import datetime, timedelta
from apscheduler.schedulers.blocking import BlockingScheduler
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter, DayLocator
from flask import Flask, render_template, request, send_from_directory
import threading

# 配置日志记录
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 定义保存文件路径
data_file = 'fuel_prices.json'
full_data = 'data.json'


def get_recipient_mails():
    global recipient_mails
    with open("recipient_mails.json", 'r') as file:
        recipient_mails = json.load(file)


# 邮件发送相关信息
mail = 'your_sender_email'
mail_password = 'your_password'
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

    logging.info(f"最低价格信息: {lowest_price_info}")

    try:
        with open(data_file, 'r') as file:
            price_records = json.load(file)
        logging.info("成功读取fuel_prices.json文件")
    except FileNotFoundError:
        logging.info("没有找到fuel_prices.json")
        return

    try:
        with open(full_data, 'r') as file:
            record_data = json.load(file)
        logging.info("成功读取data.json文件")
    except FileNotFoundError:
        logging.info("没有找到data.json")
        return

    record_data.append(lowest_price_info)  # 添加最新数据
    with open(full_data, 'w') as file:
        json.dump(record_data, file, indent=4)
        logging.info("成功更新data.json")

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
            logging.info("更新当天最低价格记录")
        else:
            logging.info("当前价格高于或等于今天的最低价格，不更新记录")
            return
    else:
        price_records.append(lowest_price_info)

    with open(data_file, 'w') as file:
        json.dump(price_records, file, indent=4)
        logging.info("成功更新fuel_prices.json")

    # 检查是否有足够的数据进行价格变动计算
    check_price_change(price_records, lowest_price_info)

    # 检查是否需要发送可视化图表邮件
    check_and_send_visualization(price_records, record_data)


def check_price_change(price_records, current_record):
    logging.info("开始检查价格变动...")
    if not any(
            datetime.strptime(record['timestamp'], '%Y-%m-%d %H:%M:%S') < datetime.now() - timedelta(days=30)
            for record in price_records):
        logging.info("数据不足，未达到30天记录。")
        return

    now = datetime.now()
    ninety_days_ago = now - timedelta(days=90)

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

        # 条件2: 当前价格低于均线的5%
        # 计算移动平均线
        data_points = len(recent_90_days_prices)
        moving_average = [np.mean(recent_90_days_prices[max(0, i - data_points + 1):i + 1]) for i in
                          range(len(recent_90_days_prices))]

        # 计算警报线
        alert_line = [round(x * 0.95, 2) for x in moving_average]  # 95%

        condition2 = current_price < alert_line[-1]
        logging.info(f"并且 条件2（低于30天均线的5%）: {condition2}, 30天移动平均: {alert_line[-1]}")

        condition3 = current_price < 140
        logging.info(f"或 条件3（低于140）: {condition3}")

        if (condition1 and condition2) or condition3:
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
        msg = MIMEText(
            f"Current Fuel Price and Location:\n"
            f"Station: {current_record['name']}\n"
            f"Location: {current_record['suburb']}, {current_record['state']}, {current_record['postcode']}\n"
            f"Price: {current_record['price']} cents/L\n"
            f"Timestamp: {current_record['timestamp']}\n\n"
            f"90-Day High Price: {highest_price_90_days} cents/L\n"
            f"Price Compared to 90-Day High: {price_change_percentage:.2f}%\n"
            f"Alert Trigger Price (MA30): {moving_average_30_days:.2f} cents/L\n"
        )
        msg['Subject'] = 'Low Fuel Price Alert!'
        msg['From'] = gmail_user
        msg['To'] = recipient_mail

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
    now = datetime.now()
    ninety_days_ago = now - timedelta(days=90)
    recent_90_days_records = [
        record for record in record_data
        if datetime.strptime(record['timestamp'], '%Y-%m-%d %H:%M:%S') > ninety_days_ago
    ]

    if not recent_90_days_records:
        logging.info("最近90天内没有足够的数据，不生成图表")
        return

    dates = [datetime.strptime(record['timestamp'], '%Y-%m-%d %H:%M:%S') for record in recent_90_days_records]
    prices = [record['price'] for record in recent_90_days_records]

    highest_price_90_days = max(prices)
    highest_date_90_days = dates[prices.index(highest_price_90_days)]

    # 计算移动平均线
    data_points = len(prices)
    moving_average = [np.mean(prices[max(0, i - data_points + 1):i + 1]) for i in range(len(prices))]

    # 计算警报线
    alert_line = [round(x * 0.95, 2) for x in moving_average]  # 95%

    plt.figure(figsize=(22, 11))
    plt.plot(dates, prices, marker='.', linestyle='-', color='green', label='QLD - U91')
    plt.plot(dates, alert_line, linestyle=':', color='red', label='Alert Line (30 Day MA)')

    # 标注90天内最高价格
    plt.axhline(highest_price_90_days, color='red', linestyle='--', label='90 Day High')
    plt.annotate('90 Day High', xy=(highest_date_90_days, highest_price_90_days),
                 xytext=(highest_date_90_days, highest_price_90_days + 5),
                 arrowprops=dict(facecolor='red', shrink=0.05))

    plt.xlabel('Date')
    plt.ylabel('Price (cents/L)')
    plt.title('U91 Fuel Prices with 90 Day High and 30 Day MA')
    plt.legend()
    plt.grid(True)

    # 设置日期格式
    ax = plt.gca()
    ax.xaxis.set_major_locator(DayLocator(interval=1))  # 每天显示一个日期
    ax.xaxis.set_major_formatter(DateFormatter('%d %b'))  # 日期格式如 "4 May"
    plt.xticks(rotation=45)

    plt.yticks(np.arange(min(prices), max(prices) + 1, 2.5))

    plt.tight_layout()

    # 保存图表到文件
    chart_file = 'static/fuel_prices_chart.png'
    plt.savefig(chart_file)
    plt.close()

    # 发送邮件
    gmail_user = mail
    gmail_password = mail_password

    # 创建邮件
    for recipient_mail in recipient_mails:
        # 创建邮件
        msg = MIMEMultipart()
        msg['Subject'] = '7-11 Weekly U91 Price Chart'
        msg['From'] = gmail_user
        msg['To'] = recipient_mail

        # 邮件正文
        text = MIMEText(
            f"State：QLD\nType：U91\nData Points: {len(prices)}\n"
            f"Trigger: {alert_line[-1]} cents/L\n90 Days High: {highest_price_90_days} cents/L\n"
            f"Current Price: {prices[-1]} cents/L"
            f"To unsubscribe, please click the following link:\n"
            f"http://20.169.240.82:7001\n"
        )
        msg.attach(text)

        # 添加图表图片
        with open(chart_file, 'rb') as f:
            img_data = f.read()

        image = MIMEImage(img_data, name='static/fuel_prices_chart.png')
        image.add_header('Content-ID', '<chart>')
        msg.attach(image)

        # 将图片嵌入邮件正文
        html = MIMEText('<br><img src="cid:chart"><br>', 'html')
        msg.attach(html)

        try:
            server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
            server.ehlo()
            server.login(gmail_user, gmail_password)
            server.sendmail(gmail_user, recipient_mail, msg.as_string())
            server.close()
            logging.warning(f"图表邮件发送成功到: {recipient_mail}")
        except Exception as e:
            logging.warning(f'图表邮件发送失败到: {recipient_mail} 错误: {e}')


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


if __name__ == '__main__':
    scheduler_thread = threading.Thread(target=run_scheduler)
    scheduler_thread.start()

    app.run(host='0.0.0.0', port=7001, debug=False)
