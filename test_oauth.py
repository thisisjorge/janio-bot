import subprocess
import time

try:
    print("Running yt-dlp with oauth2...")
    process = subprocess.Popen(
        ["yt-dlp", "--username", "oauth2", "--password", "", "https://www.youtube.com/watch?v=tCBDpRRqxjs"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    
    start_time = time.time()
    while time.time() - start_time < 10:
        line = process.stdout.readline()
        if not line:
            break
        print(line.strip())
        if "device" in line.lower() or "code" in line.lower():
            pass
            
    process.terminate()
except Exception as e:
    print(f"Error: {e}")
