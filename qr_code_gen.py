"""
Karaokedesyl - Version 3.0
A Flask-based Karaoke Song Selection and Playlist Management System.
"""

# generate_qr_static.py
import qrcode

url = "https://karaokedesyl-1.onrender.com/"
img = qrcode.make(url)
img.save("karaokedesyl_qr.png")
