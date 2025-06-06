import json
import time
import threading
import requests
import logging
from datetime import datetime, timedelta
import pandas as pd
from flask import Flask, send_from_directory, render_template, request, jsonify
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage

# File paths
DATA_FILE = 'fuel_prices.json'
FULL_DATA_FILE = 'data.json'
RECIPIENT_FILE = 'recipient_mails.json'

# Structure of subscriptions
# {
#   "weekly": ["email@foo"],
#   "alerts": {"email@foo": [{"fuel_type":"U91","method":"moving_average"}]}
# }

CODE_CACHE = {}
SUBSCRIPTIONS = {}

# Mail credentials (update these before running)
MAIL_USER = ''
MAIL_PASS = ''

# Alert state per fuel type
ALERT_STATE = {}

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


def load_json(path, default=None):
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return default if default is not None else []


def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=4)


def load_subscriptions():
    global SUBSCRIPTIONS
    data = load_json(RECIPIENT_FILE, default={"weekly": [], "alerts": {}})
    if isinstance(data, list):
        data = {"weekly": data, "alerts": {}}
        save_json(RECIPIENT_FILE, data)
    SUBSCRIPTIONS = data


def save_subscriptions():
    save_json(RECIPIENT_FILE, SUBSCRIPTIONS)


def send_verification_email(email, code):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = 'Your verification code'
    msg['From'] = MAIL_USER
    msg['To'] = email
    html = (
        f"<div style='font-family:Arial,sans-serif;font-size:16px;'>"
        f"<p>Your verification code is <b style='font-size:24px'>{code}</b></p>"
        f"<p style='color:#555'>This code expires in 1 minute.</p>"
        f"</div>"
    )
    msg.attach(MIMEText(html, 'html'))
    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(MAIL_USER, MAIL_PASS)
        server.sendmail(MAIL_USER, email, msg.as_string())
        server.quit()
        logging.info('Verification code sent to %s', email)
    except Exception as exc:
        logging.warning('Failed to send code to %s: %s', email, exc)


def verify_code(email, code):
    record = CODE_CACHE.get(email)
    if not record:
        return False
    stored, ts = record
    if stored != code:
        return False
    if (datetime.now() - ts).seconds > 60:
        return False
    return True


def add_subscription(email, weekly=False, alerts=None):
    if weekly and email not in SUBSCRIPTIONS['weekly']:
        SUBSCRIPTIONS['weekly'].append(email)
    if alerts:
        SUBSCRIPTIONS.setdefault('alerts', {})
        SUBSCRIPTIONS['alerts'].setdefault(email, [])
        SUBSCRIPTIONS['alerts'][email].extend(alerts)
    save_subscriptions()


def remove_subscription(email):
    if email in SUBSCRIPTIONS.get('weekly', []):
        SUBSCRIPTIONS['weekly'].remove(email)
    if SUBSCRIPTIONS.get('alerts', {}).get(email):
        SUBSCRIPTIONS['alerts'].pop(email)
    save_subscriptions()


def fetch_fuel_prices():
    """Fetch raw data from the public API."""
    url = 'https://projectzerothree.info/api.php?format=json'
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.json()


def parse_lowest_prices(data):
    """Return the lowest price record for each fuel type in QLD."""
    qld_region = next((r for r in data.get('regions', []) if r['region'] == 'QLD'), None)
    if not qld_region:
        return {}

    lowest = {}
    for item in qld_region.get('prices', []):
        f_type = item['type']
        if f_type not in lowest or item['price'] < lowest[f_type]['price']:
            lowest[f_type] = item

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    for info in lowest.values():
        info['timestamp'] = timestamp
    return lowest


def update_records(lowest_prices):
    """Update local JSON files and return records that changed."""
    if not lowest_prices:
        return []

    changed = []
    full_records = load_json(FULL_DATA_FILE)
    day_records = load_json(DATA_FILE)
    today = datetime.now().strftime('%Y-%m-%d')

    for fuel_type, info in lowest_prices.items():
        full_records.append(info)
        current_day = [r for r in day_records if r['type'] == fuel_type and r['timestamp'].startswith(today)]
        if not current_day or info['price'] < min(current_day, key=lambda x: x['price'])['price']:
            day_records = [r for r in day_records if not (r['type'] == fuel_type and r['timestamp'].startswith(today))]
            day_records.append(info)
            changed.append(info)

    save_json(FULL_DATA_FILE, full_records)
    if changed:
        save_json(DATA_FILE, day_records)
    return changed


