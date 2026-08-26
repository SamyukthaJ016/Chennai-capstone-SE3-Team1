import requests

url = "https://y4t9nq2bqf.execute-api.eu-west-2.amazonaws.com/v1/quotes/AAPL"

headers = {
    "X-Api-Key": "leap-sprint4-key"
}

response = requests.get(url, headers=headers)

print("Status:", response.status_code)
print("Response:")

try:
    print(response.json())
except ValueError:
    print(response.text)
