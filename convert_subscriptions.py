import json
RECIPIENT_FILE = 'recipient_mails.json'

def load_json(path):
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=4)

def convert():
    data = load_json(RECIPIENT_FILE)
    if data is None:
        print('No subscription data to convert.')
        return
    if isinstance(data, dict) and {'weekly', 'alerts', 'info'} <= set(data.keys()):
        print('Subscriptions already in new format.')
        return
    if isinstance(data, list):
        new_data = {
            'weekly': data,
            'alerts': {},
            'info': {email: {} for email in data}
        }
    else:
        print('Unrecognized subscription format. No changes made.')
        return
    save_json(RECIPIENT_FILE, new_data)
    print('Subscriptions converted to new format.')

if __name__ == '__main__':
    convert()