def evaluate_alert(records, current_record, method, threshold=None, ma_window=None):
    """Evaluate if an alert should trigger based on method."""
    if len(records) < 10:
        return False, {}

    now = datetime.now()
    ninety_days_ago = now - timedelta(days=90)
    recent_prices = [
        r['price'] for r in records
        if datetime.strptime(r['timestamp'], '%Y-%m-%d %H:%M:%S') > ninety_days_ago
    ]
    if not recent_prices:
        return False, {}

    price = current_record['price']
    highest = max(recent_prices)
    info = {'highest': highest}

    if method == 'moving_average':
        window = ma_window or 240
        window = min(window, len(recent_prices))
        ma = pd.Series(recent_prices).rolling(window=window, min_periods=1).mean().iloc[-1]
        alert_line = ma * 0.95
        triggered = price < alert_line and (highest - price) / highest >= 0.10
        info.update({'alert_line': alert_line, 'change_pct': -round((highest - price) / highest * 100, 2)})
    elif method == 'lowest':
        lowest = min(recent_prices)
        triggered = price <= lowest
        info.update({'lowest': lowest})
    elif method == 'fixed':
        if threshold is None:
            threshold = 140
        triggered = price < threshold
        info.update({'threshold': threshold})
    else:
        triggered = False

    return triggered, info


def send_alert_email(record, info, receivers):
    """Send the alert email for the given record to receivers."""
    subject = f'⚠️ {record["type"]} price alert'
    for receiver in receivers:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = MAIL_USER
        msg['To'] = receiver

        body = (
            f"Station: {record['name']}\n"
            f"Location: {record['suburb']}, {record['state']} {record['postcode']}\n"
            f"Price: {record['price']}¢/L\n"
            f"Timestamp: {record['timestamp']}\n\n"
            f"90 Day High: {info['highest']}¢/L\n"
            f"Change: {info['change_pct']}%\n"
            f"Alert Line: {info['alert_line']:.2f}¢/L"
        )
        msg.attach(MIMEText(body))
        try:
            server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
            server.login(MAIL_USER, MAIL_PASS)
            server.sendmail(MAIL_USER, receiver, msg.as_string())
            server.quit()
            logging.info('Alert email sent to %s', receiver)
        except Exception as exc:
            logging.warning('Failed to send alert email to %s: %s', receiver, exc)


def send_weekly_report(records, fuel_type):
    """Send weekly chart email."""
    if not records:
        return
    now = datetime.now()
    ninety_days_ago = now - timedelta(days=90)
    recent = [r for r in records if datetime.strptime(r['timestamp'], '%Y-%m-%d %H:%M:%S') > ninety_days_ago]
    if not recent:
        return

    dates = [datetime.strptime(r['timestamp'], '%Y-%m-%d %H:%M:%S') for r in recent]
    prices = [r['price'] for r in recent]
    highest = max(prices)
    window = min(240, len(prices))
    moving_avg = pd.Series(prices).rolling(window=window, min_periods=1).mean()
    alert_line = moving_avg * 0.95

    import matplotlib.pyplot as plt
    plt.style.use('ggplot')
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(dates, prices, label=fuel_type)
    ax.plot(dates, alert_line, label='alert line')
    ax.axhline(highest, color='r', linestyle='--', label='90 day high')
    ax.legend()
    fig.autofmt_xdate()
    chart_path = 'weekly_chart.png'
    plt.savefig(chart_path)
    plt.close(fig)

    receivers = SUBSCRIPTIONS.get('weekly', [])
    for receiver in receivers:
        msg = MIMEMultipart('related')
        msg['Subject'] = f'{fuel_type} Weekly Price Chart'
        msg['From'] = MAIL_USER
        msg['To'] = receiver
        html = (
            f"<h2>{fuel_type} Weekly Price Chart</h2>"
            f"<p>Total points: {len(prices)}</p>"
            f"<img src='cid:chart' style='max-width:100%;'>"
        )
        msg.attach(MIMEText(html, 'html'))
        with open(chart_path, 'rb') as f:
            img = MIMEImage(f.read())
            img.add_header('Content-ID', '<chart>')
            msg.attach(img)
        try:
            server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
            server.login(MAIL_USER, MAIL_PASS)
            server.sendmail(MAIL_USER, receiver, msg.as_string())
            server.quit()
            logging.info('Weekly report sent to %s', receiver)
        except Exception as exc:
            logging.warning('Failed to send weekly report to %s: %s', receiver, exc)


