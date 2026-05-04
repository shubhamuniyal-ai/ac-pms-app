"""
Starts an SSH reverse tunnel via serveo.net and updates the App URL in the database.
Run this alongside the Streamlit app to get a public internet URL.
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
        print(f"[DB] Warning: could not update URL — {e}")

URL_PATTERN = re.compile(r'https?://[a-zA-Z0-9\-]+\.serveousercontent\.com|https?://[a-zA-Z0-9\-]+\.serveo\.net')

def main():
    print("=" * 60)
    print("  AC PMS System — Public Internet URL")
    print("=" * 60)
    print("Connecting via serveo.net ...")
    print("(Wait 10-20 seconds for URL)\n")

    cmd = ["ssh", "-o", "StrictHostKeyChecking=no",
           "-o", "ServerAliveInterval=30",
           "-o", "ServerAliveCountMax=3",
           "-R", "80:localhost:8501", "serveo.net"]

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    url_found = False

    def read_stream(stream):
        nonlocal url_found
        for line in stream:
            clean = re.sub(r'\x1b\[[0-9;]*m', '', line).strip()
            if clean:
                match = URL_PATTERN.search(clean)
                if match and not url_found:
                    public_url = match.group(0)
                    url_found = True
                    print("\n" + "=" * 60)
                    print(f"  PUBLIC URL: {public_url}")
                    print("=" * 60)
                    print(f"\n  Open this on any phone or laptop:")
                    print(f"  {public_url}\n")
                    print("  Tunnel is active. Keep this window open.")
                    print("  Press Ctrl+C to stop.\n")
                    update_app_url(public_url)
                else:
                    print(clean)

    t1 = threading.Thread(target=read_stream, args=(proc.stdout,), daemon=True)
    t2 = threading.Thread(target=read_stream, args=(proc.stderr,), daemon=True)
    t1.start(); t2.start()

    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        print("\nTunnel stopped.")

if __name__ == "__main__":
    main()
