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

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Define file paths
data_file = 'fuel_prices.json'  # Record Lowest Fule Prices of The Day
full_data = 'data.json'  # Record All Data Points

# Email sending information
mail = 'sender email'
mail_password = 'sender email password'
recipient_mails = ['receiver emails']  # Add multiple recipient emails here
alert_sent = {'timestamp': '2024-06-17 04:00:59', 'price': 0}

# Initialize scheduler
scheduler = BlockingScheduler()

def fetch_and_update_fuel_prices():
    logging.info("Starting to fetch and update fuel prices...")
    url = 'https://projectzerothree.info/api.php?format=json'
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        logging.info("Successfully fetched API data")
    except requests.RequestException as e:
        logging.error(f"API request failed: {e}")
        return

    qld_u91_prices = []

    for region in data['regions']:
        if region['region'] == 'QLD':
            for price_info in region['prices']:
                if price_info['type'] == 'U91':
                    qld_u91_prices.append(price_info)

    if not qld_u91_prices:
        logging.info("No U91 gasoline prices found for QLD region.")
        return

    qld_u91_prices_sorted = sorted(qld_u91_prices, key=lambda x: x['price'])
    lowest_price_info = qld_u91_prices_sorted[0]
    lowest_price_info['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    logging.info(f"Lowest price info: {lowest_price_info}")

    try:
        with open(data_file, 'r') as file:
            price_records = json.load(file)
        logging.info("Successfully read fuel_prices.json file")
    except FileNotFoundError:
        price_records = []
        logging.info("fuel_prices.json file not found, creating a new one")

    price_records.append(lowest_price_info)

    with open(data_file, 'w') as file:
        json.dump(price_records, file)
        logging.info("Successfully updated fuel_prices.json file")

    if len(price_records) > 90:
        price_records = price_records[-90:]

    prices = [record['price'] for record in price_records]
    dates = [datetime.strptime(record['timestamp'], '%Y-%m-%d %H:%M:%S') for record in price_records]
    
    highest_price_90_days = max(prices)
    logging.info(f"Highest price in the last 90 days: {highest_price_90_days}")

    if prices[-1] > alert_sent['price'] * 1.05:
        alert_sent['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        alert_sent['price'] = prices[-1]
        send_alert_email(prices[-1], dates[-1])
        logging.warning("Price alert email sent!")

    plot_fuel_prices_chart(dates, prices, highest_price_90_days)

def send_alert_email(price, date):
    gmail_user = mail
    gmail_password = mail_password

    for recipient_mail in recipient_mails:
        msg = MIMEMultipart()
        msg['Subject'] = 'Fuel Price Alert'
        msg['From'] = gmail_user
        msg['To'] = recipient_mail

        text = MIMEText(f"Fuel price alert!\nDate: {date}\nPrice: {price} cents/L")
        msg.attach(text)

        try:
            server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
            server.ehlo()
            server.login(gmail_user, gmail_password)
            server.sendmail(gmail_user, recipient_mail, msg.as_string())
            server.close()
            logging.warning(f"Alert email sent successfully to: {recipient_mail}")
        except Exception as e:
            logging.warning(f"Failed to send alert email to: {recipient_mail}. Error: {e}")

def plot_fuel_prices_chart(dates, prices, highest_price_90_days):
    plt.figure(figsize=(10, 6))
    plt.plot(dates, prices, label='U91 Prices')
    plt.axhline(y=highest_price_90_days, color='r', linestyle='--', label='90 Day High')
    plt.title('Fuel Prices - U91')
    plt.xlabel('Date')
    plt.ylabel('Price (cents/L)')
    plt.legend()
    plt.grid(True)

    ax = plt.gca()
    ax.xaxis.set_major_locator(DayLocator(interval=1))
    ax.xaxis.set_major_formatter(DateFormatter('%d %b'))
    plt.xticks(rotation=45)
    plt.yticks(np.arange(min(prices), max(prices) + 1, 2.5))

    plt.tight_layout()

    chart_file = 'fuel_prices_chart.png'
    plt.savefig(chart_file)
    plt.close()

    send_chart_email(chart_file, prices, highest_price_90_days)

def send_chart_email(chart_file, prices, highest_price_90_days):
    gmail_user = mail
    gmail_password = mail_password

    for recipient_mail in recipient_mails:
        msg = MIMEMultipart()
        msg['Subject'] = '7-11 Weekly U91 Price Chart'
        msg['From'] = gmail_user
        msg['To'] = recipient_mail

        text = MIMEText(
            f"State: QLD\nType: U91\nData Points: {len(prices)}\n"
            f"Current Trigger Price: {prices[-1]} cents/L\n90 Days High: {highest_price_90_days} cents/L\n"
        )
        msg.attach(text)

        with open(chart_file, 'rb') as f:
            img_data = f.read()

        image = MIMEImage(img_data, name='fuel_prices_chart.png')
        image.add_header('Content-ID', '<chart>')
        msg.attach(image)

        html = MIMEText('<br><img src="cid:chart"><br>', 'html')
        msg.attach(html)

        try:
            server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
            server.ehlo()
            server.login(gmail_user, gmail_password)
            server.sendmail(gmail_user, recipient_mail, msg.as_string())
            server.close()
            logging.warning(f"Chart email sent successfully to: {recipient_mail}")
        except Exception as e:
            logging.warning(f"Failed to send chart email to: {recipient_mail}. Error: {e}")

# Schedule tasks
scheduler.add_job(fetch_and_update_fuel_prices, 'interval', hours=1)

# Start the scheduler
scheduler.start()
