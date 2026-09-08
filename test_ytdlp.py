import subprocess
try:
    print("Testing yt-dlp with cookies...")
    subprocess.run(["yt-dlp", "--cookies", "/app/cookies.txt", "--simulate", "https://www.youtube.com/watch?v=HydkjjDNTmY"])
except Exception as e:
    print(f"Error: {e}")
