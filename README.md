# Fuel Price Monitoring Script

## Introduction
This script is designed to monitor fuel prices in the QLD region for U91 gasoline(can be easily modified to your Area). It fetches the latest prices, updates local records, generates a price chart, and sends alert emails when certain conditions are met(When the fuel is relatively cheap). with this Monitor, You will be able to get the cheapest fuel by using 'My 7-Eleven' APP. (Simulate your location to the lowest price area then lock the fuel price. I can't share more about it, you might need some research).

## How It Works
### Fetching Fuel Prices:

The script fetches fuel prices from the API https://projectzerothree.info/api.php?format=json.
It extracts U91 fuel prices for the QLD region.
The fetched prices are saved locally in fuel_prices.json.
### Updating Local Records:

The script maintains a record of the latest 90 days of fuel prices.
It updates the local JSON file with new price data.
### Generating Price Chart:

The script generates a price chart using Matplotlib.
The chart includes U91 prices and the highest price in the last 90 days.
### Sending Alert Emails:

The script sends an alert email if the current price exceeds 105% of the last alert price.
The alert email includes the date and price of the alert.
### Sending Price Chart Emails:

The script sends a weekly email with the generated price chart.
The email includes information about the number of data points, the current trigger price, and the highest price in the last 90 days.

## Requirements
To use this Monitor, you need to:
- Have a working server, and have 'nohup' or 'screen' installed. (you need to know how to use them)
- Turn on 2-Step Verification in Gmail and grab an 'APP Password' in [App Passwords](https://support.google.com/accounts/answer/185833?hl=en&ref_topic=7189145&sjid=9746205447382071228-AP)
- Update the mail, mail_password, and recipient_mails variables with your Gmail/APP Password and update the recipient emails when needed.
- Install Some packages:
  ```bash
  pip install -r requirements.txt
  ```
- In your server, during a 'nohup' or 'screen' session, run: 
  ```bash
  Python main.py 
  ```
- You will need enough data to start(around 30 days for accuracy), please get them from [here](https://projectzerothree.info/trends.php)

# Chart will be sent to email
Alert line(Red): you will be notified via email when the price go below the line.
Price(Green): Historical prices.
90 Days Highest(Horizontal Red): Highest in 90 days.

<img width="348" alt="image" src="https://github.com/Joezhou1211/7-11_Fuel_Price_Monitor/assets/121386280/a1f4d29d-6090-4bfc-b984-bfb4c144f00d">

![image](https://github.com/Joezhou1211/7-11_Fuel_Price_Monitor/assets/121386280/76c5904e-23b2-4cfe-b330-7e39758212ce)

# You can now use an HTML page to view real-time price charts and Add/Remove the recipients.
- Try it on [http://20.169.240.82:7001]
<img width="1435" alt="image" src="https://github.com/user-attachments/assets/c405bd42-c833-4337-8df9-a0310378f67c">
