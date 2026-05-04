import re, sqlite3, os, time, subprocess

BASE = os.path.dirname(os.path.abspath(__file__))
DB   = os.path.join(BASE, "data", "pms.db")

def save_url(url):
    conn = sqlite3.connect(DB)
    conn.execute("UPDATE email_config SET app_url=? WHERE id=1", (url,))
    conn.commit()
    conn.close()

url = ""
for _ in range(20):
    for fname in ["url.txt", "url_err.txt"]:
        try:
            text = open(os.path.join(BASE, fname)).read()
            m = re.search(r'https://[a-zA-Z0-9]+\.lhr\.life', text)
            if m:
                url = m.group(0)
        except:
            pass
    if url:
        break
    time.sleep(2)

if url:
    save_url(url)
    print("\n" + "=" * 55)
    print("  APP IS LIVE!")
    print("=" * 55)
    print(f"\n  URL: {url}")
    print("\n  Open this on any phone or laptop on any network.")
    print("  No security warnings.\n")
    # Copy to clipboard
    try:
        subprocess.run(f'echo {url}|clip', shell=True)
        print("  (URL copied to clipboard)\n")
    except:
        pass
else:
    print("\n  Could not get URL. Check internet connection and try again.")
