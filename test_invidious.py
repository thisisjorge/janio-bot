import urllib.request
import json
import traceback

def get_invidious_stream(video_id):
    req = urllib.request.Request("https://api.invidious.io/instances.json?sort_by=health")
    with urllib.request.urlopen(req, timeout=10) as response:
        instances = json.loads(response.read().decode())
    
    for instance_info in instances:
        uri = instance_info[1].get('uri')
        if not uri: continue
        print(f"Trying {uri}...")
        try:
            api_url = f"{uri}/api/v1/videos/{video_id}"
            req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as r:
                data = json.loads(r.read().decode())
                # Find best audio format
                for fmt in data.get('adaptiveFormats', []):
                    if fmt.get('type', '').startswith('audio'):
                        print('SUCCESS WITH', uri)
                        print('Title:', data.get('title'))
                        print('Stream:', fmt.get('url')[:100])
                        return fmt.get('url')
        except Exception as e:
            pass
    print("FAILED on all instances")

get_invidious_stream("nIPGdv-vkSY")
