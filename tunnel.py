"""
Starts an SSH reverse tunnel via localhost.run — gives a clean HTTPS URL
with no security warnings. Works on any device, any network.
"""
import subprocess
import re
import os
import sqlite3
import threading

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "pms.db")

def update_app_url(url):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("UPDATE email_config SET app_url=? WHERE id=1", (url,))
        conn.commit()
        conn.close()
        print(f"[DB] App URL saved: {url}")
    except Exception as e:
        print(f"[DB] Warning: {e}")

URL_PATTERN = re.compile(r'https://[a-zA-Z0-9]+\.lhr\.life')

def main():
    print("=" * 60)
    print("  AC PMS System — Public Internet URL")
    print("=" * 60)
    print("Connecting... please wait 10-20 seconds\n")

    cmd = [
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "ServerAliveInterval=30",
        "-o", "ServerAliveCountMax=5",
        "-R", "80:localhost:8501",
        "nokey@localhost.run"
    ]

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    url_found = False

    def read_stream(stream):
        nonlocal url_found
        for line in stream:
            clean = line.strip()
            if not clean:
                continue
            match = URL_PATTERN.search(clean)
            if match and not url_found:
                public_url = match.group(0)
                url_found = True
                print("\n" + "=" * 60)
                print(f"  YOUR APP URL:")
                print(f"  {public_url}")
                print("=" * 60)
                print("\n  Open this on ANY phone or laptop on ANY network.")
                print("  No login or security warning — works like a normal website.")
                print("\n  Keep this window open while vendors use the app.\n")
                update_app_url(public_url)

    t1 = threading.Thread(target=read_stream, args=(proc.stdout,), daemon=True)
    t2 = threading.Thread(target=read_stream, args=(proc.stderr,), daemon=True)
    t1.start()
    t2.start()

    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        print("\nTunnel stopped.")

if __name__ == "__main__":
    main()
