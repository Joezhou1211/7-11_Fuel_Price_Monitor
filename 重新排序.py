import json
from datetime import datetime

# 输入数据，假设为一个列表
with open('fuel_prices.json') as f:
    data = json.load(f)

# 转换字符串时间为日期对象
def extract_date(timestamp):
    return datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S').date()

# 按日期合并数据，以最低价格为准
merged_data = {}
for entry in data:
    date = extract_date(entry["timestamp"])
    if date not in merged_data:
        merged_data[date] = entry
    else:
        if entry["price"] < merged_data[date]["price"]:
            merged_data[date] = entry

# 将结果转换为列表形式
result = list(merged_data.values())

# 打印结果
print(json.dumps(result, indent=4))

# 保存到文件
with open('merged_data.json', 'w') as f:
    json.dump(result, f, indent=4)
