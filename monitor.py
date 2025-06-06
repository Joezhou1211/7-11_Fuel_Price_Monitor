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


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


def load_json(path, default=None):
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else []


def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=4)


def load_subscriptions():
    global SUBSCRIPTIONS
    data = load_json(RECIPIENT_FILE, default={"weekly": [], "alerts": {}, "info": {}})
    if isinstance(data, list):
        data = {"weekly": data, "alerts": {}, "info": {email: {} for email in data}}
        save_json(RECIPIENT_FILE, data)
    if isinstance(data.get("weekly"), list):
        data["info"] = {email: {} for email in data.get("weekly", [])}
        data["weekly"] = data.get("weekly", [])
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
    if weekly:
        SUBSCRIPTIONS.setdefault('weekly', [])
        if email in SUBSCRIPTIONS['weekly']:
            return False, 'already subscribed to weekly'
        SUBSCRIPTIONS['weekly'].append(email)
    if alerts:
        SUBSCRIPTIONS.setdefault('alerts', {})
        if SUBSCRIPTIONS['alerts'].get(email):
            return False, 'already subscribed to alerts'
        SUBSCRIPTIONS['alerts'][email] = alerts
    SUBSCRIPTIONS.setdefault('info', {})
    SUBSCRIPTIONS['info'].setdefault(email, {})
    save_subscriptions()
    return True, ''


def remove_subscription(email):
    removed = False
    if email in SUBSCRIPTIONS.get('weekly', []):
        SUBSCRIPTIONS['weekly'].remove(email)
        removed = True
    if SUBSCRIPTIONS.get('alerts', {}).pop(email, None) is not None:
        removed = True
    if SUBSCRIPTIONS.get('info', {}).pop(email, None) is not None:
        removed = True
    if removed:
        save_subscriptions()
    return removed


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


def get_latest_prices():
    """Return the latest price record for each fuel type."""
    records = load_json(DATA_FILE)
    latest = {}
    for rec in records:
        ts = datetime.strptime(rec['timestamp'], '%Y-%m-%d %H:%M:%S')
        if rec['type'] not in latest or ts > latest[rec['type']]['ts']:
            latest[rec['type']] = {'price': rec['price'], 'ts': ts}
    return {k: v['price'] for k, v in latest.items()}


def send_weekly_summary(prices, receivers):
    """Send a structured weekly email with current prices."""
    if not prices:
        return
    rows = ''.join(
        f"<tr><td style='padding:8px 12px;border:1px solid #ddd'>{ft}</td>"
        f"<td style='padding:8px 12px;border:1px solid #ddd'>{price}¢/L</td></tr>"
        for ft, price in prices.items()
    )
    html = f"""
<div style='font-family:Arial,sans-serif;font-size:16px;'>
  <h2 style='color:#333;margin-bottom:10px'>Current Fuel Prices</h2>
  <table style='border-collapse:collapse;text-align:left;'>
    <thead>
      <tr style='background:#f4f6f8'>
        <th style='padding:8px 12px;border:1px solid #ddd'>Fuel</th>
        <th style='padding:8px 12px;border:1px solid #ddd'>Price</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
  <p style='margin-top:10px'>Visit <a href='https://nullpointers.site:8083'>dashboard</a> for details.</p>
</div>
"""
    for receiver in receivers:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = '⛽ Weekly Fuel Price Summary'
        msg['From'] = MAIL_USER
        msg['To'] = receiver
        msg.attach(MIMEText(html, 'html'))
        try:
            server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
            server.login(MAIL_USER, MAIL_PASS)
            server.sendmail(MAIL_USER, receiver, msg.as_string())
            server.quit()
            logging.info('Weekly summary sent to %s', receiver)
        except Exception as exc:
            logging.warning('Failed to send weekly summary to %s: %s', receiver, exc)


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
                        info_dict = SUBSCRIPTIONS.setdefault('info', {}).setdefault(email, {})
                        last_str = info_dict.get('trigger_last_sent')
                        last = datetime.strptime(last_str, '%Y-%m-%d %H:%M:%S').date() if last_str else None
                        today = datetime.now().date()
                        if not last or last != today:
                            send_alert_email(record, info, [email])
                            info_dict['trigger_last_sent'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            save_subscriptions()
        time.sleep(10)


def weekly_loop():
    while True:
        prices = get_latest_prices()
        receivers = []
        now = datetime.now()
        info_dict = SUBSCRIPTIONS.setdefault('info', {})
        for email in SUBSCRIPTIONS.get('weekly', []):
            last_str = info_dict.get(email, {}).get('weekly_chart_last_sent')
            last = datetime.strptime(last_str, '%Y-%m-%d %H:%M:%S') if last_str else None
            if not last or (now - last).days >= 7:
                receivers.append(email)
                info_dict.setdefault(email, {})['weekly_chart_last_sent'] = now.strftime('%Y-%m-%d %H:%M:%S')
        if receivers:
            send_weekly_summary(prices, receivers)
            save_subscriptions()
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
    data = request.json
    email = data.get('email')
    action = data.get('action')
    if not email:
        return jsonify({'error': 'email required'}), 400
    record = CODE_CACHE.get(email)
    if record and (datetime.now() - record[1]).seconds < 60:
        return jsonify({'error': 'too many requests'}), 429
    if action == 'unsubscribe' and email not in SUBSCRIPTIONS.get('weekly', []) and email not in SUBSCRIPTIONS.get('alerts', {}):
        return jsonify({'error': 'email not subscribed'}), 404
    if action == 'subscribe' and (email in SUBSCRIPTIONS.get('weekly', []) or email in SUBSCRIPTIONS.get('alerts', {})):
        return jsonify({'error': 'email already subscribed'}), 400


@app.route('/subscribe', methods=['POST'])
def api_subscribe():
    data = request.json
    email = data.get('email')
    code = data.get('code')
    if not verify_code(email, code):
        return jsonify({'error': 'invalid code'}), 400
    weekly = data.get('weekly', False)
    alerts = data.get('alerts', [])
    success, msg = add_subscription(email, weekly, alerts)
    if not success:
        return jsonify({'error': msg}), 400
    return '', 204


@app.route('/unsubscribe', methods=['POST'])
def api_unsubscribe():
    data = request.json
    email = data.get('email')
    code = data.get('code')
    if not verify_code(email, code):
        return jsonify({'error': 'invalid code'}), 400
    if not remove_subscription(email):
        return jsonify({'error': 'email not subscribed'}), 404
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

