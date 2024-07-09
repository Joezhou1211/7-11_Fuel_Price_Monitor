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
data_file = 'fuel_prices.json'
full_data = 'data.json'

# Email sending information
mail = 'sender mail'
mail_password = 'sender mail password'
recipient_mails = ['receiver mails']  # Add multiple recipient emails here
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
        logging.info("No U91 fuel prices found for QLD region.")
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
        logging.info("fuel_prices.json not found")
        return

    try:
        with open(full_data, 'r') as file:
            record_data = json.load(file)
        logging.info("Successfully read data.json file")
    except FileNotFoundError:
        logging.info("data.json not found")
        return

    record_data.append(lowest_price_info)  # Add latest data
    with open(full_data, 'w') as file:
        json.dump(record_data, file, indent=4)
        logging.info("Successfully updated data.json")

    # Update today's lowest price record
    today_str = datetime.now().strftime('%Y-%m-%d')
    today_records = [record for record in price_records if record['timestamp'].startswith(today_str)]

    # Check and extend last_sent time
    if price_records and 'last_sent' in price_records[-1]:
        last_sent_time = datetime.strptime(price_records[-1]['last_sent'], '%Y-%m-%d %H:%M:%S')
        if (datetime.now() - last_sent_time).days < 7:
            lowest_price_info['last_sent'] = price_records[-1]['last_sent']

    if today_records:
        current_lowest_today = min(today_records, key=lambda x: x['price'])
        if lowest_price_info['price'] < current_lowest_today['price']:
            price_records = [record for record in price_records if not record['timestamp'].startswith(today_str)]
            price_records.append(lowest_price_info)
            logging.info("Updated today's lowest price record")
        else:
            logging.info("Current price is higher than or equal to today's lowest price, not updating record")
            return
    else:
        price_records.append(lowest_price_info)

    with open(data_file, 'w') as file:
        json.dump(price_records, file, indent=4)
        logging.info("Successfully updated fuel_prices.json")

    # Check if there is enough data to calculate price change
    check_price_change(price_records, lowest_price_info)

    # Check if visualization email needs to be sent
    check_and_send_visualization(price_records, record_data)

def check_price_change(price_records, current_record):
    logging.info("Checking for price change...")
    if not any(
            datetime.strptime(record['timestamp'], '%Y-%m-%d %H:%M:%S') < datetime.now() - timedelta(days=30)
            for record in price_records):
        logging.info("Insufficient data, not reaching 30-day record.")
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

        logging.info(f"Current price: {current_price}")

        # Condition 1: Price dropped 10% compared to the highest price in the last 90 days
        condition1 = (highest_price_90_days - current_price) / highest_price_90_days >= 0.10
        logging.info(f"Condition 1 (10% drop from 90-day high): {condition1}, 90-day highest price: {highest_price_90_days}")

        # Condition 2: Current price is below the 5% moving average
        # Calculate moving average
        data_points = len(recent_90_days_prices)
        moving_average = [np.mean(recent_90_days_prices[max(0, i - data_points + 1):i + 1]) for i in range(len(recent_90_days_prices))]

        # Calculate alert line
        alert_line = [round(x * 0.95, 2) for x in moving_average]  # 95%

        condition2 = current_price < alert_line[-1]
        logging.info(f"and Condition 2 (below 30-day MA by 5%): {condition2}, 30-day moving average: {alert_line[-1]}")

        condition3 = current_price < 140
        logging.info(f"or Condition 3 (below 140): {condition3}")

        if (condition1 and condition2) or condition3:
            if not alert_sent['timestamp'] or datetime.strptime(alert_sent['timestamp'],
                                                                '%Y-%m-%d %H:%M:%S').date() != datetime.now().date():
                if not alert_sent['price'] or (alert_sent['price'] - current_price) / alert_sent['price'] >= 0.01:
                    alert_sent['price'] = current_price
                    price_change_percentage = -round(
                        ((highest_price_90_days - current_price) / highest_price_90_days) * 100, 2)
                    logging.info(f"Current price change percentage compared to the highest point in the past 90 days: {price_change_percentage}%")
                    alert_sent['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')  # Update alert sent time
                    sendemail(current_record, highest_price_90_days, price_change_percentage, alert_line[-1])
                else:
                    logging.info("Price change less than 1%, not sending alert email.")
            else:
                logging.info("Alert email already sent today, not sending again.")
        else:
            logging.info("Conditions not met, not sending alert.")
    else:
        logging.info("Insufficient price data in the last 90 days.")

def send_email(current_record, highest_price_90_days, price_change_percentage, moving_average_30_days):
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
            logging.warning(f"Email successfully sent to: {recipient_mail}")
        except Exception as e:
            logging.warning(f'Failed to send email to: {recipient_mail} Error: {e}')

