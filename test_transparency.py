import webview
import time
import os

# Try setting WEBVIEW2 default background color to transparent
os.environ["WEBVIEW2_DEFAULT_BACKGROUND_COLOR"] = "00000000"

html = """
<html>
<body style="background: transparent; color: white; margin: 50px;">
    <h1>Transparent Test</h1>
    <div style="background: red; width: 100px; height: 100px; border-radius: 50px;"></div>
</body>
</html>
"""

window = webview.create_window(
    'Transparent Test', 
    html=html, 
    transparent=True, 
    frameless=True,
    width=400, height=400
)

def close_later():
    time.sleep(5)
    window.destroy()

webview.start(close_later)
