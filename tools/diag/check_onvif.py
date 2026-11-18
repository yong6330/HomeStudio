import urllib.request
import os

def test_onvif():
    ip = "192.168.0.32"
    url = f"http://{ip}/onvif/device_service"
    
    # Simple SOAP GetCapabilities request
    soap_req = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope" xmlns:tds="http://www.onvif.org/ver10/device/wsdl">
  <soap:Body>
    <tds:GetCapabilities>
      <tds:Category>All</tds:Category>
    </tds:GetCapabilities>
  </soap:Body>
</soap:Envelope>"""

    headers = {
        "Content-Type": "application/soap+xml; charset=utf-8; action=\"http://www.onvif.org/ver10/device/wsdl/GetCapabilities\"",
    }

    try:
        req = urllib.request.Request(url, data=soap_req.encode(), headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            print("ONVIF status:", resp.status)
            print("ONVIF resp:", resp.read()[:500].decode(errors="replace"))
    except Exception as e:
        print("ONVIF error:", e)

if __name__ == "__main__":
    test_onvif()