def check_and_send_visualization(price_records, record_data):
    logging.info("Checking if visualization email needs to be sent...")
    if not price_records:
        logging.info("No price records found, not sending email")
        return

    # Check the timestamp of the last sent email
    last_record = price_records[-1]
    last_sent_timestamp = last_record.get('last_sent')

    now = datetime.now()
    if not last_sent_timestamp or (now - datetime.strptime(last_sent_timestamp, '%Y-%m-%d %H:%M:%S')).days >= 7:
        # Generate and send chart email
        send_visualization_email(record_data)
        # Update the sent timestamp
        last_record['last_sent'] = now.strftime('%Y-%m-%d %H:%M:%S')
        with open(data_file, 'w') as file:
            json.dump(price_records, file, indent=4)

def send_visualization_email(record_data):
    now = datetime.now()
    ninety_days_ago = now - timedelta(days=90)
    recent_90_days_records = [
        record for record in record_data
        if datetime.strptime(record['timestamp'], '%Y-%m-%d %H:%M:%S') > ninety_days_ago
    ]

    if not recent_90_days_records:
        logging.info("Not enough data in the last 90 days, no chart generated")
        return

    dates = [datetime.strptime(record['timestamp'], '%Y-%m-%d %H:%M:%S') for record in recent_90_days_records]
    prices = [record['price'] for record in recent_90_days_records]

    highest_price_90_days = max(prices)
    highest_date_90_days = dates[prices.index(highest_price_90_days)]

    # Calculate moving average
    data_points = len(prices)
    moving_average = [np.mean(prices[max(0, i - data_points + 1):i + 1]) for i in range(len(prices))]

    # Calculate alert line
    alert_line = [round(x * 0.95, 2) for x in moving_average]  # 95%

    plt.figure(figsize=(22, 11))
    plt.plot(dates, prices, marker='o', linestyle='-', color='green', label='QLD - U91')
    plt.plot(dates, alert_line, linestyle=':', color='red', label='Alert Line (30 Day MA)')

    # Annotate 90-day highest price
    plt.axhline(highest_price_90_days, color='red', linestyle='--', label='90 Day High')
    plt.annotate('90 Day High', xy=(highest_date_90_days, highest_price_90_days),
                 xytext=(highest_date_90_days, highest_price_90_days + 5),
                 arrowprops=dict(facecolor='red', shrink=0.05))

    plt.xlabel('Date')
    plt.ylabel('Price (cents/L)')
    plt.title('U91 Fuel Prices with 90 Day High and 30 Day MA')
    plt.legend()
    plt.grid(True)

    # Set date format
    ax = plt.gca()
    ax.xaxis.set_major_locator(DayLocator(interval=1))  # Show one date per day
    ax.xaxis.set_major_formatter(DateFormatter('%d %b'))  # Date format like "4 May"
    plt.xticks(rotation=45)

    plt.yticks(np.arange(min(prices), max(prices) + 1, 2.5))

    plt.tight_layout()

    # Save chart to file
    chart_file = 'fuel_prices_chart.png'
    plt.savefig(chart_file)
    plt.close()

    # Send email
    gmail_user = mail
    gmail_password = mail_password

    # Create email
    for recipient_mail in recipient_mails:
        msg = MIMEMultipart()
        msg['Subject'] = '7-11 Weekly U91 Price Chart'
        msg['From'] = gmail_user
        msg['To'] = recipient_mail

        # Email body
        text = MIMEText(
            f"State：QLD\nType：U91\nData Points: {len(prices)}\n"
            f"Current Trigger Price: {alert_line[-1]} cents/L\n90 Days High: {highest_price_90_days} cents/L\n"
        )
        msg.attach(text)

        # Attach chart image
        with open(chart_file, 'rb') as f:
            img_data = f.read()

        image = MIMEImage(img_data, name='fuel_prices_chart.png')
        image.add_header('Content-ID', '<chart>')
        msg.attach(image)

        # Embed image in email body
        html = MIMEText('<br><img src="cid:chart"><br>', 'html')
        msg.attach(html)

        try:
            server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
            server.ehlo()
            server.login(gmail_user, gmail_password)
            server.sendmail(gmail_user, recipient_mail, msg.as_string())
            server.close()
            logging.warning(f"Chart email successfully sent to: {recipient_mail}")
        except Exception as e:
            logging.warning(f'Failed to send chart email to: {recipient_mail} Error: {e}')

# Schedule task
scheduler.add_job(fetch_and_update_fuel_prices, 'interval', hours=1)  # Auto run every 1 hour, or modify to 30 minutes, 30 seconds, etc.

# Start scheduler
scheduler.start()
