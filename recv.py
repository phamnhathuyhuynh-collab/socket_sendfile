from PIL import Image
import base64
from io import BytesIO

import socket

s = socket.socket()

port = 8000
#image = Image.open("anhtest.jpg")
text = """
def zip_directory(folder_path):
    zipbuffer = io.BytesIO()
    with zipfile.ZipFile(zipbuffer, 'w', zipfile.ZIP_DEFLATED) as zf: # cần phân biệt giữa zip_deflated và zip_stored
        for folder_name, subfolers, filenames in os.walk(folder_path):
            for filename in filenames: 
                file_path = os.path.join(folder_name, filename)
                arcname = os.path.relpath(file_path, folder_path)
                zf.write(file_path, arcname)

    zip_data = zipbuffer.getvalue()
    base64_encoded = base64.b64encode(zip_data)
    return base64_encoded

def sendFile(fileName, method):
    if method == "send":
        t = fileName
        if "." in fileName:
            with open(fileName, "rb") as file_data:
                encode = base64.b64encode(file_data.read())
        else: 
            encode = zip_directory(fileName)

        s = socket.socket()
        s.connect(('192.168.1.85', port))
        s.sendall(t.encode())
        s.close()

        s = socket.socket()
        s.connect(('192.168.1.85', port))
        s.sendall(method.encode())
        s.close()

        s = socket.socket()
        s.connect(('192.168.1.85', port))  
        s.sendall(encode)
        s.close()"""
s.connect(('192.168.1.85', port))
s.sendall(text.encode())
s.close()
