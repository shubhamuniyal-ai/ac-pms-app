"""
AC PMS Supervisor — starts Streamlit + tunnel, restarts both if they die.
Run this once and leave it open. It keeps everything alive automatically.
"""
import subprocess, re, sqlite3, os, time, sys, threading

BASE    = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "data", "pms.db")
PY      = sys.executable

def save_url(url):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("UPDATE email_config SET app_url=? WHERE id=1", (url,))
        conn.commit(); conn.close()
    except: pass

def start_streamlit():
    return subprocess.Popen(
        [PY, "-m", "streamlit", "run", "app.py",
         "--server.headless=true",
         "--server.enableCORS=false",
         "--server.enableXsrfProtection=false",
         "--server.port=8501"],
        cwd=BASE
    )

def start_tunnel():
    return subprocess.Popen(
        ["ssh", "-o", "StrictHostKeyChecking=no",
         "-o", "ServerAliveInterval=20",
         "-o", "ServerAliveCountMax=3",
         "-R", "80:localhost:8501", "nokey@localhost.run"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )

def watch_tunnel(proc):
    url_found = False
    def read(stream):
        nonlocal url_found
        for line in stream:
            line = line.strip()
            m = re.search(r'https://[a-zA-Z0-9]+\.lhr\.life', line)
            if m and not url_found:
                url = m.group(0)
                url_found = True
                save_url(url)
                print("\n" + "="*55)
                print(f"  APP URL: {url}")
                print("="*55)
                print("  Open this on any phone or laptop.\n")
    t1 = threading.Thread(target=read, args=(proc.stdout,), daemon=True)
    t2 = threading.Thread(target=read, args=(proc.stderr,), daemon=True)
    t1.start(); t2.start()

print("="*55)
print("  AC PMS System — Starting...")
print("="*55)

sl = start_streamlit()
print(f"[Streamlit] Started (PID {sl.pid})")
print("[Streamlit] Waiting to be ready...")
time.sleep(10)

tn = start_tunnel()
print(f"[Tunnel] Started (PID {tn.pid})")
watch_tunnel(tn)

print("[Tunnel] Waiting for URL (15s)...\n")

try:
    while True:
        time.sleep(5)
        # Restart Streamlit if dead
        if sl.poll() is not None:
            print("[Streamlit] Died — restarting...")
            sl = start_streamlit()
            print(f"[Streamlit] Restarted (PID {sl.pid})")
            time.sleep(8)
        # Restart tunnel if dead
        if tn.poll() is not None:
            print("[Tunnel] Died — restarting...")
            tn = start_tunnel()
            print(f"[Tunnel] Restarted (PID {tn.pid})")
            watch_tunnel(tn)
            time.sleep(15)
except KeyboardInterrupt:
    print("\nShutting down...")
    sl.terminate(); tn.terminate()
