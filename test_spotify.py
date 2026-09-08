import urllib.request
import re
import sys

url = 'https://open.spotify.com/intl-pt/track/0lJdXwCEhZR7Jlwq6Za8j5?si=99c740f08ca34a09'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'})
try:
    html = urllib.request.urlopen(req).read().decode('utf-8')
    title_match = re.search(r'<meta property="og:title" content="(.*?)"', html, re.IGNORECASE)
    desc_match = re.search(r'<meta property="og:description" content="(.*?)"', html, re.IGNORECASE)
    print("Title:", title_match.group(1) if title_match else "None")
    print("Description:", desc_match.group(1) if desc_match else "None")
except Exception as e:
    print(e)