# --- loops ---

def data_loop():
    while True:
        try:
            raw = fetch_fuel_prices()
            lowest = parse_lowest_prices(raw)
            changed = update_records(lowest)
            for rec in changed:
                ALERT_QUEUE.append(rec)
        except Exception as exc:
            logging.error('Data loop error: %s', exc)
        time.sleep(3600)


def alert_loop():
    while True:
        if ALERT_QUEUE:
            record = ALERT_QUEUE.pop(0)
            all_records = [r for r in load_json(DATA_FILE) if r['type'] == record['type']]
            alerts = SUBSCRIPTIONS.get('alerts', {})
            for email, configs in alerts.items():
                for cfg in configs:
                    if cfg.get('fuel_type') != record['type']:
                        continue
                    triggered, info = evaluate_alert(
                        all_records,
                        record,
                        cfg.get('method'),
                        cfg.get('threshold'),
                        cfg.get('ma_window')
                    )
                    if triggered:
                        state = ALERT_STATE.get(email)
                        today = datetime.now().date()
                        if not state or datetime.strptime(state['timestamp'], '%Y-%m-%d %H:%M:%S').date() != today:
                            send_alert_email(record, info, [email])
                            ALERT_STATE[email] = {
                                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                'price': record['price']
                            }
        time.sleep(10)


def weekly_loop():
    while True:
        records = load_json(DATA_FILE)
        types = {r['type'] for r in records}
        for f_type in types:
            type_records = [r for r in records if r['type'] == f_type]
            last_sent = max((datetime.strptime(r.get('last_sent'), '%Y-%m-%d %H:%M:%S')
                              for r in type_records if r.get('last_sent')), default=None)
            if not last_sent or (datetime.now() - last_sent).days >= 7:
                send_weekly_report(type_records, f_type)
                if type_records:
                    type_records[-1]['last_sent'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        save_json(DATA_FILE, records)
        time.sleep(86400)


# --- Flask UI ---
app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/subscribe')
def subscribe_page():
    return render_template('subscribe.html')

@app.route('/unsubscribe')
def unsubscribe_page():
    return render_template('unsubscribe.html')

@app.route('/fuel_prices.json')
def serve_day():
    return send_from_directory('.', DATA_FILE)

@app.route('/data.json')
def serve_full():
    return send_from_directory('.', FULL_DATA_FILE)


@app.route('/send_code', methods=['POST'])
def api_send_code():
    email = request.json.get('email')
    if not email:
        return jsonify({'error': 'email required'}), 400
    record = CODE_CACHE.get(email)
    if record and (datetime.now() - record[1]).seconds < 60:
        return jsonify({'error': 'too many requests'}), 429
    code = '{:06d}'.format(int(time.time()*1000) % 1000000)
    CODE_CACHE[email] = (code, datetime.now())
    send_verification_email(email, code)
    return '', 204


@app.route('/subscribe', methods=['POST'])
def api_subscribe():
    data = request.json
    email = data.get('email')
    code = data.get('code')
    if not verify_code(email, code):
        return jsonify({'error': 'invalid code'}), 400
    weekly = data.get('weekly', False)
    alerts = data.get('alerts', [])
    add_subscription(email, weekly, alerts)
    return '', 204


@app.route('/unsubscribe', methods=['POST'])
def api_unsubscribe():
    data = request.json
    email = data.get('email')
    code = data.get('code')
    if not verify_code(email, code):
        return jsonify({'error': 'invalid code'}), 400
    remove_subscription(email)
    return '', 204


# shared queue for alerts
ALERT_QUEUE = []


def main():
    load_subscriptions()
    threads = [
        threading.Thread(target=data_loop, daemon=True),
        threading.Thread(target=alert_loop, daemon=True),
        threading.Thread(target=weekly_loop, daemon=True),
        threading.Thread(target=lambda: app.run(host='0.0.0.0', port=6789, debug=False), daemon=True)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


if __name__ == '__main__':
    main()

