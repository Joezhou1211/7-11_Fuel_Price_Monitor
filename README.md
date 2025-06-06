# Fuel Price Monitoring Script

## Introduction
This script is designed to monitor fuel prices in the QLD region for **all** fuel types (can be easily modified to your Area). It fetches the latest prices, updates local records, generates a price chart, and sends alert emails when certain conditions are met (when the fuel is relatively cheap). With this Monitor, you will be able to get the cheapest fuel by using 'My 7-Eleven' APP. (Simulate your location to the lowest price area then lock the fuel price. I can't share more about it, you might need some research).

## How It Works
### Fetching Fuel Prices:

The script fetches fuel prices from the API https://projectzerothree.info/api.php?format=json.
It extracts fuel prices for **all available types** in the QLD region.
The fetched prices are saved locally in fuel_prices.json.
### Updating Local Records:

The script maintains a record of the latest 90 days of fuel prices.
It updates the local JSON file with new price data.
### Generating Price Chart:

The script generates a price chart using Matplotlib.
The chart includes price trends for each fuel type and the highest price in the last 90 days.
### Sending Alert Emails:

The monitor can send alert emails when the price drops below a calculated threshold
(95% of the current moving average and at least 10% lower than the 90‑day high).
The alert email includes the station information, current price and the alert line.
### Sending Price Chart Emails:

The script sends a weekly email with the generated price chart.
The email includes information about the number of data points, the current trigger price, and the highest price in the last 90 days.

## Setup
Follow these steps to get the monitor running:
1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```
2. **Configure mail** – enable Gmail 2‑Step Verification, create an App Password and edit `MAIL_USER`/`MAIL_PASS` in `monitor.py`.
3. **(Optional) Seed historical data** – around 30 days improves accuracy. Download it from [projectzerothree.info](https://projectzerothree.info/trends.php).
4. **Start the service** (use `nohup` or `screen` on a server):
   ```bash
   python monitor.py
   ```
5. Visit `http://<server>:6789` to view charts or manage subscriptions.

# Chart will be sent to email
Alert line(Red): you will be notified via email when the price go below the line.
Price(Green): Historical prices.
90 Days Highest(Horizontal Red): Highest in 90 days.

<img width="348" alt="image" src="https://github.com/Joezhou1211/7-11_Fuel_Price_Monitor/assets/121386280/a1f4d29d-6090-4bfc-b984-bfb4c144f00d">

![image](https://github.com/Joezhou1211/7-11_Fuel_Price_Monitor/assets/121386280/76c5904e-23b2-4cfe-b330-7e39758212ce)

# You can now use an HTML page to view real-time price charts and Add/Remove the recipients.
- Try it on [http://20.169.240.82:7001] PLEASE DO NOT ATTACK THIS SERVER.
<img width="1435" alt="image" src="https://github.com/user-attachments/assets/c405bd42-c833-4337-8df9-a0310378f67c">
