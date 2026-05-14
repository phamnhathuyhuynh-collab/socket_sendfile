import sys
import socket
import base64
import zipfile
import io
from io import BytesIO
import os

port = 8000
param_1 = sys.argv[1]
param_2 = sys.argv[2]

def zip_directory(folder_path):
    try:
        zipbuffer = io.BytesIO()
        with zipfile.ZipFile(zipbuffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for folder_name, subfolers, filenames in os.walk(folder_path):
                for filename in filenames: 
                    file_path = os.path.join(folder_name, filename)
                    arcname = os.path.relpath(file_path, folder_path)
                    zf.write(file_path, arcname)
        zip_data = zipbuffer.getvalue()
        base64_encoded = base64.b64encode(zip_data)
        return base64_encoded
    except Exception as e:
        print(f"[!] Lỗi khi nén thư mục: {e}")

def sendFile(fileName, method):
    if method == "send":
        try:
            if "." in fileName:
                with open(fileName, "rb") as file_data:
                    encode = base64.b64encode(file_data.read())
            else: 
                encode = zip_directory(fileName)
            s = socket.socket()
            s.connect(('YOUR_PCs_IP_NEED_TO_SEND_FILE', port))
            s.sendall(method.encode())
            s.close()
            s = socket.socket()
            s.connect(('YOUR_PCs_IP_NEED_TO_SEND_FILE', port))
            s.sendall(fileName.encode())
            s.close()
            s = socket.socket()
            s.connect(('YOUR_PCs_IP_NEED_TO_SEND_FILE', port))  
            s.sendall(encode)
            s.close()
        except Exception as e:
            print(f"[!] Lỗi khi gửi file: {e}")

    if method == "get":
        try:
            s = socket.socket()
            s.connect(('YOUR_PCs_IP_NEED_TO_SEND_FILE', port))
            s.sendall(method.encode())
            s.close()

            s = socket.socket()
            s.connect(('YOUR_PCs_IP_NEED_TO_SEND_FILE', port))
            s.sendall(fileName.encode())
            s.close()

            s = socket.socket()
            s.bind(('', port))
            s.listen(5)
            file_encode = b""
            c, addr = s.accept()
            while True: 
                p = c.recv(4096)
                if not p: 
                    break
                file_encode += p 
            file_encode = base64.b64decode(file_encode) 
            if "." in fileName: 
                with open(fileName, "wb") as file_data: 
                    file_data.write(file_encode)
            else: 
                fileraw = io.BytesIO(file_encode)
                with zipfile.ZipFile(fileraw, 'r') as zf: 
                    zf.extractall(fileName)
        except Exception as e:
            print(f"[!] Lỗi khi nhận file: {e}")

if __name__ == "__main__":
    sendFile(param_1, param_2)
