import time
import email.utils
import xml.etree.ElementTree as ET
import xml.sax.saxutils as saxutils
from app.services.persistence import get_hex_hash

def format_torznab_results(results, base_url, season=None, ep=None):
    timestamp = time.time() - 10800
    now_rfc = email.utils.formatdate(timestamp, usegmt=True)
    base_url = str(base_url).rstrip("/")
    
    rss = ET.Element("rss", version="2.0")
    rss.set("xmlns:torznab", "http://torznab.com/schemas/2015/feed")
    channel = ET.SubElement(rss, "channel")
    
    ET.SubElement(channel, "title").text = "AirDC++ Bridge Results"
    ET.SubElement(channel, "description").text = "AirDC++ Torznab Bridge Feed"
    ET.SubElement(channel, "language").text = "en-us"
    ET.SubElement(channel, "category").text = "2000"
    
    for res in results:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = res['name']
        
        fake_hash = get_hex_hash(res['tth'])
        
        # URL de descarga real (HTTP) con extensión fake para felicidad de Radarr
        download_url = f"{base_url}/download/{fake_hash}.torrent?name={saxutils.quoteattr(res['name'])[1:-1]}"
        fake_magnet = f"magnet:?xt=urn:btih:{fake_hash}&dn={saxutils.quoteattr(res['name'])[1:-1]}&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337%2Fannounce"
        
        ET.SubElement(item, "link").text = fake_magnet
        ET.SubElement(item, "description").text = "AirDC++ Result"
        guid = ET.SubElement(item, "guid")
        guid.text = fake_hash
        guid.set("isPermaLink", "false")
        
        enclosure = ET.SubElement(item, "enclosure")
        enclosure.set("url", download_url)
        enclosure.set("length", str(int(float(res['size']))))
        enclosure.set("type", "application/x-bittorrent")
        
        ET.SubElement(item, "pubDate").text = now_rfc
        
        # Atributos Torznab
        lang = "English"
        if any(x in res['name'].lower() for x in ["spanish", "español", "esp", "spa", " es ", ".es.", "castellano", "hdo", "tland", "hdzero", "microhd", "dual", "multi"]):
            lang = "Spanish"
            
        attrs = [
            ("category", "5000" if season else "2000"),
            ("size", str(int(float(res['size'])))),
            ("infohash", fake_hash),
            ("magneturl", fake_magnet),
            ("language", lang),
            ("seeders", "100"),
            ("peers", "10")
        ]
        
        if season:
            attrs.append(("season", season))
        if ep:
            attrs.append(("episode", ep))
        
        for name, val in attrs:
            attr = ET.SubElement(item, "{http://torznab.com/schemas/2015/feed}attr")
            attr.set("name", name)
            attr.set("value", val)
            
    return ET.tostring(rss, encoding="unicode", method="xml")

def get_test_xml():
    now_rfc = email.utils.formatdate(usegmt=True)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:torznab="http://torznab.com/schemas/2015/feed" version="2.0">
<channel>
    <title>AirDC++ Bridge Test</title>
    <description>AirDC++ Torznab Bridge Feed</description>
    <language>en-us</language>
    <category>2000</category>
    <item>
        <title>Test Movie File 1080p.mkv</title>
        <guid isPermaLink="false">MOVIEHASH123</guid>
        <pubDate>{now_rfc}</pubDate>
        <size>2147483648</size>
        <link>magnet:?xt=urn:btih:6363636363636363636363636363636363636363&amp;dn=MovieTest</link>
        <enclosure url="http://localhost:8000/download/6363636363636363636363636363636363636363.torrent" length="2147483648" type="application/x-bittorrent" />
        <torznab:attr name="category" value="2000"/>
        <torznab:attr name="size" value="2147483648"/>
        <torznab:attr name="infohash" value="6363636363636363636363636363636363636363"/>
        <torznab:attr name="seeders" value="50"/>
        <torznab:attr name="peers" value="10"/>
    </item>
</channel>
</rss>"""

def get_caps_xml():
    return """<?xml version="1.0" encoding="UTF-8"?>
<caps>
    <server version="1.0" title="AirDC++ Bridge" />
    <limits max="100" default="50" />
    <registration status="no" open="yes" />
    <searching>
        <search available="yes" supportedParams="q,imdbid,tmdbid" />
        <tv-search available="yes" supportedParams="q,season,ep,imdbid,tvdbid" />
        <movie-search available="yes" supportedParams="q,imdbid,tmdbid" />
    </searching>
    <categories>
        <category id="2000" name="Movies">
            <subcat id="2040" name="HD" />
        </category>
        <category id="5000" name="TV">
            <subcat id="5040" name="HD" />
        </category>
    </categories>
</caps>"""
