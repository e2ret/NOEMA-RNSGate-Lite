#!/usr/bin/env python3
import urllib.request, xml.etree.ElementTree as ET, re

try:
    url = "http://rp5.ru/rss/1435/ru"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        xml = r.read()
    root = ET.fromstring(xml)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entry = root.find("atom:entry", ns)
    title = entry.find("atom:title", ns).text
    summary = entry.find("atom:summary", ns).text.strip()
    updated = entry.find("atom:updated", ns).text[:16].replace("T", " ")

    weather = f"""`c`Ff69--- Погода в Белгороде ---
`F0aa`c{title}
`l{summary}
`c(обновлено: {updated} UTC)
`F0aa"""

    txt = open("/root/.nomadnetwork/storage/pages/index.mu").read()
    txt = re.sub(r"##WEATHER_START##.*?##WEATHER_END##", 
                 f"##WEATHER_START##\n{weather}\n##WEATHER_END##", 
                 txt, flags=re.DOTALL)
    open("/root/.nomadnetwork/storage/pages/index.mu","w").write(txt)
    print("OK")
except Exception as e:
    print(f"ERROR: {e}")
