import socket             
from io import BytesIO
import base64
import time
import zipfile
import io
import os
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

def server():
    try:
        s = socket.socket()         
        print("ok ca marche mais j'attend tes fichiers!!")
        port = 8000               
        s.bind(('', port))         
        s.listen()     
        while True: 
            b, addr = s.accept()
            method = b.recv(1024).decode()

            c, addr = s.accept()     
            filename = c.recv(1024).decode()
            
            print ('oke je ai recu tes fichiers', addr )

            if method == "send":
                a, addr = s.accept()
                filedata = b""
                while True:
                    encodeFile = a.recv(4096)
                    if not encodeFile:
                        break
                    filedata += encodeFile
                filedata = base64.b64decode(filedata)
                if not "." in filename:
                    fileraw = io.BytesIO(filedata)
                    with zipfile.ZipFile(fileraw, 'r') as zf:
                        zf.extractall(filename) 
                else:
                    with open(filename, "wb") as f:
                        print(filename)
                        f.write(filedata)
                c.close() 
            if method == "get":
                if "." in filename:
                    with open(filename, "rb") as file_data:
                        encode = base64.b64encode(file_data.read())
                else: 
                    encode = zip_directory(filename)

                s_two = socket.socket()
                s_two.connect(('192.168.1.219', port))  
                s_two.sendall(encode)
                s_two.close()

    except Exception as e:
        print(f"[!] loi khi nhan file: {e}")

if __name__ == "__main__":
    server()