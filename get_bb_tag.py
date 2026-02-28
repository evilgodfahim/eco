import requests
import os

repo = "MiddleSchoolStudent/BotBrowser"
url = f"https://api.github.com/repos/{repo}/releases/latest"
headers = {"Authorization": f"Bearer {os.environ.get('GH_TOKEN')}"}

resp = requests.get(url, headers=headers)
data = resp.json()

tag = data['tag_name']
assets = [a['name'] for a in data['assets']]

with open("/tmp/bb_assets.txt", "w") as f:
    f.write("\n".join(assets))

print(tag)
